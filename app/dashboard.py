"""
Кастомная панель управления (Dashboard) для менеджеров: FastAPI + Jinja2 + Bootstrap 5.
"""
import asyncio
import io
import os
import re
import shutil
import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slugify import slugify

from app.database import get_db
from app.models import Property, PropertyImage, PropertyDocument

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

PAGE_SIZE = 20
IMAGE_MAX_WIDTH = 1600
IMAGE_JPEG_QUALITY = 85


# --- Зависимость: проверка админа ---
async def check_admin(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


# --- Хелперы для файлов (перенесены из admin_views) ---
def _folder_slug_from_title(title: Optional[str], property_id: int) -> str:
    if not title or not str(title).strip():
        return str(property_id)
    slug = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip()[:50] or str(property_id)
    return slug


def get_upload_dirs(property_id: int, title: Optional[str] = None) -> Tuple[str, str]:
    """Папка формата ID_Название_объекта, внутри строго «Фото» и «Документы»."""
    folder_name = f"{property_id}_{_folder_slug_from_title(title, property_id)}"
    base = os.path.join("static", "uploads", "properties", folder_name)
    images_dir = os.path.join(base, "Фото")
    documents_dir = os.path.join(base, "Документы")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)
    return images_dir, documents_dir


def _resize_image_sync(source: bytes, dest_path: str) -> bool:
    try:
        img = Image.open(io.BytesIO(source))
        img.load()
    except Exception:
        return False
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > IMAGE_MAX_WIDTH:
        ratio = IMAGE_MAX_WIDTH / w
        new_h = max(1, int(h * ratio))
        img = img.resize((IMAGE_MAX_WIDTH, new_h), Image.Resampling.LANCZOS)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        img.save(dest_path, "JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
    except Exception:
        return False
    return True


async def _resize_image_async(source: bytes, dest_path: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _resize_image_sync(source, dest_path))


def normalize_image_url(file_path: str) -> str:
    path = file_path.replace(os.sep, "/").lstrip("/")
    if not path.startswith("static/"):
        path = "static/" + path.lstrip("/") if path else "static"
    return "/" + path


# --- Редирект с /dashboard на список ---
@router.get("", dependencies=[Depends(check_admin)])
async def dashboard_root():
    return RedirectResponse(url="/dashboard/properties", status_code=302)


# --- Список объектов ---
@router.get("/properties", dependencies=[Depends(check_admin)])
async def list_properties(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
):
    if page < 1:
        page = 1
    stmt = (
        select(Property)
        .where(Property.parent_id.is_(None))
        .options(selectinload(Property.images), selectinload(Property.children))
        .order_by(Property.id.desc())
    )
    total_result = await db.execute(select(func.count(Property.id)).where(Property.parent_id.is_(None)))
    total = total_result.scalar() or 0
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    stmt = stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    result = await db.execute(stmt)
    properties = result.scalars().all()
    pages = list(range(1, total_pages + 1))
    return templates.TemplateResponse(
        "dashboard/list.html",
        {
            "request": request,
            "properties": properties,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "pages": pages,
        },
    )


# --- Создание: GET форма ---
@router.get("/properties/new", dependencies=[Depends(check_admin)])
async def new_property_form(request: Request):
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": None, "is_edit": False},
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
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    show_on_main: Optional[str] = Form(None),
    main_page_order: Optional[int] = Form(None),
    parent_id: Optional[int] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
):
    slug_val = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
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

    prop = Property(
        title=title or "",
        slug=slug_val,
        description=description or None,
        price=price,
        area=area,
        address=address or "",
        deal_type=deal_type or "Аренда",
        category=category or "Офис",
        latitude=lat_val,
        longitude=lon_val,
        main_page_order=main_page_order_val,
        parent_id=parent_id,
        main_image=None,
        is_active=is_active_val,
        show_on_main=show_on_main_val,
    )
    db.add(prop)
    await db.flush()

    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title)

    if main_image and main_image.filename:
        data = await main_image.read()
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await _resize_image_async(data, dest)
        if not ok:
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(main_image.filename)[1] or '.jpg'}")
            with open(dest, "wb") as f:
                f.write(data)
        prop.main_image = normalize_image_url(dest)

    for f in extra_images or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await _resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest))
        db.add(img)

    for f in extra_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(await f.read())
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url="/dashboard/properties", status_code=303)


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
    ).where(Property.id == id)
    result = await db.execute(stmt)
    model = result.scalar().one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": model, "is_edit": True},
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
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    main_page_order: Optional[int] = Form(None),
    parent_id: Optional[int] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
    is_active: Optional[str] = Form(None),
    show_on_main: Optional[str] = Form(None),
):
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalar().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")

    slug_val = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
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

    prop.title = title or ""
    prop.slug = slug_val
    prop.description = description or None
    prop.price = price
    prop.area = area
    prop.address = address or ""
    prop.deal_type = deal_type or "Аренда"
    prop.category = category or "Офис"
    prop.latitude = lat_val
    prop.longitude = lon_val
    prop.is_active = is_active_val
    prop.show_on_main = show_on_main_val
    prop.main_page_order = main_page_order_val
    prop.parent_id = parent_id

    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title)

    if main_image and main_image.filename:
        data = await main_image.read()
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await _resize_image_async(data, dest)
        if not ok:
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(main_image.filename)[1] or '.jpg'}")
            with open(dest, "wb") as f:
                f.write(data)
        prop.main_image = normalize_image_url(dest)

    for f in extra_images or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await _resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest))
        db.add(img)

    for f in extra_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(await f.read())
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url="/dashboard/properties", status_code=303)


# --- Удаление объекта ---
@router.post("/properties/delete/{id:int}", dependencies=[Depends(check_admin)])
async def delete_property(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalar().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")
    await db.delete(prop)
    await db.commit()
    return RedirectResponse(url="/dashboard/properties", status_code=303)


# --- Удаление фото галереи (AJAX) ---
@router.delete("/ajax/images/{id:int}", dependencies=[Depends(check_admin)])
async def delete_image_ajax(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PropertyImage).where(PropertyImage.id == id))
    img = result.scalar().one_or_none()
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
    doc = result.scalar().one_or_none()
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
        .where(Property.parent_id.is_(None))
        .order_by(Property.title)
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    return templates.TemplateResponse(
        "dashboard/folders.html",
        {"request": request, "properties": properties},
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
    property_obj = result.scalar().one_or_none()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return templates.TemplateResponse(
        "dashboard/folder_view.html",
        {"request": request, "property_obj": property_obj},
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
    prop = result.scalar().one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")
    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title)

    for f in new_photos or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await _resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest))
        db.add(img)

    for f in new_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(await f.read())
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()
    return RedirectResponse(url=f"/dashboard/folders/{id}", status_code=303)
