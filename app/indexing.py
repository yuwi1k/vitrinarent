"""
Search engine indexing notifications: IndexNow (Yandex, Bing) + Google Indexing API.

IndexNow — мгновенное уведомление Яндекса и Bing об изменённых URL.
Google Indexing API — уведомление Google (требует service account).

Все вызовы fire-and-forget: ошибки логируются, но не прерывают работу.
"""
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

INDEXNOW_KEY: str = os.getenv("INDEXNOW_KEY", "")

INDEXNOW_ENDPOINTS = [
    "https://yandex.com/indexnow",
    "https://www.bing.com/indexnow",
]

_google_credentials = None
_GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")


def _get_google_credentials():
    """Lazy-load Google service account credentials."""
    global _google_credentials
    if _google_credentials is not None:
        return _google_credentials

    sa_file = _GOOGLE_SERVICE_ACCOUNT_FILE
    if not sa_file or not os.path.isfile(sa_file):
        return None

    try:
        from google.oauth2 import service_account
        scopes = ["https://www.googleapis.com/auth/indexing"]
        _google_credentials = service_account.Credentials.from_service_account_file(
            sa_file, scopes=scopes
        )
        logger.info("Google Indexing API credentials loaded from %s", sa_file)
        return _google_credentials
    except Exception as e:
        logger.warning("Failed to load Google credentials: %s", e)
        return None


def _get_all_site_urls(slug_or_id: str) -> list[str]:
    """Build full URLs for a property across all configured site domains."""
    urls: list[str] = []
    vitrina_domains = os.getenv("SITE_DOMAINS_VITRINA", "").strip()
    diapazon_domains = os.getenv("SITE_DOMAINS_DIAPAZON", "").strip()

    for raw in (vitrina_domains, diapazon_domains):
        for domain in raw.split(","):
            domain = domain.strip()
            if domain:
                urls.append(f"https://{domain}/property/{slug_or_id}")

    return urls


def _get_all_sitemap_urls() -> list[str]:
    """Build sitemap URLs for all configured domains."""
    urls: list[str] = []
    for env_key in ("SITE_DOMAINS_VITRINA", "SITE_DOMAINS_DIAPAZON"):
        for domain in os.getenv(env_key, "").strip().split(","):
            domain = domain.strip()
            if domain:
                urls.append(f"https://{domain}/sitemap.xml")
    return urls


async def notify_indexnow(urls: list[str]):
    """Send IndexNow batch notification to Yandex and Bing."""
    if not INDEXNOW_KEY or not urls:
        return

    host = os.getenv("SITE_DOMAINS_VITRINA", "").split(",")[0].strip()
    if not host:
        host = os.getenv("SITE_DOMAINS_DIAPAZON", "").split(",")[0].strip()
    if not host:
        logger.warning("IndexNow: no host domain configured, skipping")
        return

    payload = {
        "host": host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{host}/{INDEXNOW_KEY}.txt",
        "urlList": urls[:10000],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in INDEXNOW_ENDPOINTS:
            try:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                logger.info(
                    "IndexNow %s → %s (%d URLs)",
                    endpoint, resp.status_code, len(urls),
                )
            except Exception as e:
                logger.warning("IndexNow %s failed: %s", endpoint, e)


async def notify_google_indexing(urls: list[str], action: str = "URL_UPDATED"):
    """
    Notify Google Indexing API about URL changes.
    action: 'URL_UPDATED' or 'URL_DELETED'
    Requires GOOGLE_SERVICE_ACCOUNT_FILE env var pointing to a service account JSON.
    """
    creds = _get_google_credentials()
    if creds is None:
        return

    try:
        from google.auth.transport.requests import Request as AuthRequest
        if creds.expired or not creds.token:
            creds.refresh(AuthRequest())
    except Exception as e:
        logger.warning("Google Indexing API: failed to refresh token: %s", e)
        return

    api_url = "https://indexing.googleapis.com/v3/urlNotifications:publish"
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in urls:
            try:
                resp = await client.post(
                    api_url,
                    json={"url": url, "type": action},
                    headers=headers,
                )
                logger.info("Google Indexing %s → %s (%s)", url, resp.status_code, action)
            except Exception as e:
                logger.warning("Google Indexing %s failed: %s", url, e)


async def notify_url_changed(slug_or_id: str):
    """Notify all search engines about a new/updated property page."""
    urls = _get_all_site_urls(slug_or_id)
    if not urls:
        return

    try:
        await notify_indexnow(urls)
    except Exception as e:
        logger.warning("IndexNow notification failed: %s", e)

    try:
        await notify_google_indexing(urls, "URL_UPDATED")
    except Exception as e:
        logger.warning("Google Indexing notification failed: %s", e)


async def notify_url_deleted(slug_or_id: str):
    """Notify all search engines about a deleted property page."""
    urls = _get_all_site_urls(slug_or_id)
    if not urls:
        return

    try:
        await notify_indexnow(urls)
    except Exception as e:
        logger.warning("IndexNow notification failed: %s", e)

    try:
        await notify_google_indexing(urls, "URL_DELETED")
    except Exception as e:
        logger.warning("Google Indexing notification failed: %s", e)
