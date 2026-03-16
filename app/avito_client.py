import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.5


class AvitoAutoloadClient:
    """
    Минималистичный клиент для Autoload API Авито.

    Ожидает, что в окружении заданы:
    - AVITO_API_CLIENT_ID
    - AVITO_API_CLIENT_SECRET
    - AVITO_AUTOLOAD_UPLOAD_URL  — полный URL метода загрузки фида (из документации Autoload API).

    Мы специально не «угадываем» endpoint, а берём его из настроек, чтобы вы могли
    скопировать точный путь из Swagger на `developers.avito.ru`.
    """

    def __init__(self) -> None:
        self.client_id = (os.getenv("AVITO_API_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("AVITO_API_CLIENT_SECRET") or "").strip()
        self.base_url = (os.getenv("AVITO_API_BASE_URL") or "https://api.avito.ru").rstrip("/")
        self.upload_url = (os.getenv("AVITO_AUTOLOAD_UPLOAD_URL") or "").strip()
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    def _validate_config(self) -> Optional[str]:
        if not self.client_id or not self.client_secret:
            return "Не заданы AVITO_API_CLIENT_ID / AVITO_API_CLIENT_SECRET в окружении."
        if not self.upload_url:
            return "Не задан AVITO_AUTOLOAD_UPLOAD_URL (полный URL метода загрузки фида Авито Autoload API)."
        return None

    async def _get_access_token(self, scope: Optional[str] = None) -> str:
        """
        Получение access_token по client_credentials с кешированием по TTL.
        """
        cache_key = scope or "__default__"
        cached = self._token_cache.get(cache_key)
        if cached and cached["expires_at"] > time.monotonic():
            return cached["token"]

        token_url = f"{self.base_url}/token"
        data: Dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if scope:
            data["scope"] = scope
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
            body = resp.json()
        token = body.get("access_token")
        if not token:
            raise RuntimeError("Не удалось получить access_token от Авито (пустой access_token в ответе).")
        expires_in = int(body.get("expires_in", 3600))
        self._token_cache[cache_key] = {
            "token": token,
            "expires_at": time.monotonic() + max(expires_in - 60, 60),
        }
        return token

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTP-запрос с retry и exponential backoff для 5xx/429/таймаутов."""
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 30.0)) as client:
                    resp = await getattr(client, method)(url, **kwargs)
                if resp.status_code == 429:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning("Rate limited (429) by %s, retrying in %.1fs (attempt %d/%d)", url, wait, attempt + 1, _MAX_RETRIES)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning("Server error %d from %s, retrying in %.1fs (attempt %d/%d)", resp.status_code, url, wait, attempt + 1, _MAX_RETRIES)
                    await asyncio.sleep(wait)
                    continue
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning("Network error calling %s: %s, retrying in %.1fs (attempt %d/%d)", url, exc, wait, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(wait)
        if last_exc:
            raise last_exc
        return resp  # type: ignore[possibly-undefined]

    async def upload_feed(self) -> Dict[str, Any]:
        """
        Запуск автозагрузки через метод /autoload/v1/upload.
        """
        config_error = self._validate_config()
        if config_error:
            raise RuntimeError(config_error)

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        resp = await self._request_with_retry("post", self.upload_url, headers=headers, timeout=60.0)

        status = resp.status_code
        try:
            payload: Any = resp.json()
        except Exception:
            logger.warning("Avito API returned non-JSON response (HTTP %s): %s", resp.status_code, resp.text[:500])
            payload = {"raw": resp.text}

        if status >= 400:
            raise RuntimeError(f"Ошибка Autoload API (HTTP {status}): {payload}")

        return {"status_code": status, "response": payload}

    async def get_user_id(self) -> str:
        """GET /core/v1/accounts/self — get current user_id."""
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._request_with_retry("get", f"{self.base_url}/core/v1/accounts/self", headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("id", ""))

    async def get_items_stats(
        self, user_id: str, item_ids: list[int],
        date_from: str = "", date_to: str = "",
    ) -> Dict[str, Any]:
        """POST /stats/v1/accounts/{user_id}/items — statistics for items."""
        from datetime import datetime, timedelta
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        if not date_from:
            date_from = (datetime.now() - timedelta(days=270)).strftime("%Y-%m-%d")
        token = await self._get_access_token(scope="stats:read")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "fields": ["uniqViews", "uniqContacts", "uniqFavorites"],
            "itemIds": item_ids,
            "periodGrouping": "month",
        }
        resp = await self._request_with_retry(
            "post",
            f"{self.base_url}/stats/v1/accounts/{user_id}/items",
            headers=headers, json=body, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_autoload_item_info(self, user_id: str, ad_id: int) -> Dict[str, Any]:
        """GET /autoload/v1/accounts/{user_id}/items/{ad_id}/ — item autoload details and errors."""
        token = await self._get_access_token(scope="autoload:reports")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._request_with_retry(
            "get",
            f"{self.base_url}/autoload/v1/accounts/{user_id}/items/{ad_id}/",
            headers=headers, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_chats(self, user_id: str, unread_only: bool = False) -> Dict[str, Any]:
        """GET /messenger/v2/accounts/{user_id}/chats — list chats."""
        token = await self._get_access_token(scope="messenger:read")
        headers = {"Authorization": f"Bearer {token}"}
        params = {}
        if unread_only:
            params["unread_only"] = "true"
        resp = await self._request_with_retry(
            "get", f"{self.base_url}/messenger/v2/accounts/{user_id}/chats",
            headers=headers, params=params, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_chat_messages(self, user_id: str, chat_id: str) -> Dict[str, Any]:
        """GET /messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/"""
        token = await self._get_access_token(scope="messenger:read")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._request_with_retry(
            "get", f"{self.base_url}/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
            headers=headers, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def send_chat_message(self, user_id: str, chat_id: str, text: str) -> Dict[str, Any]:
        """POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"""
        token = await self._get_access_token(scope="messenger:write")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"message": {"text": text}, "type": "text"}
        resp = await self._request_with_retry(
            "post", f"{self.base_url}/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
            headers=headers, json=body, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    def _auth_error_detail(self, response: httpx.Response) -> str:
        """Текст ошибки с телом ответа для отладки 401/403."""
        try:
            body = response.json()
            return f"HTTP {response.status_code}: {body}"
        except Exception:
            logger.warning("Could not parse Avito error response as JSON", exc_info=True)
            return f"HTTP {response.status_code}: {response.text[:500]}"

    async def apply_vas(self, user_id: str, item_id: int, vas_slug: str) -> Dict[str, Any]:
        """PUT /core/v1/accounts/{user_id}/items/{item_id}/vas — apply VAS package."""
        token = await self._get_access_token(scope="items:apply_vas")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"vas": {"slug": vas_slug}}
        resp = await self._request_with_retry(
            "put", f"{self.base_url}/core/v1/accounts/{user_id}/items/{item_id}/vas",
            headers=headers, json=body, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_vas_packages(self, user_id: str, item_id: int) -> Dict[str, Any]:
        """GET /core/v1/accounts/{user_id}/items/{item_id}/vas — current VAS on item."""
        token = await self._get_access_token(scope="items:apply_vas")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._request_with_retry(
            "get", f"{self.base_url}/core/v1/accounts/{user_id}/items/{item_id}/vas",
            headers=headers, timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_last_completed_report_items(self) -> Dict[str, Any]:
        """
        Получает данные по объявлениям из последнего завершённого отчёта автозагрузки.
        """
        token = await self._get_access_token(scope="autoload:reports")
        headers = {"Authorization": f"Bearer {token}"}

        last_url = f"{self.base_url}/autoload/v3/reports/last_completed_report"
        r_last = await self._request_with_retry("get", last_url, headers=headers, timeout=30.0)
        if r_last.status_code == 401:
            self._token_cache.pop("autoload:reports", None)
            raise RuntimeError(
                "Авито вернул 401 Unauthorized. Проверьте AVITO_API_CLIENT_ID и AVITO_API_CLIENT_SECRET, "
                "что ключи выданы для доступа к API Автозагрузки (раздел «Для профессионалов»). "
                f"Ответ API: {self._auth_error_detail(r_last)}"
            )
        if r_last.status_code == 404:
            raise RuntimeError("У Авито ещё нет ни одного завершённого отчёта автозагрузки.")
        r_last.raise_for_status()
        last_data = r_last.json()
        report_id = last_data.get("report_id")
        if not report_id:
            raise RuntimeError("Не удалось получить report_id из last_completed_report.")

        page = 0
        per_page = 200
        max_pages = 50
        items: list[dict[str, Any]] = []
        while True:
            items_url = f"{self.base_url}/autoload/v2/reports/{report_id}/items"
            params = {"page": page, "per_page": per_page}
            r_items = await self._request_with_retry("get", items_url, headers=headers, params=params, timeout=30.0)
            r_items.raise_for_status()
            data = r_items.json()
            batch = data.get("items") or []
            meta = data.get("meta") or {}
            items.extend(batch)
            pages = int(meta.get("pages") or 0)
            if page + 1 >= pages:
                break
            page += 1
            if page >= max_pages:
                logger.warning("Avito report pagination: reached max_pages=%d limit", max_pages)
                break
            await asyncio.sleep(0.12)

        return {"report_id": report_id, "items": items}

