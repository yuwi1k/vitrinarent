"""
Клиент публичного API Циан (https://public-api.cian.ru).

Авторизация: Bearer <ACCESS KEY> (ключ запрашивается у import@cian.ru).
Ограничения: не более ~10 запросов в секунду на метод, даты в Europe/Moscow.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.5


class CianApiClient:
    """Клиент для работы с API Циан: отчёты по импорту, список объявлений."""

    def __init__(self) -> None:
        self.access_key = (os.getenv("CIAN_ACCESS_KEY") or "").strip()
        self.base_url = (
            os.getenv("CIAN_API_BASE_URL") or "https://public-api.cian.ru"
        ).rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_key}",
            "Content-Type": "application/json",
        }

    def _validate_config(self) -> Optional[str]:
        if not self.access_key:
            return "Не задан CIAN_ACCESS_KEY в окружении."
        return None

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTP-запрос с retry и exponential backoff для 5xx/429/таймаутов."""
        last_exc: Optional[Exception] = None
        resp: Optional[httpx.Response] = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 30.0)) as client:
                    resp = await getattr(client, method)(url, **kwargs)
                if resp.status_code == 429:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning("CIAN rate limited (429), retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, _MAX_RETRIES)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning("CIAN server error %d, retrying in %.1fs (attempt %d/%d)", resp.status_code, wait, attempt + 1, _MAX_RETRIES)
                    await asyncio.sleep(wait)
                    continue
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning("Network error calling CIAN %s: %s, retrying in %.1fs (attempt %d/%d)", url, exc, wait, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(wait)
        if last_exc:
            raise last_exc
        return resp  # type: ignore[return-value]

    async def get_last_order_info(self) -> Dict[str, Any]:
        """
        GET /v1/get-last-order-info
        """
        err = self._validate_config()
        if err:
            raise RuntimeError(err)
        r = await self._request_with_retry(
            "get",
            f"{self.base_url}/v1/get-last-order-info",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    async def get_order(self) -> Dict[str, Any]:
        """
        GET /v1/get-order
        """
        err = self._validate_config()
        if err:
            raise RuntimeError(err)
        r = await self._request_with_retry(
            "get",
            f"{self.base_url}/v1/get-order",
            headers=self._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    async def get_my_offers(
        self,
        page: int = 1,
        page_size: int = 100,
        statuses: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        GET /v2/get-my-offers
        """
        err = self._validate_config()
        if err:
            raise RuntimeError(err)
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if statuses:
            for s in statuses:
                params.setdefault("statuses", []).append(s)
        if source:
            params["source"] = source
        r = await self._request_with_retry(
            "get",
            f"{self.base_url}/v2/get-my-offers",
            headers=self._headers(),
            params=params,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()
