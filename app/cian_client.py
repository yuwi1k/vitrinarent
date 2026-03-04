"""
Клиент публичного API Циан (https://public-api.cian.ru).

Авторизация: Bearer <ACCESS KEY> (ключ запрашивается у import@cian.ru).
Ограничения: не более ~10 запросов в секунду на метод, даты в Europe/Moscow.
"""
import os
from typing import Any, Dict, List, Optional

import httpx


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

    async def get_last_order_info(self) -> Dict[str, Any]:
        """
        GET /v1/get-last-order-info
        Состояние последнего отчёта по импорту: URL фида, дата проверки, проблемы и т.д.
        """
        err = self._validate_config()
        if err:
            raise RuntimeError(err)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/get-last-order-info",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def get_order(self) -> Dict[str, Any]:
        """
        GET /v1/get-order
        Последний актуальный отчёт по импорту объявлений (детали по объектам).
        """
        err = self._validate_config()
        if err:
            raise RuntimeError(err)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/get-order",
                headers=self._headers(),
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
        Список объявлений агентства с пагинацией.
        statuses: например ["published", "inactive"]
        source: "manual" | "upload"
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base_url}/v2/get-my-offers",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()
