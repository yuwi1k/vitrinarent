"""
Файловый менеджер: список папок (объектов), просмотр папки, загрузка файлов.
"""
import os
import uuid

from fastapi import APIRouter, Request, Depends, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import UPLOAD_MAX_FILE_SIZE
from app.database import get_db
from app.dashboard.common import (
    check_admin,
    templates,
    _validate_upload_file,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    _get_root_property,
    _get_street_slug_for_property,
)
from app.models import Property, PropertyImage, PropertyDocument
from app.file_utils import get_upload_dirs, resize_image_async, normalize_image_url

router = APIRouter()


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
    property_obj = result.scalar_one_or_none()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    root = await _get_root_property(db, property_obj)
    street_display = (root.address or root.title or "").strip() or f"Объект #{root.id}"
    return templates.TemplateResponse(
        "dashboard/folder_view.html",
        {"request": request, "property_obj": property_obj, "street_display": street_display},
    )


@router.post("/folders/{id:int}/upload", dependencies=[Depends(check_admin)])
async def folder_upload(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
    new_photos: list[UploadFile] = File([]),
    new_documents: list[UploadFile] = File([]),
):
    result = await db.execute(select(Property).where(Property.id == id))
    prop = result.scalar_one_or_none()
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
