"""
Кастомная панель управления (Dashboard) для менеджеров: FastAPI + Jinja2 + Bootstrap 5.
"""
import csv
import io
import json
import os
import shutil
import uuid
from typing import Optional, Any

from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slugify import slugify

from app.config import PAGE_SIZE_DASHBOARD, UPLOAD_MAX_FILE_SIZE
from app.database import get_db
from app.models import Property, PropertyImage, PropertyDocument
from app.file_utils import get_upload_dirs, get_street_slug, resize_image_async, normalize_image_url
from app.admin_password import get_admin_password, set_admin_password
from app.feed import generate_avito_feed_full
from app.avito_client import AvitoAutoloadClient
from app.settings_store import get_settings_for_edit, save_settings

# Разрешённые расширения для загрузок
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf"}

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


def _validate_upload_file(
    file: Optional[UploadFile],
    allowed_extensions: set,
    max_size: int,
) -> Optional[str]:
    """Проверка файла. Возвращает None если ок, иначе строку с ошибкой."""
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        return f"Недопустимое расширение. Разрешены: {', '.join(sorted(allowed_extensions))}"
    # Размер проверим после чтения в обработчике
    return None


# --- Зависимость: проверка админа ---
async def check_admin(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


async def _ensure_unique_slug(db: AsyncSession, slug: str, exclude_id: Optional[int] = None) -> str:
    """Если slug уже занят другим объектом, добавляет суффикс (-copy, -2, -3, …) пока не станет уникальным."""
    if not (slug or "").strip():
        return slug or "object"
    base = (slug or "").strip()
    n = 0
    while True:
        candidate = f"{base}-copy" if n == 1 else (f"{base}-{n}" if n > 1 else base)
        stmt = select(Property.id).where(Property.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(Property.id != exclude_id)
        r = await db.execute(stmt)
        if r.scalar_one_or_none() is None:
            return candidate
        n += 1


async def _get_parent_candidates(db: AsyncSession, exclude_id: Optional[int] = None) -> list:
    """Список объектов без родителя (корневые) для выбора родителя — (id, title)."""
    stmt = select(Property.id, Property.title).where(Property.parent_id.is_(None)).order_by(Property.title.asc().nullslast(), Property.id.asc())
    if exclude_id is not None:
        stmt = stmt.where(Property.id != exclude_id)
    result = await db.execute(stmt)
    rows = result.all()
    return [(r[0], (r[1] or "")) for r in rows]


async def _get_root_property(db: AsyncSession, prop: Property) -> Property:
    """Корневой объект иерархии (здание/улица)."""
    root = prop
    while getattr(root, "parent_id", None):
        parent_r = await db.execute(select(Property).where(Property.id == root.parent_id))
        parent = parent_r.scalar_one_or_none()
        if not parent:
            break
        root = parent
    return root


async def _get_street_slug_for_property(db: AsyncSession, prop: Property) -> str:
    """Слаг папки улицы: по корневому объекту иерархии (адрес или название)."""
    root = await _get_root_property(db, prop)
    return get_street_slug(root.address or root.title, str(root.id))


# --- Выгрузка фида Авито (XML) ---
@router.get("/export/avito", dependencies=[Depends(check_admin)])
async def export_avito_feed(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .where(Property.is_active.is_(True))
        .options(selectinload(Property.images))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_bytes = generate_avito_feed_full(properties)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="avito_feed.xml"'},
    )


@router.get("/export/avito-new", dependencies=[Depends(check_admin)])
async def export_avito_feed_new(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .where(Property.is_active.is_(True))
        .options(selectinload(Property.images))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    all_properties = result.scalars().all()
    properties = []
    for p in all_properties:
        data = getattr(p, "avito_data", None)
        avito_id = ""
        if isinstance(data, dict):
            v = data.get("AvitoId")
            avito_id = str(v).strip() if v is not None else ""
        if not avito_id:
            properties.append(p)
    xml_bytes = generate_avito_feed_full(properties)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="avito_feed_new.xml"'},
    )


@router.get("/export/avito-autoload-new", dependencies=[Depends(check_admin)])
async def export_avito_feed_new_autoload(db: AsyncSession = Depends(get_db)):
    """
    Запускает автозагрузку по настроенному фиду Авито через Autoload API.
    Возвращает JSON с кратким результатом.
    """
    client = AvitoAutoloadClient()
    try:
        result_payload = await client.upload_feed()
        return JSONResponse(
            {
                "ok": True,
                "message": "Автозагрузка через Autoload API Авито запущена.",
                "api_result": result_payload,
            }
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=500,
        )


@router.get("/avito/sync", dependencies=[Depends(check_admin)])
async def avito_sync_autoload_statuses(db: AsyncSession = Depends(get_db)):
    """
    Синхронизирует статусы автозагрузки из последнего завершённого отчёта:
    проставляет AvitoId и статус в avito_data по полю ad_id (наш Property.id в фиде).
    """
    client = AvitoAutoloadClient()
    try:
        payload = await client.get_last_completed_report_items()
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=200,
        )

    items = payload.get("items") or []
    updated = 0
    for item in items:
        ad_id = item.get("ad_id")
        if not ad_id:
            continue
        try:
            prop_id = int(str(ad_id))
        except ValueError:
            continue
        result = await db.execute(select(Property).where(Property.id == prop_id))
        prop = result.scalar_one_or_none()
        if not prop:
            continue
        data = getattr(prop, "avito_data", None) or {}
        if not isinstance(data, dict):
            data = {}
        avito_id = item.get("avito_id")
        if avito_id is not None:
            data["AvitoId"] = str(avito_id)
        section = item.get("section") or {}
        section_slug = section.get("slug")
        if section_slug:
            data["AutoloadSectionSlug"] = section_slug
        avito_status = item.get("avito_status")
        if avito_status:
            data["AvitoStatus"] = avito_status
        prop.avito_data = data
        updated += 1

    await db.commit()
    return JSONResponse(
        {
            "ok": True,
            "updated": updated,
            "total_items": len(items),
        }
    )


# --- Стартовая страница дашборда: счётчики и быстрые действия ---
@router.get("", dependencies=[Depends(check_admin)])
async def dashboard_home(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    total_r = await db.execute(select(func.count(Property.id)))
    total = total_r.scalar() or 0
    active_r = await db.execute(select(func.count(Property.id)).where(Property.is_active.is_(True)))
    active_count = active_r.scalar() or 0
    on_main_r = await db.execute(select(func.count(Property.id)).where(Property.show_on_main.is_(True)))
    on_main_count = on_main_r.scalar() or 0
    rent_r = await db.execute(select(func.count(Property.id)).where(Property.deal_type == "Аренда"))
    rent_count = rent_r.scalar() or 0
    sale_r = await db.execute(select(func.count(Property.id)).where(Property.deal_type == "Продажа"))
    sale_count = sale_r.scalar() or 0
    avito_rows_r = await db.execute(select(Property.avito_data))
    avito_rows = avito_rows_r.scalars().all()
    avito_published = 0
    for data in avito_rows:
        if not data or not isinstance(data, dict):
            continue
        v = data.get("AvitoId")
        if v is not None and str(v).strip():
            avito_published += 1
    avito_not_published = max(0, (total or 0) - avito_published)
    return templates.TemplateResponse(
        "dashboard/home.html",
        {
            "request": request,
            "total": total,
            "active_count": active_count,
            "on_main_count": on_main_count,
            "rent_count": rent_count,
            "sale_count": sale_count,
            "avito_published": avito_published,
            "avito_not_published": avito_not_published,
        },
    )


# --- Список объектов (с фильтром и поиском) ---
@router.get("/properties", dependencies=[Depends(check_admin)])
async def list_properties(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[str] = None,
):
    if page < 1:
        page = 1
    stmt = select(Property).options(
        selectinload(Property.images),
        selectinload(Property.children),
    )
    count_stmt = select(func.count(Property.id))
    stmt = stmt.where(Property.parent_id.is_(None))
    count_stmt = count_stmt.where(Property.parent_id.is_(None))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
        count_stmt = count_stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
    if deal_type and deal_type.strip() and deal_type != "Все":
        stmt = stmt.where(Property.deal_type == deal_type.strip())
        count_stmt = count_stmt.where(Property.deal_type == deal_type.strip())
    if category and category.strip() and category != "Все":
        stmt = stmt.where(Property.category == category.strip())
        count_stmt = count_stmt.where(Property.category == category.strip())
    if is_active is not None and is_active != "" and is_active != "all":
        if is_active in ("1", "true", "yes"):
            stmt = stmt.where(Property.is_active.is_(True))
            count_stmt = count_stmt.where(Property.is_active.is_(True))
        else:
            stmt = stmt.where(Property.is_active.is_(False))
            count_stmt = count_stmt.where(Property.is_active.is_(False))

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    total_pages = max(1, (total + PAGE_SIZE_DASHBOARD - 1) // PAGE_SIZE_DASHBOARD)
    stmt = stmt.order_by(Property.id.desc()).offset((page - 1) * PAGE_SIZE_DASHBOARD).limit(PAGE_SIZE_DASHBOARD)
    result = await db.execute(stmt)
    properties = result.scalars().all()
    pages = list(range(1, total_pages + 1))
    property_groups = [(p, sorted(getattr(p, "children", None) or [], key=lambda c: c.id)) for p in properties]
    return templates.TemplateResponse(
        "dashboard/list.html",
        {
            "request": request,
            "properties": properties,
            "property_groups": property_groups,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "pages": pages,
            "q": q or "",
            "deal_type": deal_type or "Все",
            "category": category or "Все",
            "is_active": is_active if is_active not in (None, "") else "all",
        },
    )


# --- Настройки: смена пароля админа ---
@router.get("/settings/password", dependencies=[Depends(check_admin)])
async def settings_password_form(request: Request):
    return templates.TemplateResponse(
        "dashboard/settings_password.html",
        {"request": request, "error": None, "success": False},
    )


@router.post("/settings/password", dependencies=[Depends(check_admin)])
async def settings_password_change(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
):
    error = None
    if not current_password.strip():
        error = "Введите текущий пароль."
    elif current_password != get_admin_password():
        error = "Текущий пароль неверен."
    elif not new_password.strip():
        error = "Введите новый пароль."
    elif len(new_password) < 6:
        error = "Новый пароль должен быть не короче 6 символов."
    elif new_password != new_password_confirm:
        error = "Повтор нового пароля не совпадает."
    if error:
        return templates.TemplateResponse(
            "dashboard/settings_password.html",
            {"request": request, "error": error, "success": False},
            status_code=400,
        )
    set_admin_password(new_password)
    return templates.TemplateResponse(
        "dashboard/settings_password.html",
        {"request": request, "error": None, "success": True},
    )


# --- Настройки контактов для фида Авито (без правки .env) ---
@router.get("/settings", dependencies=[Depends(check_admin)])
async def settings_form(request: Request):
    settings_data = get_settings_for_edit()
    return templates.TemplateResponse(
        "dashboard/settings.html",
        {"request": request, "settings": settings_data, "error": None, "success": False},
    )


@router.post("/settings", dependencies=[Depends(check_admin)])
async def settings_save(
    request: Request,
    avito_manager_name: str = Form(""),
    avito_contact_phone: str = Form(""),
):
    save_settings(avito_manager_name=avito_manager_name, avito_contact_phone=avito_contact_phone)
    settings_data = get_settings_for_edit()
    return templates.TemplateResponse(
        "dashboard/settings.html",
        {"request": request, "settings": settings_data, "error": None, "success": True},
    )


# --- Экспорт списка объектов в CSV ---
@router.get("/export/csv", dependencies=[Depends(check_admin)])
async def export_properties_csv(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .where(Property.parent_id.is_(None))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id", "title", "slug", "deal_type", "category", "price", "area", "address", "is_active", "show_on_main"])
    for p in properties:
        writer.writerow([
            p.id,
            (p.title or ""),
            (p.slug or ""),
            (p.deal_type or ""),
            (p.category or ""),
            p.price or 0,
            p.area or 0,
            (p.address or ""),
            "да" if p.is_active else "нет",
            "да" if p.show_on_main else "нет",
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="properties.csv"'},
    )


# --- Создание: GET форма ---
@router.get("/properties/new", dependencies=[Depends(check_admin)])
async def new_property_form(request: Request, db: AsyncSession = Depends(get_db)):
    parents = await _get_parent_candidates(db, exclude_id=None)
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": None, "is_edit": False, "is_copy": False, "parent_candidates": parents},
    )


# --- Копирование объекта: форма с предзаполненными данными ---
@router.get("/properties/copy/{id:int}", dependencies=[Depends(check_admin)])
async def copy_property_form(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Property).where(Property.id == id))
    source = result.scalars().one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Объект не найден")
    # При копировании не исключаем источник: копия — новый объект, его можно привязать к оригиналу как к родителю
    parents = await _get_parent_candidates(db, exclude_id=None)
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": source, "is_edit": False, "is_copy": True, "parent_candidates": parents},
    )


# --- Создание: POST ---
@router.post("/properties/new", dependencies=[Depends(check_admin)])
async def create_property(
    request: Request,
    db: AsyncSession = Depends(get_db),
    title: str = Form(""),
    slug: str = Form(""),
    description: str = Form(""),
    price: int = Form(0),
    area: float = Form(0.0),
    address: str = Form(""),
    deal_type: str = Form("Аренда"),
    category: str = Form("Офис"),
    avito_object_type: Optional[str] = Form(None),
    floors_total: Optional[str] = Form(None),
    floor_number: Optional[str] = Form(None),
    power_kw: Optional[str] = Form(None),
    ceiling_height: Optional[str] = Form(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    show_on_main: Optional[str] = Form(None),
    main_page_order: Optional[int] = Form(None),
    parent_id: Optional[str] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
    avito_data_json: Optional[str] = Form(None),
    copy_from_id: Optional[str] = Form(None),
):
    copy_from_val: Optional[int] = None
    if copy_from_id and str(copy_from_id).strip():
        try:
            copy_from_val = int(copy_from_id)
        except (TypeError, ValueError):
            pass
    parent_id_val: Optional[int] = None
    if parent_id is not None and str(parent_id).strip() != "":
        try:
            parent_id_val = int(parent_id)
        except (TypeError, ValueError):
            pass
    slug_val = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
    slug_val = await _ensure_unique_slug(db, slug_val)
    is_active_val = is_active in ("1", "true", "on", True)
    show_on_main_val = show_on_main in ("1", "true", "on", True)
    main_page_order_val = None
    if main_page_order is not None and str(main_page_order).strip() != "":
        try:
            main_page_order_val = int(main_page_order)
        except (TypeError, ValueError):
            pass
    lat_val = float(latitude) if latitude and latitude.strip() else None
    lon_val = float(longitude) if longitude and longitude.strip() else None
    floors_total_val: Optional[int] = None
    if floors_total and floors_total.strip():
        try:
            floors_total_val = int(floors_total.strip())
        except (TypeError, ValueError):
            floors_total_val = None
    floor_number_val: Optional[int] = None
    if floor_number and floor_number.strip():
        try:
            floor_number_val = int(floor_number.strip())
        except (TypeError, ValueError):
            floor_number_val = None
    power_kw_val: Optional[float] = None
    if power_kw and power_kw.strip():
        try:
            power_kw_val = float(power_kw.strip().replace(",", "."))
        except (TypeError, ValueError):
            power_kw_val = None
    ceiling_height_val: Optional[float] = None
    if ceiling_height and ceiling_height.strip():
        try:
            ceiling_height_val = float(ceiling_height.strip().replace(",", "."))
        except (TypeError, ValueError):
            ceiling_height_val = None
    avito_type_val = (avito_object_type or "").strip() or None
    avito_data_val: Optional[dict[str, Any]] = None
    if avito_data_json and (avito_data_json or "").strip():
        try:
            avito_data_val = json.loads(avito_data_json.strip())
            if not isinstance(avito_data_val, dict):
                avito_data_val = None
        except (json.JSONDecodeError, TypeError):
            avito_data_val = None

    prop = Property(
        title=title or "",
        slug=slug_val,
        description=description or None,
        price=price,
        area=area,
        address=address or "",
        deal_type=deal_type or "Аренда",
        category=category or "Офис",
        avito_object_type=avito_type_val,
        avito_data=avito_data_val,
        latitude=lat_val,
        longitude=lon_val,
        floors_total=floors_total_val,
        floor_number=floor_number_val,
        power_kw=power_kw_val,
        ceiling_height=ceiling_height_val,
        main_page_order=main_page_order_val,
        parent_id=parent_id_val,
        main_image=None,
        is_active=is_active_val,
        show_on_main=show_on_main_val,
    )
    db.add(prop)
    await db.flush()

    street_slug = await _get_street_slug_for_property(db, prop)
    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title, street_slug)

    if copy_from_val and (not main_image or not main_image.filename):
        source_result = await db.execute(
            select(Property).options(
                selectinload(Property.images),
                selectinload(Property.documents),
            ).where(Property.id == copy_from_val)
        )
        source_prop = source_result.scalar_one_or_none()
        if source_prop:
            if source_prop.main_image:
                src_path = source_prop.main_image.lstrip("/").replace("/", os.sep)
                if os.path.isfile(src_path):
                    with open(src_path, "rb") as f:
                        data = f.read()
                    dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
                    ok = await resize_image_async(data, dest)
                    if not ok:
                        dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(src_path)[1] or '.jpg'}")
                        with open(dest, "wb") as out:
                            out.write(data)
                    prop.main_image = normalize_image_url(dest)
            for idx, img in enumerate(sorted(source_prop.images or [], key=lambda x: getattr(x, "sort_order", 0))):
                if not getattr(img, "image_url", None):
                    continue
                src_path = img.image_url.lstrip("/").replace("/", os.sep)
                if not os.path.isfile(src_path):
                    continue
                with open(src_path, "rb") as f:
                    data = f.read()
                dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
                ok = await resize_image_async(data, dest)
                if not ok:
                    ext = os.path.splitext(src_path)[1] or ".jpg"
                    dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
                    with open(dest, "wb") as out:
                        out.write(data)
                db.add(PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest), sort_order=idx))
            # Копирование документов
            for doc in source_prop.documents or []:
                if not getattr(doc, "document_url", None):
                    continue
                src_path = doc.document_url.lstrip("/").replace("/", os.sep)
                if not os.path.isfile(src_path):
                    continue
                ext = os.path.splitext(src_path)[1] or ""
                dest_doc = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
                with open(src_path, "rb") as f_in, open(dest_doc, "wb") as f_out:
                    f_out.write(f_in.read())
                new_title = doc.title or "Документ"
                new_url = f"/{dest_doc.replace(os.sep, '/')}"
                db.add(PropertyDocument(property_id=prop.id, title=new_title, document_url=new_url))

    if main_image and main_image.filename:
        err = _validate_upload_file(main_image, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = await main_image.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(main_image.filename)[1] or '.jpg'}")
            with open(dest, "wb") as f:
                f.write(data)
        prop.main_image = normalize_image_url(dest)

    for idx, f in enumerate(extra_images or []):
        if not f or not f.filename:
            continue
        err = _validate_upload_file(f, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = await f.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest), sort_order=idx)
        db.add(img)

    for f in extra_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        if ext.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Недопустимое расширение документа. Разрешены: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
        data_doc = await f.read()
        if len(data_doc) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Документ «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(data_doc)
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url=f"/dashboard/properties/edit/{prop.id}", status_code=303)


