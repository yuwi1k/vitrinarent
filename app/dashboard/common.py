"""
Общие зависимости и хелперы для роутов дашборда: шаблоны, проверка авторизации, валидация файлов.
"""
import os
from typing import Optional, TYPE_CHECKING

from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOAD_MAX_FILE_SIZE
from app.file_utils import get_street_slug
from app.models import Property

if TYPE_CHECKING:
    from fastapi import UploadFile

# Разрешённые расширения для загрузок
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf"}

templates = Jinja2Templates(directory="templates")


def _validate_upload_file(
    file: Optional["UploadFile"],
    allowed_extensions: set,
    max_size: int,
) -> Optional[str]:
    """Проверка файла. Возвращает None если ок, иначе строку с ошибкой."""
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        return f"Недопустимое расширение. Разрешены: {', '.join(sorted(allowed_extensions))}"
    return None


async def check_admin(request: Request):
    """
    Проверяет, что в сессии выставлен флаг is_admin.
    Если нет — редирект на /dashboard/login.
    """
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/dashboard/login"})


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
