"""
Админ-панель (SQLAdmin): аутентификация, виджеты форм, ModelView для Property/PropertyImage/PropertyDocument, BaseView для папок.
"""
import asyncio
import io
import os
import re
import shutil
import uuid
import base64
from typing import Optional, Tuple, Union

from fastapi.responses import RedirectResponse, Response
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqladmin import BaseView, ModelView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.filters import ForeignKeyFilter
from starlette.requests import Request

from slugify import slugify
from wtforms import SelectField, StringField, FileField
from markupsafe import Markup

from app.database import SessionLocal
from app.models import Property, PropertyImage, PropertyDocument
from app.feed import generate_avito_feed


# --- ВИЗУАЛЬНЫЙ РЕДАКТОР ПРЕВЬЮ (CROPPER.JS) ---
class ImageCropWidget:
    def __call__(self, field, **kwargs):
        html = f"""
        <div class="image-cropper-container" style="background: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #ddd;">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>

            <input type="hidden" name="{field.name}" id="hidden_{field.id}" value="{field.data or ''}">
            
            <label class="form-label fw-bold">Выберите фото для превью:</label>
            <input type="file" id="file_{field.id}" accept="image/*" class="form-control mb-3">
            
            <div id="preview_container_{field.id}" style="display: {'block' if field.data else 'none'};">
                <p class="text-muted mb-1"><small>Текущее превью:</small></p>
                <img id="preview_{field.id}" src="{field.data or ''}" style="max-height: 200px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            </div>

            <div id="modal_{field.id}" style="display: none; margin-top: 15px;">
                <p class="text-primary fw-bold">Выделите нужную область (4:3):</p>
                <div style="max-height: 400px; overflow: hidden; border: 2px dashed #5a6c7d;">
                    <img id="image_{field.id}" style="max-width: 100%; display: block;">
                </div>
                <div class="mt-3">
                    <button type="button" class="btn btn-success" onclick="cropImage_{field.id}()">Обрезать и Применить</button>
                    <button type="button" class="btn btn-secondary ms-2" onclick="cancelCrop_{field.id}()">Отмена</button>
                </div>
            </div>

            <script>
                let cropper_{field.id} = null;
                document.getElementById('file_{field.id}').addEventListener('change', function(e) {{
                    const files = e.target.files;
                    if (files && files.length > 0) {{
                        const reader = new FileReader();
                        reader.onload = function(event) {{
                            document.getElementById('image_{field.id}').src = event.target.result;
                            document.getElementById('modal_{field.id}').style.display = 'block';
                            document.getElementById('preview_container_{field.id}').style.display = 'none';
                            if (cropper_{field.id}) cropper_{field.id}.destroy();
                            cropper_{field.id} = new Cropper(document.getElementById('image_{field.id}'), {{
                                aspectRatio: 4 / 3,
                                viewMode: 1,
                            }});
                        }};
                        reader.readAsDataURL(files[0]);
                    }}
                }});

                function cropImage_{field.id}() {{
                    if (!cropper_{field.id}) return;
                    const canvas = cropper_{field.id}.getCroppedCanvas({{ width: 800, height: 600 }});
                    const base64data = canvas.toDataURL('image/jpeg', 0.85); 
                    document.getElementById('hidden_{field.id}').value = base64data;
                    document.getElementById('preview_{field.id}').src = base64data;
                    document.getElementById('preview_container_{field.id}').style.display = 'block';
                    document.getElementById('modal_{field.id}').style.display = 'none';
                    cropper_{field.id}.destroy();
                    cropper_{field.id} = null;
                }}

                function cancelCrop_{field.id}() {{
                    document.getElementById('modal_{field.id}').style.display = 'none';
                    document.getElementById('file_{field.id}').value = '';
                    document.getElementById('preview_container_{field.id}').style.display = document.getElementById('hidden_{field.id}').value ? 'block' : 'none';
                    if (cropper_{field.id}) {{ cropper_{field.id}.destroy(); cropper_{field.id} = null; }}
                }}
            </script>
        </div>
        """
        return Markup(html)


