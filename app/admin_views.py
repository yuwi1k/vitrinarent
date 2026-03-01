"""
Админ-панель (SQLAdmin): аутентификация, базовые ModelView для Property/PropertyImage/PropertyDocument, BaseView для папок.
Кастомная панель менеджеров — в app/dashboard.py.
"""
import asyncio
import io
import os
import re
import shutil
import uuid
from typing import Optional, Tuple, Union

from fastapi.responses import RedirectResponse, Response, JSONResponse
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqladmin import BaseView, ModelView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.filters import ForeignKeyFilter
from starlette.requests import Request

from wtforms import FileField
from markupsafe import Markup

from app.database import SessionLocal
from app.models import Property, PropertyImage, PropertyDocument
from app.feed import generate_avito_feed


def _property_folder_name(property_id: int, title: Optional[str] = None) -> str:
    if title is None:
        with SessionLocal() as session:
            prop = session.query(Property).filter(Property.id == property_id).first()
            title = (prop.title if prop else "") or ""
    slug = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip()[:50] or str(property_id)
    return f"{property_id}_{slug}"


def _get_property_upload_dirs(property_id: int) -> Tuple[str, str]:
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


IMAGE_MAX_WIDTH = 1600
IMAGE_JPEG_QUALITY = 85


def _resize_image_sync(
    source: Union[str, bytes], dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH, quality: int = IMAGE_JPEG_QUALITY,
) -> bool:
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
    source: Union[str, bytes], dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH, quality: int = IMAGE_JPEG_QUALITY,
) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: _resize_image_sync(source, dest_path, max_width, quality)
    )


def _normalize_image_url(file_path: str) -> str:
    path = file_path.replace(os.sep, "/").lstrip("/")
    if not path.startswith("static/"):
        path = "static/" + path.lstrip("/") if path else "static"
    return "/" + path


# --- АУТЕНТИФИКАЦИЯ ---
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


# --- АДМИНКИ МОДЕЛЕЙ (БАЗОВЫЕ) ---
class PropertyImageAdmin(ModelView, model=PropertyImage):
    name = "Фото галереи"
    name_plural = "Галерея"
    form_overrides = {"image_url": FileField}
    column_list = [PropertyImage.id, PropertyImage.property, PropertyImage.image_url]
    column_labels = {PropertyImage.property: "Объект (папка)"}
    column_filters = [ForeignKeyFilter(PropertyImage.property_id, Property.title, Property, title="Папка (объект)")]
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


class PropertyDocumentAdmin(ModelView, model=PropertyDocument):
    name = "Документ"
    name_plural = "Документы"
    form_overrides = {"document_url": FileField}
    column_list = [PropertyDocument.id, PropertyDocument.property, PropertyDocument.title]
    column_labels = {PropertyDocument.property: "Объект (папка)"}
    column_filters = [ForeignKeyFilter(PropertyDocument.property_id, Property.title, Property, title="Папка (объект)")]
    column_formatters = {
        PropertyDocument.property: lambda m, a: Markup(
            f'<span title="Папка: {_property_folder_name(m.property_id, getattr(m.property, "title", None))}">'
            f"{(m.property.title if m.property else '') or ('Объект #' + str(m.property_id))}</span>"
        ),
        PropertyDocument.title: lambda m, a: (
            Markup(f'<a href="{m.document_url}" target="_blank" rel="noopener">{(m.title or "Документ")}</a>')
            if (m.document_url and m.document_url.strip()) else Markup(str(m.title or "—"))
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


class PropertyAdmin(ModelView, model=Property):
    name = "Объект"
    name_plural = "Объекты недвижимости"
    icon = "fa-solid fa-building"
    column_list = [
        Property.id, Property.title, Property.deal_type, Property.category,
        Property.price, Property.is_active, Property.show_on_main,
        Property.main_page_order, "children_count_badge",
    ]
    form_columns = [
        "title", "slug", "description", "price", "area", "address", "main_image",
        "is_active", "show_on_main", "main_page_order", "deal_type", "category",
        "latitude", "longitude", "parent_id",
    ]


class ObjectFoldersView(BaseView):
    name = "Папки объектов"
    identity = "folders"
    icon = "fa-solid fa-folder-tree"

    @expose("/folders", methods=["GET"], identity="folders")
    async def index(self, request: Request):
        with SessionLocal() as session:
            properties = session.query(Property).options(
                selectinload(Property.images), selectinload(Property.documents)
            ).order_by(Property.title).all()
        return await self.templates.TemplateResponse(
            request, "sqladmin/folders.html", {"properties": properties, "request": request}
        )
