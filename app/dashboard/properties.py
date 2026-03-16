"""
CRUD объектов недвижимости: список, создание, редактирование, удаление, массовые действия.
"""
import json
import logging
import os
import shutil
import uuid
import types
from typing import Optional, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from slugify import slugify

from app.config import PAGE_SIZE_DASHBOARD, UPLOAD_MAX_FILE_SIZE
from app.database import get_db
from app.indexing import notify_url_changed, notify_url_deleted
from app.dashboard.common import (
    check_admin,
    templates,
    add_flash,
    _validate_upload_file,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    _get_street_slug_for_property,
)
from app.models import Property, PropertyImage, PropertyDocument
from app.file_utils import get_upload_dirs, resize_image_async, normalize_image_url

router = APIRouter()


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


def _form_model_from_params(
    title: str = "",
    slug: str = "",
    description: str = "",
    address: str = "",
    deal_type: str = "Аренда",
    category: str = "Офис",
    price: int = 0,
    area: float = 0.0,
    latitude: Optional[str] = None,
    longitude: Optional[str] = None,
    parent_id: Optional[int] = None,
    avito_data: Optional[dict] = None,
    cian_data: Optional[dict] = None,
    **kwargs: Any,
) -> Any:
    """Объект для повторного отображения формы создания при ошибке валидации."""
    return types.SimpleNamespace(
        id=None,
        title=title or "",
        slug=slug or "",
        description=description or "",
        address=address or "",
        deal_type=deal_type or "Аренда",
        category=category or "Офис",
        price=price or 0,
        area=area or 0.0,
        latitude=latitude,
        longitude=longitude,
        parent_id=parent_id,
        avito_data=avito_data,
        cian_data=cian_data,
        images=[],
        documents=[],
        main_image=None,
        floors_total=kwargs.get("floors_total"),
        floor_number=kwargs.get("floor_number"),
        power_kw=kwargs.get("power_kw"),
        ceiling_height=kwargs.get("ceiling_height"),
        avito_object_type=kwargs.get("avito_object_type"),
        building_type=kwargs.get("building_type"),
        building_class=kwargs.get("building_class"),
        decoration=kwargs.get("decoration"),
        parking_type=kwargs.get("parking_type"),
        entrance_type=kwargs.get("entrance_type"),
        layout_type=kwargs.get("layout_type"),
        heating_type=kwargs.get("heating_type"),
        property_rights=kwargs.get("property_rights"),
        rental_type=kwargs.get("rental_type"),
        parking_spaces=kwargs.get("parking_spaces"),
        distance_from_road=kwargs.get("distance_from_road"),
    )


async def _render_create_form_error(
    request: Request,
    db: AsyncSession,
    err: str,
    title: str = "",
    slug: str = "",
    description: str = "",
    address: str = "",
    deal_type: str = "Аренда",
    category: str = "Офис",
    price: int = 0,
    area: float = 0.0,
    latitude: Optional[str] = None,
    longitude: Optional[str] = None,
    parent_id_val: Optional[int] = None,
    avito_data_val: Optional[dict] = None,
    cian_data_val: Optional[dict] = None,
    floors_total_val: Optional[int] = None,
    floor_number_val: Optional[int] = None,
    power_kw_val: Optional[float] = None,
    ceiling_height_val: Optional[float] = None,
    avito_type_val: Optional[str] = None,
    building_type_val: Optional[str] = None,
    building_class_val: Optional[str] = None,
    decoration_val: Optional[str] = None,
    parking_type_val: Optional[str] = None,
    entrance_type_val: Optional[str] = None,
    layout_type_val: Optional[str] = None,
    heating_type_val: Optional[str] = None,
    property_rights_val: Optional[str] = None,
    rental_type_val: Optional[str] = None,
    parking_spaces_val: Optional[int] = None,
    distance_from_road_val: Optional[str] = None,
):
    parents = await _get_parent_candidates(db)
    form_model = _form_model_from_params(
        title=title, slug=slug, description=description, address=address,
        deal_type=deal_type, category=category, price=price, area=area,
        latitude=latitude, longitude=longitude, parent_id=parent_id_val,
        avito_data=avito_data_val, cian_data=cian_data_val,
        floors_total=floors_total_val, floor_number=floor_number_val,
        power_kw=power_kw_val, ceiling_height=ceiling_height_val,
        avito_object_type=avito_type_val,
        building_type=building_type_val, building_class=building_class_val,
        decoration=decoration_val, parking_type=parking_type_val,
        entrance_type=entrance_type_val, layout_type=layout_type_val,
        heating_type=heating_type_val, property_rights=property_rights_val,
        rental_type=rental_type_val, parking_spaces=parking_spaces_val,
        distance_from_road=distance_from_road_val,
    )
    return templates.TemplateResponse(
        "dashboard/form.html",
        {
            "request": request,
            "model": form_model,
            "form_errors": [err],
            "is_edit": False,
            "is_copy": False,
            "parent_candidates": parents,
        },
        status_code=400,
    )


