"""
Общая логика работы с файлами: пути папок объектов, ресайз изображений, нормализация URL.
Используется в dashboard и admin_views.
"""
import asyncio
import io
import os
import re
from typing import Optional, Tuple, Union

from PIL import Image

IMAGE_MAX_WIDTH = 1600
IMAGE_JPEG_QUALITY = 85

# Подпапки внутри папки объекта (единый формат для дашборда и SQLAdmin)
IMAGES_SUBFOLDER = "Фото"
DOCUMENTS_SUBFOLDER = "Документы"


def folder_slug_from_title(title: Optional[str], property_id: int) -> str:
    if not title or not str(title).strip():
        return str(property_id)
    slug = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip()[:50] or str(property_id)
    return slug


def get_upload_dirs(property_id: int, title: Optional[str] = None) -> Tuple[str, str]:
    """Папка формата ID_Название_объекта, внутри строго «Фото» и «Документы»."""
    folder_name = f"{property_id}_{folder_slug_from_title(title, property_id)}"
    base = os.path.join("static", "uploads", "properties", folder_name)
    images_dir = os.path.join(base, IMAGES_SUBFOLDER)
    documents_dir = os.path.join(base, DOCUMENTS_SUBFOLDER)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)
    return images_dir, documents_dir


def get_property_folder_name(property_id: int, title: Optional[str] = None) -> str:
    """Имя папки для отображения (например в админке)."""
    slug = folder_slug_from_title(title, property_id)
    return f"{property_id}_{slug}"


def resize_image_sync(
    source: Union[str, bytes],
    dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY,
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


async def resize_image_async(
    source: Union[str, bytes],
    dest_path: str,
    max_width: int = IMAGE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY,
) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: resize_image_sync(source, dest_path, max_width, quality),
    )


def normalize_image_url(file_path: str) -> str:
    path = file_path.replace(os.sep, "/").lstrip("/")
    if not path.startswith("static/"):
        path = "static/" + path.lstrip("/") if path else "static"
    return "/" + path
