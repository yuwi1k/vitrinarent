"""
Общие зависимости и хелперы для роутов дашборда: шаблоны, проверка авторизации, валидация файлов.
"""
import os
from typing import Optional, TYPE_CHECKING
import secrets

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


def csrf_token(request: "Request") -> str:
    """
    Генерирует / возвращает CSRF‑токен для текущей сессии.
    Используется в шаблонах: {{ csrf_token(request) }}.
    """
    token = request.session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf_token"] = token
    return token


def get_flash(request: "Request") -> list:
    """
    Возвращает список флеш-сообщений из сессии и очищает его.
    Каждый элемент: {"type": "success"|"error"|"info", "message": "..."}.
    """
    messages = request.session.get("flash") or []
    request.session["flash"] = []
    return messages


def add_flash(request: "Request", message: str, type: str = "success") -> None:
    """Добавляет флеш-сообщение (будет показано после редиректа). type: success, error, info."""
    request.session.setdefault("flash", []).append({"type": type, "message": message})


# Делаем csrf_token и get_flash доступными во всех шаблонах.
templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["get_flash"] = get_flash


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
    # Проверяем размер файла (в байтах)
    try:
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
    except Exception:
        size = None
    if size is not None and size > max_size:
        return f"Файл слишком большой. Максимальный размер: {max_size // (1024 * 1024)} МБ"
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