async def _render_edit_form_error(request: Request, db: AsyncSession, id: int, err: str):
    """Повторный показ формы редактирования с сообщением об ошибке (400)."""
    stmt = select(Property).options(
        selectinload(Property.images),
        selectinload(Property.documents),
        selectinload(Property.parent).selectinload(Property.children),
        selectinload(Property.children),
    ).where(Property.id == id)
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Объект не найден")
    parents = await _get_parent_candidates(db, exclude_id=model.id)
    building = getattr(model, "parent", None) or model
    children_list = list(getattr(building, "children", None) or [])
    building_nav_items = [(building.id, building.title or f"Объект #{building.id}", f"/dashboard/properties/edit/{building.id}")]
    for c in sorted(children_list, key=lambda x: x.id):
        building_nav_items.append((c.id, c.title or f"Объект #{c.id}", f"/dashboard/properties/edit/{c.id}"))
    return templates.TemplateResponse(
        "dashboard/form.html",
        {
            "request": request,
            "model": model,
            "form_errors": [err],
            "is_edit": True,
            "is_copy": False,
            "parent_candidates": parents,
            "building_nav_items": building_nav_items,
        },
        status_code=400,
    )


from fastapi.responses import JSONResponse


if os.getenv("TESTING") == "1":
    @router.post("/properties/_debug_form")
    async def debug_properties_form(request: Request):
        """
        Вспомогательный endpoint только для тестов: возвращает form-данные как JSON,
        чтобы убедиться, какие поля реально приходят с формы.
        """
        form = await request.form()
        data = {}
        for k, v in form.multi_items():
            # UploadFile отображаем как строку с именем файла
            if hasattr(v, "filename"):
                data.setdefault(k, []).append(f"<file:{v.filename}>")
            else:
                data.setdefault(k, []).append(str(v))
        return JSONResponse({"form": data})


@router.get("/properties/api/parent-data/{id:int}", dependencies=[Depends(check_admin)])
async def get_parent_data(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalar_one_or_none()
    if not prop:
        return JSONResponse({"ok": False}, status_code=404)
    return JSONResponse({
        "ok": True,
        "data": {
            "address": prop.address or "",
            "latitude": prop.latitude,
            "longitude": prop.longitude,
            "floors_total": prop.floors_total,
            "building_type": prop.building_type or "",
            "building_class": prop.building_class or "",
            "decoration": prop.decoration or "",
            "parking_type": prop.parking_type or "",
            "entrance_type": prop.entrance_type or "",
            "layout_type": prop.layout_type or "",
            "heating_type": prop.heating_type or "",
            "property_rights": prop.property_rights or "",
            "rental_type": prop.rental_type or "",
            "parking_spaces": prop.parking_spaces,
            "distance_from_road": prop.distance_from_road or "",
        }
    })


@router.get("/properties/new", dependencies=[Depends(check_admin)])
async def new_property_form(request: Request, db: AsyncSession = Depends(get_db)):
    parents = await _get_parent_candidates(db, exclude_id=None)
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": None, "is_edit": False, "is_copy": False, "parent_candidates": parents},
    )