# --- Редактирование: GET форма ---
@router.get("/properties/edit/{id:int}", dependencies=[Depends(check_admin)])
async def edit_property_form(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Property).options(
        selectinload(Property.images),
        selectinload(Property.documents),
        selectinload(Property.parent).selectinload(Property.children),
        selectinload(Property.children),
    ).where(Property.id == id)
    result = await db.execute(stmt)
    model = result.scalars().one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Объект не найден")
    parents = await _get_parent_candidates(db, exclude_id=model.id)
    building = getattr(model, "parent", None) or model
    children_list = list(getattr(building, "children", None) or [])
    building_nav_items = [(building.id, building.title or f"Объект #{building.id}", f"/dashboard/properties/edit/{building.id}")]
    for c in sorted(children_list, key=lambda x: (getattr(x, "main_page_order") or 999, x.id)):
        building_nav_items.append((c.id, c.title or f"Объект #{c.id}", f"/dashboard/properties/edit/{c.id}"))
    return templates.TemplateResponse(
        "dashboard/form.html",
        {
            "request": request,
            "model": model,
            "is_edit": True,
            "is_copy": False,
            "parent_candidates": parents,
            "building_nav_items": building_nav_items,
        },
    )


# --- Редактирование: POST ---
@router.post("/properties/edit/{id:int}", dependencies=[Depends(check_admin)])
async def update_property(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
    title: str = Form(""),
    slug: str = Form(""),
    description: str = Form(""),
    price: int = Form(0),
    area: float = Form(0.0),
    address: str = Form(""),
    deal_type: str = Form("Аренда"),
    category: str = Form("Офис"),
    avito_object_type: Optional[str] = Form(None),
    floors_total: Optional[str] = Form(None),
    floor_number: Optional[str] = Form(None),
    power_kw: Optional[str] = Form(None),
    ceiling_height: Optional[str] = Form(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    main_page_order: Optional[int] = Form(None),
    parent_id: Optional[str] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
    is_active: Optional[str] = Form(None),
    show_on_main: Optional[str] = Form(None),
    avito_data_json: Optional[str] = Form(None),
):
    parent_id_val: Optional[int] = None
    if parent_id is not None and str(parent_id).strip() != "":
        try:
            parent_id_val = int(parent_id)
        except (TypeError, ValueError):
            pass
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalars().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")

    slug_val = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
    slug_val = await _ensure_unique_slug(db, slug_val, exclude_id=id)
    is_active_val = is_active in ("1", "true", "on", True)
    show_on_main_val = show_on_main in ("1", "true", "on", True)
    main_page_order_val = None
    if main_page_order is not None and str(main_page_order).strip() != "":
        try:
            main_page_order_val = int(main_page_order)
        except (TypeError, ValueError):
            pass
    lat_val = float(latitude) if latitude and latitude.strip() else None
    lon_val = float(longitude) if longitude and longitude.strip() else None
    floors_total_val: Optional[int] = None
    if floors_total and floors_total.strip():
        try:
            floors_total_val = int(floors_total.strip())
        except (TypeError, ValueError):
            floors_total_val = None
    floor_number_val: Optional[int] = None
    if floor_number and floor_number.strip():
        try:
            floor_number_val = int(floor_number.strip())
        except (TypeError, ValueError):
            floor_number_val = None
    power_kw_val: Optional[float] = None
    if power_kw and power_kw.strip():
        try:
            power_kw_val = float(power_kw.strip().replace(",", "."))
        except (TypeError, ValueError):
            power_kw_val = None
    ceiling_height_val: Optional[float] = None
    if ceiling_height and ceiling_height.strip():
        try:
            ceiling_height_val = float(ceiling_height.strip().replace(",", "."))
        except (TypeError, ValueError):
            ceiling_height_val = None
    avito_type_val = (avito_object_type or "").strip() or None
    avito_data_val: Optional[dict[str, Any]] = None
    if avito_data_json and (avito_data_json or "").strip():
        try:
            avito_data_val = json.loads(avito_data_json.strip())
            if not isinstance(avito_data_val, dict):
                avito_data_val = None
        except (json.JSONDecodeError, TypeError):
            avito_data_val = None

    prop.title = title or ""
    prop.slug = slug_val
    prop.description = description or None
    prop.price = price
    prop.area = area
    prop.address = address or ""
    prop.deal_type = deal_type or "Аренда"
    prop.category = category or "Офис"
    prop.avito_object_type = avito_type_val
    prop.avito_data = avito_data_val
    prop.latitude = lat_val
    prop.longitude = lon_val
    prop.floors_total = floors_total_val
    prop.floor_number = floor_number_val
    prop.power_kw = power_kw_val
    prop.ceiling_height = ceiling_height_val
    prop.is_active = is_active_val
    prop.show_on_main = show_on_main_val
    prop.main_page_order = main_page_order_val
    prop.parent_id = parent_id_val

    street_slug = await _get_street_slug_for_property(db, prop)
    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title, street_slug)

    if main_image and main_image.filename:
        err = _validate_upload_file(main_image, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = await main_image.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(main_image.filename)[1] or '.jpg'}")
            with open(dest, "wb") as f:
                f.write(data)
        prop.main_image = normalize_image_url(dest)

    next_order = 0
    max_order_r = await db.execute(select(func.max(PropertyImage.sort_order)).where(PropertyImage.property_id == id))
    next_order = (max_order_r.scalar() or 0) + 1
    for f in extra_images or []:
        if not f or not f.filename:
            continue
        err = _validate_upload_file(f, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = await f.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest), sort_order=next_order)
        next_order += 1
        db.add(img)

    for f in extra_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        if ext.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Недопустимое расширение документа. Разрешены: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
        data_doc = await f.read()
        if len(data_doc) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Документ «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(data_doc)
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url="/dashboard/properties", status_code=303)