class ImageCropField(StringField):
    widget = ImageCropWidget()


# --- ВИДЖЕТ МНОЖЕСТВЕННОЙ ЗАГРУЗКИ ФАЙЛОВ ---
class MultiFileWidget:
    """Рендерит <input type="file" multiple> с заданным accept."""
    def __init__(self, accept: str = "*"):
        self.accept = accept

    def __call__(self, field, **kwargs):
        return Markup(
            f'<input type="file" name="{field.name}" multiple accept="{self.accept}" class="form-control">'
        )


class MultiFileField(StringField):
    """Поле формы только для отображения multi-file input; файлы читаем из request.form() в after_model_change."""
    def __init__(self, label=None, accept="*", **kwargs):
        super().__init__(label, **kwargs)
        self.widget = MultiFileWidget(accept=accept)


# --- ХЕЛПЕР: ПАПКИ ЗАГРУЗКИ ПО ОБЪЕКТУ (название + id) ---
def _property_folder_name(property_id: int, title: Optional[str] = None) -> str:
    """Возвращает имя папки объекта (без создания директорий). Для отображения в админке."""
    if title is None:
        with SessionLocal() as session:
            prop = session.query(Property).filter(Property.id == property_id).first()
            title = (prop.title if prop else "") or ""
    slug = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip()[:50] or str(property_id)
    return f"{property_id}_{slug}"


def _get_property_upload_dirs(property_id: int) -> Tuple[str, str]:
    """Возвращает (путь к папке фото, путь к папке документов) для объекта. Папки создаются при первом вызове."""
    with SessionLocal() as session:
        prop = session.query(Property).filter(Property.id == property_id).first()
        title = (prop.title if prop else "") or ""
    slug = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip()[:50] or str(property_id)
    folder_name = f"{property_id}_{slug}"
    base = os.path.join("static", "uploads", "properties", folder_name)
    images_dir = os.path.join(base, "images")
    documents_dir = os.path.join(base, "documents")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)
    return images_dir, documents_dir


# --- ОПТИМИЗАЦИЯ ИЗОБРАЖЕНИЙ (Pillow): ресайз до 1600px, JPEG 85% ---
IMAGE_MAX_WIDTH = 1600
IMAGE_JPEG_QUALITY = 85


def _resize_image_sync(
    source: Union[str, bytes],
    dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY,
) -> bool:
    """
    Уменьшает изображение до max_width по ширине (пропорции сохраняются), сохраняет в JPEG.
    source — путь к файлу (str) или байты. Возвращает True при успехе, False при ошибке (битый/не картинка).
    """
    try:
        if isinstance(source, bytes):
            img = Image.open(io.BytesIO(source))
        else:
            img = Image.open(source)
        img.load()
    except Exception:
        return False
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        new_h = max(1, int(h * ratio))
        img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        img.save(dest_path, "JPEG", quality=quality, optimize=True)
    except Exception:
        return False
    return True


