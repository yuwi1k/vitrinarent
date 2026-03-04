"""
AJAX-обработчики: изменение порядка фото, удаление фото и документов.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dashboard.common import check_admin
from app.models import PropertyImage, PropertyDocument

router = APIRouter()


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


@router.delete("/ajax/images/{id:int}", dependencies=[Depends(check_admin)])
async def delete_image_ajax(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PropertyImage).where(PropertyImage.id == id))
    img = result.scalar_one_or_none()
    if not img:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)
    await db.delete(img)
    await db.commit()
    return JSONResponse({"status": "ok"})


@router.delete("/ajax/documents/{id:int}", dependencies=[Depends(check_admin)])
async def delete_document_ajax(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PropertyDocument).where(PropertyDocument.id == id))
    doc = result.scalar_one_or_none()
    if not doc:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)
    await db.delete(doc)
    await db.commit()
    return JSONResponse({"status": "ok"})