# --- Массовые действия ---
@router.post("/properties/bulk", dependencies=[Depends(check_admin)])
async def bulk_action(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    raw_ids = form.getlist("ids")
    action = (form.get("action") or "").strip()
    id_list = []
    for i in raw_ids:
        try:
            id_list.append(int(i))
        except (TypeError, ValueError):
            pass
    if not id_list or action not in ("activate", "deactivate", "show_on_main", "hide_from_main"):
        return RedirectResponse(url="/dashboard/properties", status_code=303)
    base = update(Property).where(Property.id.in_(id_list), Property.parent_id.is_(None))
    if action == "activate":
        await db.execute(base.values(is_active=True))
    elif action == "deactivate":
        await db.execute(base.values(is_active=False))
    elif action == "show_on_main":
        await db.execute(base.values(show_on_main=True))
    elif action == "hide_from_main":
        await db.execute(base.values(show_on_main=False))
    await db.commit()
    return RedirectResponse(url="/dashboard/properties", status_code=303)


# --- Удаление объекта ---
@router.post("/properties/delete/{id:int}", dependencies=[Depends(check_admin)])
async def delete_property(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
    delete_children: Optional[str] = None,
):
    """delete_children: '1'/'yes'/'true' — удалить и дочерние; '0'/'no' — оставить дочерние (сделать корневыми)."""
    stmt = (
        select(Property)
        .options(
            selectinload(Property.children),
            selectinload(Property.images),
            selectinload(Property.documents),
        )
        .where(Property.id == id)
    )
    result = await db.execute(stmt)
    prop = result.scalars().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")

    children = list(prop.children or [])
    remove_children = delete_children in ("1", "true", "yes")

    # Соберём список объектов, для которых нужно почистить папки файлов
    props_to_cleanup: list[Property] = [prop]
    if children and remove_children:
        props_to_cleanup.extend(children)

    # Запоминаем пути папок до удаления из БД
    folders_to_remove: set[str] = set()
    for p in props_to_cleanup:
        try:
            street_slug = await _get_street_slug_for_property(db, p)
            images_dir, documents_dir = get_upload_dirs(p.id, p.title, street_slug)
            base_dir = os.path.dirname(images_dir)  # общая папка объекта (где Фото/Документы)
            folders_to_remove.add(base_dir)
        except Exception:
            # Не мешаем удалению объекта, даже если что-то пошло не так с файловой системой
            continue

    if children:
        if remove_children:
            for child in children:
                await db.delete(child)
        else:
            for child in children:
                child.parent_id = None

    await db.delete(prop)
    await db.commit()

    # После успешного удаления из БД — чистим папки на диске
    for folder in folders_to_remove:
        try:
            if os.path.isdir(folder):
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            # Тихо игнорируем ошибки файловой системы
            continue
    return RedirectResponse(url="/dashboard/properties", status_code=303)


# --- Изменение порядка фото галереи (AJAX) ---
@router.post("/ajax/images/reorder", dependencies=[Depends(check_admin)])
async def reorder_images_ajax(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        body = await request.json()
        order = body.get("order")
        if not order or not isinstance(order, list):
            return JSONResponse({"status": "error", "message": "Expected { \"order\": [id1, id2, ...] }"}, status_code=400)
        id_list = [int(x) for x in order if isinstance(x, (int, str)) and str(x).isdigit()]
        if not id_list:
            return JSONResponse({"status": "error", "message": "Empty or invalid order"}, status_code=400)
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)
    result = await db.execute(select(PropertyImage).where(PropertyImage.id.in_(id_list)))
    images = result.scalars().all()
    if len(images) != len(id_list):
        return JSONResponse({"status": "error", "message": "Some images not found"}, status_code=400)
    prop_id = images[0].property_id
    if not all(img.property_id == prop_id for img in images):
        return JSONResponse({"status": "error", "message": "Images must belong to the same property"}, status_code=400)
    id_to_order = {img_id: idx for idx, img_id in enumerate(id_list)}
    for img in images:
        img.sort_order = id_to_order[img.id]
    await db.commit()
    return JSONResponse({"status": "ok"})


# --- Удаление фото галереи (AJAX) ---
@router.delete("/ajax/images/{id:int}", dependencies=[Depends(check_admin)])
async def delete_image_ajax(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PropertyImage).where(PropertyImage.id == id))
    img = result.scalars().one_or_none()
    if not img:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)
    await db.delete(img)
    await db.commit()
    return JSONResponse({"status": "ok"})