async def _resize_image_async(
    source: Union[str, bytes],
    dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY,
) -> bool:
    """Асинхронная обёртка: Pillow выполняется в executor, чтобы не блокировать event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _resize_image_sync(source, dest_path, max_width, quality),
    )


def _normalize_image_url(file_path: str) -> str:
    """Приводит путь к URL для фронта: всегда начинается с / (и с /static/ для статики)."""
    path = file_path.replace(os.sep, "/").lstrip("/")
    if not path.startswith("static/"):
        path = "static/" + path.lstrip("/") if path else "static"
    return "/" + path


# --- АУТЕНТИФИКАЦИЯ АДМИН-ПАНЕЛИ ---
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        expected_username = os.getenv("ADMIN_USERNAME", "admin")
        expected_password = os.getenv("ADMIN_PASSWORD", "admin")

        if username == expected_username and password == expected_password:
            request.session.update({"is_admin": True})
            return True

        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("is_admin"))


# --- АДМИНКА ДЛЯ ГАЛЕРЕИ ---
class PropertyImageAdmin(ModelView, model=PropertyImage):
    name = "Фото галереи"
    name_plural = "Галерея"
    form_overrides = {"image_url": FileField}
    column_list = [PropertyImage.id, PropertyImage.property, PropertyImage.image_url]
    column_labels = {PropertyImage.property: "Объект (папка)"}
    column_filters = [
        ForeignKeyFilter(PropertyImage.property_id, Property.title, Property, title="Папка (объект)"),
    ]

    column_formatters = {
        PropertyImage.property: lambda m, a: Markup(
            f'<span title="Папка: {_property_folder_name(m.property_id, getattr(m.property, "title", None))}">'
            f"{(m.property.title if m.property else '') or ('Объект #' + str(m.property_id))}</span>"
        ),
        PropertyImage.image_url: lambda m, a: Markup(f'<img src="{m.image_url}" style="height: 50px;">') if m.image_url else "",
    }

    async def on_model_change(self, data, model, is_created, request):
        file = data.get("image_url")
        if file and hasattr(file, "filename") and file.filename:
            property_id = data.get("property_id") or (model.property_id if model else None)
            if property_id:
                images_dir, _ = _get_property_upload_dirs(property_id)
                upload_dir = images_dir
            else:
                upload_dir = "static/uploads/gallery"
                os.makedirs(upload_dir, exist_ok=True)
            file.file.seek(0)
            raw_bytes = file.file.read()
            dest_path = os.path.join(upload_dir, f"{uuid.uuid4()}.jpg")
            ok = await _resize_image_async(raw_bytes, dest_path)
            if not ok:
                dest_path = os.path.join(upload_dir, f"{uuid.uuid4()}{os.path.splitext(file.filename)[1] or '.jpg'}")
                with open(dest_path, "wb") as f:
                    f.write(raw_bytes)
            data["image_url"] = _normalize_image_url(dest_path)


# --- АДМИНКА ДЛЯ ДОКУМЕНТОВ ---
class PropertyDocumentAdmin(ModelView, model=PropertyDocument):
    name = "Документ"
    name_plural = "Документы"
    form_overrides = {"document_url": FileField}
    column_list = [PropertyDocument.id, PropertyDocument.property, PropertyDocument.title]
    column_labels = {PropertyDocument.property: "Объект (папка)"}
    column_filters = [
        ForeignKeyFilter(PropertyDocument.property_id, Property.title, Property, title="Папка (объект)"),
    ]

    column_formatters = {
        PropertyDocument.property: lambda m, a: Markup(
            f'<span title="Папка: {_property_folder_name(m.property_id, getattr(m.property, "title", None))}">'
            f"{(m.property.title if m.property else '') or ('Объект #' + str(m.property_id))}</span>"
        ),
        PropertyDocument.title: lambda m, a: (
            Markup(f'<a href="{m.document_url}" target="_blank" rel="noopener">{(m.title or "Документ")}</a>')
            if (m.document_url and m.document_url.strip())
            else Markup(str(m.title or "—"))
        ),
    }

    async def on_model_change(self, data, model, is_created, request):
        file = data.get("document_url")
        if file and hasattr(file, "filename") and file.filename:
            property_id = data.get("property_id") or (model.property_id if model else None)
            if property_id:
                _, documents_dir = _get_property_upload_dirs(property_id)
                upload_dir = documents_dir
            else:
                upload_dir = "static/documents"
                os.makedirs(upload_dir, exist_ok=True)
            safe_filename = f"{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"
            path = os.path.join(upload_dir, safe_filename)
            with open(path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            data["document_url"] = f"/{path.replace(os.sep, '/')}"


# --- ГЛАВНАЯ АДМИНКА ОБЪЕКТА ---
class PropertyAdmin(ModelView, model=Property):
    column_list = [
        Property.id,
        Property.title,
        Property.deal_type,
        Property.category,
        Property.price,
        Property.is_active,
        Property.show_on_main,
        Property.main_page_order,
        "children_count_badge",
    ]

    column_details_list = [
        Property.id,
        Property.title,
        Property.description,
        Property.price,
        Property.area,
        Property.address,
        Property.deal_type,
        Property.category,
        Property.latitude,
        Property.longitude,
        Property.is_active,
        Property.show_on_main,
        Property.main_page_order,
        Property.parent_id,
        Property.children,
    ]
    column_labels = {
        Property.show_on_main: "На главной",
        Property.main_page_order: "Порядок на главной",
        Property.children: "Вложенные",
        "children_count_badge": "Состав",
        Property.is_active: "Активно",
    }
    name = "Объект"
    name_plural = "Объекты недвижимости"
    icon = "fa-solid fa-building"
    edit_template = "sqladmin/edit_property.html"

    # При открытии редактирования подгружаем фото и документы для отображения
    def form_edit_query(self, request: Request):
        stmt = super().form_edit_query(request)
        return stmt.options(
            selectinload(Property.images),
            selectinload(Property.documents),
            selectinload(Property.children),
            selectinload(Property.parent),
        )

    # extra_images и extra_documents не в form_columns: это не поля модели, добавляются в scaffold_form
    form_columns = [
        "title",
        "slug",
        "description",
        "price",
        "area",
        "address",
        "main_image",
        "is_active",
        "show_on_main",
        "main_page_order",
        "deal_type",
        "category",
        "latitude",
        "longitude",
        "parent_id",
    ]

    form_overrides = {
        "deal_type": SelectField,
        "category": SelectField,
        "main_image": ImageCropField,
    }

    form_args = {
        "deal_type": {"choices": [("Аренда", "Аренда"), ("Продажа", "Продажа")]},
        "category": {"choices": [("Офис", "Офис"), ("Торговая площадь", "Торговая площадь"), ("Свободного назначения", "Свободного назначения"), ("Промышленное", "Промышленное"), ("Склад", "Склад"), ("ГАБ", "ГАБ"), ("Здание", "Здание")]},
        "show_on_main": {"label": "Показывать на главной (1 из 3)"},
        "main_page_order": {"label": "Порядок на главной (1, 2 или 3)"},
    }

    column_formatters = {
        "children_count_badge": lambda m, a: (
            Markup(
                f"<a href='/admin/property/list?parent_id={m.id}' style='text-decoration: none;'>"
                f"<span class='badge bg-info'>{m.children_count_badge}</span>"
                "</a>"
            )
            if m.children
            else Markup(
                f"<a href='/admin/property/list?parent_id={m.id}' style='text-decoration: none;'>"
                "<span class='badge bg-secondary'>Целиком</span>"
                "</a>"
            )
        )
    }

    def list_query(self, request: Request):
        """
        Умная фильтрация списка объектов:
        - по умолчанию показываем только родительские здания (parent_id IS NULL);
        - если в query-параметрах есть parent_id, показываем только детей этого здания.
        """
        parent_id = request.query_params.get("parent_id")
        stmt = select(Property)

        if parent_id and parent_id.isdigit():
            stmt = stmt.where(Property.parent_id == int(parent_id))
        else:
            stmt = stmt.where(Property.parent_id.is_(None))

        return stmt

    async def scaffold_form(self, rules=None):
        form_class = await super().scaffold_form(rules)
        # Множественная загрузка: фото и документы (файлы читаем из request в after_model_change)
        setattr(
            form_class,
            "extra_images",
            MultiFileField("Доп. фото (можно несколько)", accept="image/*"),
        )
        setattr(
            form_class,
            "extra_documents",
            MultiFileField(
                "Документы (PDF, Word, Excel и т.д.)",
                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.odt,.ods,.odp",
            ),
        )
        return form_class

    async def on_model_change(self, data, model, is_created, request):
        # Автогенерация slug из title, если пусто
        slug_val = data.get("slug")
        if not slug_val or not str(slug_val).strip():
            data["slug"] = slugify(data.get("title") or "object", allow_unicode=False) or "object"

        # Нормализация полей «на главной»: тип и пустые значения (галочка при редактировании может не приходить)
        if "show_on_main" not in data:
            data["show_on_main"] = False
        else:
            val = data["show_on_main"]
            data["show_on_main"] = bool(val and str(val).lower() not in ("", "false", "0", "n", "no"))
        if "main_page_order" in data:
            val = data["main_page_order"]
            if val is None or (isinstance(val, str) and val.strip() == ""):
                data["main_page_order"] = None
            else:
                try:
                    data["main_page_order"] = int(val) if val is not None else None
                except (TypeError, ValueError):
                    data["main_page_order"] = None

        image_data = data.get("main_image")
        if isinstance(image_data, str) and image_data.startswith("data:image"):
            try:
                header, encoded = image_data.split(",", 1)
                file_data = base64.b64decode(encoded)
            except Exception:
                file_data = None
            if file_data:
                prop_id = getattr(model, "id", None)
                if prop_id:
                    images_dir, _ = _get_property_upload_dirs(prop_id)
                    upload_dir = images_dir
                else:
                    upload_dir = os.path.join("static", "uploads", "properties", "tmp")
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, f"{uuid.uuid4()}.jpg")
                ok = await _resize_image_async(file_data, file_path)
                if not ok:
                    with open(file_path, "wb") as f:
                        f.write(file_data)
                data["main_image"] = _normalize_image_url(file_path)
        elif not image_data or not isinstance(image_data, str):
            # Пустое значение или не строка (например, файл) — не перезаписываем при редактировании
            if is_created:
                data["main_image"] = None
            else:
                data.pop("main_image", None)

        # Убираем поля множественной загрузки из data (файлы обрабатываем в after_model_change из request)
        data.pop("extra_images", None)
        data.pop("extra_documents", None)

    async def after_model_change(self, data, model, is_created, request):
        form_data = await request.form()
        image_files = form_data.getlist("extra_images") or []
        doc_files = form_data.getlist("extra_documents") or []

        images_dir = documents_dir = None
        if image_files or doc_files:
            images_dir, documents_dir = _get_property_upload_dirs(model.id)

        # Гарантируем, что превью main_image лежит в папке объекта
        final_main_image_url = model.main_image
        if model.main_image:
            if images_dir is None:
                images_dir, documents_dir = _get_property_upload_dirs(model.id)

            current_url = model.main_image
            rel_path = current_url.lstrip("/")

            # Ожидаемый префикс пути для изображений объекта
            images_prefix = images_dir.replace(os.sep, "/")
            if not images_prefix.endswith("/"):
                images_prefix = images_prefix + "/"

            # Если превью не лежит в каталоге images этого объекта, переносим и при необходимости оптимизируем
            if not rel_path.startswith(images_prefix):
                old_path = rel_path
                if os.path.exists(old_path):
                    new_path = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
                    os.makedirs(images_dir, exist_ok=True)
                    try:
                        with open(old_path, "rb") as f:
                            raw = f.read()
                        if await _resize_image_async(raw, new_path):
                            os.remove(old_path)
                        else:
                            shutil.move(old_path, new_path)
                    except Exception:
                        ext = os.path.splitext(old_path)[1] or ".jpg"
                        new_path = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
                        shutil.move(old_path, new_path)
                    final_main_image_url = _normalize_image_url(new_path)

                    with SessionLocal() as session:
                        prop = session.get(Property, model.id)
                        if prop:
                            prop.main_image = final_main_image_url
                            session.commit()

        # Создаём запись в галерее для превью, чтобы оно отображалось среди фото объекта
        if final_main_image_url:
            normalized_main = _normalize_image_url(final_main_image_url)
            with SessionLocal() as session:
                exists = (
                    session.query(PropertyImage)
                    .filter(
                        PropertyImage.property_id == model.id,
                        PropertyImage.image_url == normalized_main,
                    )
                    .first()
                )
                if not exists:
                    session.add(
                        PropertyImage(
                            property_id=model.id,
                            image_url=normalized_main,
                        )
                    )
                    session.commit()

        for f in image_files:
            if not getattr(f, "filename", None):
                continue
            f.file.seek(0)
            raw_bytes = f.file.read()
            dest_path = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
            ok = await _resize_image_async(raw_bytes, dest_path)
            if not ok:
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                dest_path = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
                with open(dest_path, "wb") as out:
                    out.write(raw_bytes)
            url_path = _normalize_image_url(dest_path)
            with SessionLocal() as session:
                session.add(PropertyImage(property_id=model.id, image_url=url_path))
                session.commit()

        for f in doc_files:
            if not getattr(f, "filename", None):
                continue
            ext = os.path.splitext(f.filename)[1] or ""
            safe_filename = f"{uuid.uuid4()}{ext}"
            path = os.path.join(documents_dir, safe_filename)
            with open(path, "wb") as out:
                shutil.copyfileobj(f.file, out)
            title = os.path.splitext(f.filename)[0] or "Документ"
            url_path = f"/{path.replace(os.sep, '/')}"
            with SessionLocal() as session:
                session.add(
                    PropertyDocument(
                        property_id=model.id,
                        title=title,
                        document_url=url_path,
                    )
                )
                session.commit()

    @action(
        name="clone_to_child",
        label="Нарезать (создать вложенное)",
        add_in_detail=True,
        add_in_list=True,
    )
    async def clone_to_child(self, request: Request):
        # Определяем исходный объект: из списка (pks) или из детальной формы (pk)
        pks_param = request.query_params.get("pks")
        original_id = None
        if pks_param:
            ids = [pk for pk in pks_param.split(",") if pk]
            if ids:
                original_id = int(ids[0])
        if original_id is None:
            pk = request.path_params.get("pk")
            if pk is not None:
                original_id = int(pk)

        if original_id is None:
            return Response(content="Не удалось определить исходный объект", status_code=400)

        with SessionLocal() as session:
            original: Property | None = session.get(Property, original_id)
            if not original:
                return Response(content="Исходный объект не найден", status_code=404)

            clone = Property(
                title=f"{original.title} (Часть)" if original.title else "Часть объекта",
                description=original.description,
                price=original.price,
                area=original.area,
                address=original.address,
                main_image=original.main_image,
                is_active=False,
                deal_type=original.deal_type,
                category=original.category,
                latitude=original.latitude,
                longitude=original.longitude,
                parent_id=original.id,
            )
            session.add(clone)
            session.commit()

        referer = request.headers.get("referer")
        redirect_url = referer or str(request.url_for("admin:list", identity="property"))
        return RedirectResponse(url=redirect_url, status_code=303)

    @action(name="export_xml", label="Скачать XML для Авито")
    async def export_xml(self, request: Request):
        pks = request.query_params.get("pks", "").split(",")
        if not pks or pks == ['']: return Response(content="Выберите объекты", status_code=400)
        with SessionLocal() as session:
            ids = [int(pk) for pk in pks]
            properties = session.query(Property).filter(Property.id.in_(ids)).all()
            xml_content = generate_avito_feed(properties)
        return Response(content=xml_content, media_type="application/xml", headers={"Content-Disposition": "attachment; filename=avito_export.xml"})


# --- ПАПКИ ОБЪЕКТОВ (как в облаке) ---
class ObjectFoldersView(BaseView):
    """Список объектов как папок: в каждой папке — фото и документы."""
    name = "Папки объектов"
    identity = "folders"
    icon = "fa-solid fa-folder-tree"

    @expose("/folders", methods=["GET"], identity="folders")
    async def index(self, request: Request):
        with SessionLocal() as session:
            properties = (
                session.query(Property)
                .options(
                    selectinload(Property.images),
                    selectinload(Property.documents),
                )
                .order_by(Property.title)
                .all()
            )
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/folders.html",
            {
                "properties": properties,
                "request": request,
            },
        )