@router.get("/properties/copy/{id:int}", dependencies=[Depends(check_admin)])
async def copy_property_form(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Property).options(
        selectinload(Property.images),
        selectinload(Property.documents),
    ).where(Property.id == id)
    result = await db.execute(stmt)
    source = result.scalars().one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Объект не найден")
    parents = await _get_parent_candidates(db, exclude_id=None)
    return templates.TemplateResponse(
        "dashboard/form.html",
        {"request": request, "model": source, "is_edit": False, "is_copy": True, "parent_candidates": parents},
    )


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
    building_type: Optional[str] = Form(None),
    building_class: Optional[str] = Form(None),
    decoration: Optional[str] = Form(None),
    parking_type: Optional[str] = Form(None),
    entrance_type: Optional[str] = Form(None),
    layout_type: Optional[str] = Form(None),
    heating_type: Optional[str] = Form(None),
    property_rights: Optional[str] = Form(None),
    rental_type: Optional[str] = Form(None),
    parking_spaces: Optional[str] = Form(None),
    distance_from_road: Optional[str] = Form(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    publish_on_avito: Optional[str] = Form(None),
    publish_on_cian: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
    avito_data_json: Optional[str] = Form(None),
    cian_data_json: Optional[str] = Form(None),
    copy_from_id: Optional[str] = Form(None),
):
    copy_from_val: Optional[int] = None
    if copy_from_id and str(copy_from_id).strip():
        try:
            copy_from_val = int(copy_from_id)
        except (TypeError, ValueError):
            copy_from_val = None

    parent_id_val: Optional[int] = None
    if parent_id is not None and str(parent_id).strip() != "":
        try:
            parent_id_val = int(parent_id)
        except (TypeError, ValueError):
            parent_id_val = None

    title = (title or "").strip()[:50]

    slug_val_input = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
    slug_val = await _ensure_unique_slug(db, slug_val_input)

    is_active_val = is_active in ("1", "true", "on", True)
    publish_on_avito_val = publish_on_avito in ("1", "true", "on", True)
    publish_on_cian_val = publish_on_cian in ("1", "true", "on", True)

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

    building_type_val = (building_type or "").strip() or None
    building_class_val = (building_class or "").strip() or None
    decoration_val = (decoration or "").strip() or None
    parking_type_val = (parking_type or "").strip() or None
    entrance_type_val = (entrance_type or "").strip() or None
    layout_type_val = (layout_type or "").strip() or None
    heating_type_val = (heating_type or "").strip() or None
    property_rights_val = (property_rights or "").strip() or None
    rental_type_val = (rental_type or "").strip() or None
    distance_from_road_val = (distance_from_road or "").strip() or None

    parking_spaces_val: Optional[int] = None
    if parking_spaces and parking_spaces.strip():
        try:
            parking_spaces_val = int(parking_spaces.strip())
        except (TypeError, ValueError):
            parking_spaces_val = None

    avito_data_val: Optional[dict[str, Any]] = None
    if avito_data_json and (avito_data_json or "").strip():
        try:
            avito_data_val = json.loads(avito_data_json.strip())
            if not isinstance(avito_data_val, dict):
                avito_data_val = None
        except (json.JSONDecodeError, TypeError):
            avito_data_val = None

    cian_data_val: Optional[dict[str, Any]] = None
    if cian_data_json and (cian_data_json or "").strip():
        try:
            cian_data_val = json.loads(cian_data_json.strip())
            if not isinstance(cian_data_val, dict):
                cian_data_val = None
        except (json.JSONDecodeError, TypeError):
            cian_data_val = None

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
        cian_data=cian_data_val,
        latitude=lat_val,
        longitude=lon_val,
        floors_total=floors_total_val,
        floor_number=floor_number_val,
        power_kw=power_kw_val,
        ceiling_height=ceiling_height_val,
        building_type=building_type_val,
        building_class=building_class_val,
        decoration=decoration_val,
        parking_type=parking_type_val,
        entrance_type=entrance_type_val,
        layout_type=layout_type_val,
        heating_type=heating_type_val,
        property_rights=property_rights_val,
        rental_type=rental_type_val,
        parking_spaces=parking_spaces_val,
        distance_from_road=distance_from_road_val,
        parent_id=parent_id_val,
        main_image=None,
        is_active=is_active_val,
        publish_on_avito=publish_on_avito_val,
        publish_on_cian=publish_on_cian_val,
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

    _form_err_ctx = lambda err: _render_create_form_error(
        request, db, err, title=title, slug=slug_val_input, description=description, address=address,
        deal_type=deal_type, category=category, price=price, area=area, latitude=latitude, longitude=longitude,
        parent_id_val=parent_id_val, avito_data_val=avito_data_val, cian_data_val=cian_data_val,
        floors_total_val=floors_total_val, floor_number_val=floor_number_val, power_kw_val=power_kw_val,
        ceiling_height_val=ceiling_height_val, avito_type_val=avito_type_val,
        building_type_val=building_type_val, building_class_val=building_class_val,
        decoration_val=decoration_val, parking_type_val=parking_type_val,
        entrance_type_val=entrance_type_val, layout_type_val=layout_type_val,
        heating_type_val=heating_type_val, property_rights_val=property_rights_val,
        rental_type_val=rental_type_val, parking_spaces_val=parking_spaces_val,
        distance_from_road_val=distance_from_road_val,
    )
    if main_image and main_image.filename:
        err = _validate_upload_file(main_image, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            return await _form_err_ctx(err)
        data = await main_image.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            return await _form_err_ctx(f"Файл слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
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
            return await _form_err_ctx(err)
        data = await f.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            return await _form_err_ctx(f"Файл «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
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
            return await _form_err_ctx(f"Недопустимое расширение документа. Разрешены: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
        data_doc = await f.read()
        if len(data_doc) > UPLOAD_MAX_FILE_SIZE:
            return await _form_err_ctx(f"Документ «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(data_doc)
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()

    if prop.is_active:
        try:
            await notify_url_changed(prop.slug or str(prop.id))
        except Exception as e:
            logger.warning("Indexing notification failed: %s", e)

    add_flash(request, "Объект создан.", "success")
    return RedirectResponse(url=f"/dashboard/properties/edit/{prop.id}", status_code=303)


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
    for c in sorted(children_list, key=lambda x: x.id):
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
    building_type: Optional[str] = Form(None),
    building_class: Optional[str] = Form(None),
    decoration: Optional[str] = Form(None),
    parking_type: Optional[str] = Form(None),
    entrance_type: Optional[str] = Form(None),
    layout_type: Optional[str] = Form(None),
    heating_type: Optional[str] = Form(None),
    property_rights: Optional[str] = Form(None),
    rental_type: Optional[str] = Form(None),
    parking_spaces: Optional[str] = Form(None),
    distance_from_road: Optional[str] = Form(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    main_image: UploadFile = File(None),
    extra_images: list[UploadFile] = File([]),
    extra_documents: list[UploadFile] = File([]),
    gallery_order: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    publish_on_avito: Optional[str] = Form(None),
    publish_on_cian: Optional[str] = Form(None),
    avito_data_json: Optional[str] = Form(None),
    cian_data_json: Optional[str] = Form(None),
):
    parent_id_val: Optional[int] = None
    if parent_id is not None and str(parent_id).strip() != "":
        try:
            parent_id_val = int(parent_id)
        except (TypeError, ValueError):
            parent_id_val = None

    title = (title or "").strip()[:50]

    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")

    slug_val_input = (slug or "").strip() or slugify(title or "object", allow_unicode=False) or "object"
    slug_val = await _ensure_unique_slug(db, slug_val_input, exclude_id=id)

    is_active_val = is_active in ("1", "true", "on", True)
    publish_on_avito_val = publish_on_avito in ("1", "true", "on", True)
    publish_on_cian_val = publish_on_cian in ("1", "true", "on", True)

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

    building_type_val = (building_type or "").strip() or None
    building_class_val = (building_class or "").strip() or None
    decoration_val = (decoration or "").strip() or None
    parking_type_val = (parking_type or "").strip() or None
    entrance_type_val = (entrance_type or "").strip() or None
    layout_type_val = (layout_type or "").strip() or None
    heating_type_val = (heating_type or "").strip() or None
    property_rights_val = (property_rights or "").strip() or None
    rental_type_val = (rental_type or "").strip() or None
    distance_from_road_val = (distance_from_road or "").strip() or None

    parking_spaces_val: Optional[int] = None
    if parking_spaces and parking_spaces.strip():
        try:
            parking_spaces_val = int(parking_spaces.strip())
        except (TypeError, ValueError):
            parking_spaces_val = None

    avito_data_val: Optional[dict[str, Any]] = None
    if avito_data_json and (avito_data_json or "").strip():
        try:
            avito_data_val = json.loads(avito_data_json.strip())
            if not isinstance(avito_data_val, dict):
                avito_data_val = None
        except (json.JSONDecodeError, TypeError):
            avito_data_val = None

    cian_data_val: Optional[dict[str, Any]] = None
    if cian_data_json and (cian_data_json or "").strip():
        try:
            cian_data_val = json.loads(cian_data_json.strip())
            if not isinstance(cian_data_val, dict):
                cian_data_val = None
        except (json.JSONDecodeError, TypeError):
            cian_data_val = None

    old_price = prop.price

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
    if cian_data_val is not None:
        prop.cian_data = cian_data_val
    prop.latitude = lat_val
    prop.longitude = lon_val
    prop.floors_total = floors_total_val
    prop.floor_number = floor_number_val
    prop.power_kw = power_kw_val
    prop.ceiling_height = ceiling_height_val
    prop.building_type = building_type_val
    prop.building_class = building_class_val
    prop.decoration = decoration_val
    prop.parking_type = parking_type_val
    prop.entrance_type = entrance_type_val
    prop.layout_type = layout_type_val
    prop.heating_type = heating_type_val
    prop.property_rights = property_rights_val
    prop.rental_type = rental_type_val
    prop.parking_spaces = parking_spaces_val
    prop.distance_from_road = distance_from_road_val
    prop.is_active = is_active_val
    prop.publish_on_avito = publish_on_avito_val
    prop.publish_on_cian = publish_on_cian_val
    prop.parent_id = parent_id_val

    street_slug = await _get_street_slug_for_property(db, prop)
    images_dir, documents_dir = get_upload_dirs(prop.id, prop.title, street_slug)

    if main_image and main_image.filename:
        err = _validate_upload_file(main_image, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            return await _render_edit_form_error(request, db, id, err)
        data = await main_image.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            return await _render_edit_form_error(request, db, id, f"Файл слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{os.path.splitext(main_image.filename)[1] or '.jpg'}")
            with open(dest, "wb") as f:
                f.write(data)
        prop.main_image = normalize_image_url(dest)

    new_sort_orders: dict[int, int] = {}
    if gallery_order and gallery_order.strip():
        items = [x.strip() for x in gallery_order.split(",") if x.strip()]
        for pos, item in enumerate(items):
            parts = item.split(":")
            if len(parts) == 2 and parts[0] == "existing":
                try:
                    img_id = int(parts[1])
                    await db.execute(
                        update(PropertyImage)
                        .where(PropertyImage.id == img_id, PropertyImage.property_id == id)
                        .values(sort_order=pos)
                    )
                except (ValueError, TypeError):
                    pass
            elif len(parts) == 2 and parts[0] == "new":
                try:
                    new_sort_orders[int(parts[1])] = pos
                except (ValueError, TypeError):
                    pass

    max_order_r = await db.execute(select(func.max(PropertyImage.sort_order)).where(PropertyImage.property_id == id))
    fallback_order = (max_order_r.scalar() or 0) + 1

    valid_file_idx = 0
    for f in extra_images or []:
        if not f or not f.filename:
            continue
        err = _validate_upload_file(f, ALLOWED_IMAGE_EXTENSIONS, UPLOAD_MAX_FILE_SIZE)
        if err:
            return await _render_edit_form_error(request, db, id, err)
        data = await f.read()
        if len(data) > UPLOAD_MAX_FILE_SIZE:
            return await _render_edit_form_error(request, db, id, f"Файл «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        dest = os.path.join(images_dir, f"{uuid.uuid4()}.jpg")
        ok = await resize_image_async(data, dest)
        if not ok:
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            dest = os.path.join(images_dir, f"{uuid.uuid4()}{ext}")
            with open(dest, "wb") as out:
                out.write(data)
        sort_val = new_sort_orders.get(valid_file_idx, fallback_order)
        fallback_order = max(fallback_order, sort_val + 1)
        img = PropertyImage(property_id=prop.id, image_url=normalize_image_url(dest), sort_order=sort_val)
        valid_file_idx += 1
        db.add(img)

    for f in extra_documents or []:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1] or ""
        if ext.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
            return await _render_edit_form_error(request, db, id, f"Недопустимое расширение документа. Разрешены: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
        data_doc = await f.read()
        if len(data_doc) > UPLOAD_MAX_FILE_SIZE:
            return await _render_edit_form_error(request, db, id, f"Документ «{f.filename}» слишком большой (макс. {UPLOAD_MAX_FILE_SIZE // (1024*1024)} МБ)")
        path = os.path.join(documents_dir, f"{uuid.uuid4()}{ext}")
        with open(path, "wb") as out:
            out.write(data_doc)
        title_doc = os.path.splitext(f.filename)[0] or "Документ"
        doc = PropertyDocument(property_id=prop.id, title=title_doc, document_url=f"/{path.replace(os.sep, '/')}")
        db.add(doc)

    await db.commit()

    try:
        await notify_url_changed(prop.slug or str(prop.id))
    except Exception as e:
        logger.warning("Indexing notification failed: %s", e)

    if price and price != old_price and prop.publish_on_avito:
        avito_data = prop.avito_data or {}
        avito_id = avito_data.get("AvitoId") if isinstance(avito_data, dict) else None
        if avito_id:
            try:
                from app.avito_client import AvitoAutoloadClient
                avito_client = AvitoAutoloadClient()
                await avito_client.update_item_price(int(avito_id), price)
                add_flash(request, f"Объект сохранён. Цена обновлена на Авито ({old_price} → {price} ₽).", "success")
            except Exception as exc:
                logger.warning("Avito price update failed for item %s: %s", avito_id, exc)
                add_flash(request, f"Объект сохранён, но не удалось обновить цену на Авито: {exc}", "warning")
            return RedirectResponse(url="/dashboard/properties", status_code=303)

    add_flash(request, "Объект сохранён.", "success")
    return RedirectResponse(url="/dashboard/properties", status_code=303)


@router.get("/properties/bulk-delete-confirm", dependencies=[Depends(check_admin)])
async def bulk_delete_confirm(
    request: Request,
    db: AsyncSession = Depends(get_db),
    ids: Optional[str] = None,
):
    """Страница подтверждения массового удаления: список объектов и форма POST в bulk."""
    if not ids or not ids.strip():
        add_flash(request, "Не выбрано ни одного объекта.", "error")
        return RedirectResponse(url="/dashboard/properties", status_code=303)
    id_list = []
    for part in ids.strip().split(","):
        part = part.strip()
        if not part:
            continue
        try:
            id_list.append(int(part))
        except (TypeError, ValueError):
            continue
    if not id_list:
        add_flash(request, "Некорректный список ID.", "error")
        return RedirectResponse(url="/dashboard/properties", status_code=303)
    # Только корневые объекты
    stmt = select(Property).where(
        Property.id.in_(id_list),
        Property.parent_id.is_(None),
    ).order_by(Property.id.asc())
    result = await db.execute(stmt)
    properties = result.scalars().all()
    if not properties:
        add_flash(request, "Выбранные объекты не найдены или не являются корневыми.", "error")
        return RedirectResponse(url="/dashboard/properties", status_code=303)
    return templates.TemplateResponse(
        "dashboard/bulk_delete_confirm.html",
        {
            "request": request,
            "properties": properties,
        },
    )


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
    if not id_list or action not in ("activate", "deactivate", "delete"):
        return RedirectResponse(url="/dashboard/properties", status_code=303)
    base_ids = [i for i in id_list]
    base = update(Property).where(Property.id.in_(base_ids))
    if action == "activate":
        await db.execute(base.values(is_active=True))
        await db.commit()
        add_flash(request, f"Опубликовано объектов: {len(base_ids)}.", "success")
    elif action == "deactivate":
        await db.execute(base.values(is_active=False))
        await db.commit()
        add_flash(request, f"Снято с публикации: {len(base_ids)}.", "success")
    elif action == "delete":
        # Удаляем выбранные объекты вместе с дочерними (эквивалент delete_children=1)
        for pid in base_ids:
            try:
                await delete_property(request, pid, db, delete_children="1")
            except HTTPException:
                # Пропускаем, если объект уже удалён или не найден
                continue
        add_flash(request, f"Удалено объектов: {len(base_ids)}.", "success")
    return RedirectResponse(url="/dashboard/properties", status_code=303)


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
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Объект не найден")

    children = list(prop.children or [])
    remove_children = delete_children in ("1", "true", "yes")

    props_to_cleanup: list[Property] = [prop]
    if children and remove_children:
        props_to_cleanup.extend(children)

    folders_to_remove: set[str] = set()
    for p in props_to_cleanup:
        try:
            street_slug = await _get_street_slug_for_property(db, p)
            images_dir, documents_dir = get_upload_dirs(p.id, p.title, street_slug)
            base_dir = os.path.dirname(images_dir)
            folders_to_remove.add(base_dir)
        except Exception:
            continue

    prop_slug_or_id = prop.slug or str(prop.id)

    if children:
        if remove_children:
            for child in children:
                await db.delete(child)
        else:
            for child in children:
                child.parent_id = None

    await db.delete(prop)
    await db.commit()

    try:
        await notify_url_deleted(prop_slug_or_id)
    except Exception as e:
        logger.warning("Indexing notification failed: %s", e)

    for folder in folders_to_remove:
        try:
            if os.path.isdir(folder):
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            continue
    add_flash(request, "Объект удалён.", "success")
    return RedirectResponse(url="/dashboard/properties", status_code=303)


@router.post("/properties/{id:int}/toggle-feed", dependencies=[Depends(check_admin)])
async def toggle_property_feed(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse
    body = await request.json()
    field = body.get("field")
    if field not in ("publish_on_avito", "publish_on_cian"):
        return JSONResponse({"error": "invalid field"}, status_code=400)

    stmt = select(Property).where(Property.id == id)
    result = await db.execute(stmt)
    prop = result.scalar_one_or_none()
    if not prop:
        return JSONResponse({"error": "not found"}, status_code=404)

    new_val = not getattr(prop, field)
    setattr(prop, field, new_val)
    await db.commit()
    return JSONResponse({"id": id, "field": field, "enabled": new_val})