# --- Удаление документа (AJAX) ---
@router.delete("/ajax/documents/{id:int}", dependencies=[Depends(check_admin)])
async def delete_document_ajax(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PropertyDocument).where(PropertyDocument.id == id))
    doc = result.scalars().one_or_none()
    if not doc:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)
    await db.delete(doc)
    await db.commit()
    return JSONResponse({"status": "ok"})


# --- Файловый менеджер: список папок (объектов) ---
@router.get("/folders", dependencies=[Depends(check_admin)])
async def list_folders(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Property)
        .options(selectinload(Property.children))
        .where(Property.parent_id.is_(None))
        .order_by(Property.title)
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    property_groups = [(p, sorted(getattr(p, "children", None) or [], key=lambda c: c.id)) for p in properties]
    return templates.TemplateResponse(
        "dashboard/folders.html",
        {"request": request, "properties": properties, "property_groups": property_groups},
    )


# --- Файловый менеджер: содержимое папки объекта ---
@router.get("/folders/{id:int}", dependencies=[Depends(check_admin)])
async def folder_view(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Property)
        .options(
            selectinload(Property.images),
            selectinload(Property.documents),
        )
        .where(Property.id == id)
    )
    result = await db.execute(stmt)
    property_obj = result.scalars().one_or_none()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    root = await _get_root_property(db, property_obj)
    street_display = (root.address or root.title or "").strip() or f"Объект #{root.id}"
    return templates.TemplateResponse(
        "dashboard/folder_view.html",
        {"request": request, "property_obj": property_obj, "street_display": street_display},
    )


# --- Загрузка файлов в папку объекта ---
@router.post("/folders/{id:int}/upload", dependencies=[Depends(check_admin)])
async def folder_upload(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
    new_photos: list[UploadFile] = File([]),
    new_documents: list[UploadFile] = File([]),
):
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalars().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")
    street_slug = await _get_street_slug_for_property(db, prop)
    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title, street_slug)

    max_order_r = await db.execute(select(func.max(PropertyImage.sort_order)).where(PropertyImage.property_id == id))
    next_order = (max_order_r.scalar() or 0) + 1
    for f in new_photos or []:
        if not f or not f.filename:
            continue
        err = _validate_upload_file(f, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = await f.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest), sort_order=next_order)
        next_order += 1
        db.add(img)

    for f in new_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        if ext.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Недопустимое расширение документа. Разрешены: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
        data_doc = await f.read()
        if len(data_doc) > UPLOAD_MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Документ «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(data_doc)
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url=f"/dashboard/folders/{id}", status_code=303)
