"""JCat XML feed generator — Avito-compatible format for JCat distribution."""
import logging

from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Property
from app.feed import generate_avito_feed_full

logger = logging.getLogger(__name__)

_STRIP_TAGS = ("AvitoId", "AdStatus", "ListingFee", "ManagerName", "ContactPhone")


async def generate_jcat_feed(db: AsyncSession) -> str:
    """Generate JCat-compatible XML feed (Avito format with minor modifications)."""
    stmt = (
        select(Property)
        .where(Property.is_active == True)
        .options(selectinload(Property.images))
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()

    xml_bytes = generate_avito_feed_full(properties)

    try:
        root = etree.fromstring(xml_bytes)
        for ad in root.findall("Ad"):
            for tag in _STRIP_TAGS:
                el = ad.find(tag)
                if el is not None:
                    ad.remove(el)
    except Exception:
        logger.exception("Failed to post-process JCat feed, using raw Avito XML")
        return xml_bytes.decode("utf-8") if isinstance(xml_bytes, bytes) else xml_bytes

    return etree.tostring(root, encoding="unicode", xml_declaration=True)
