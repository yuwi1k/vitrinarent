import os
from typing import Optional, Dict, Any

import httpx


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
        # По умолчанию используется публичный хост API Авито; при необходимости можно переопределить
        self.base_url = (os.getenv("AVITO_API_BASE_URL") or "https://api.avito.ru").rstrip("/")
        # Полный URL метода запуска выгрузки по настроенному фиду, из Autoload API:
        # https://api.avito.ru/autoload/v1/upload
        self.upload_url = (os.getenv("AVITO_AUTOLOAD_UPLOAD_URL") or "").strip()

    def _validate_config(self) -> Optional[str]:
        if not self.client_id or not self.client_secret:
            return "Не заданы AVITO_API_CLIENT_ID / AVITO_API_CLIENT_SECRET в окружении."
        if not self.upload_url:
            return "Не задан AVITO_AUTOLOAD_UPLOAD_URL (полный URL метода загрузки фида Авито Autoload API)."
        return None

    async def _get_access_token(self, scope: Optional[str] = None) -> str:
        """
        Получение access_token по client_credentials.
        Официальный токен-эндпоинт Авито: POST {base_url}/token
        scope: опционально, для доступа к отчётам автозагрузки можно передать "autoload:reports".
        """
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
        return token

    async def upload_feed(self) -> Dict[str, Any]:
        """
        Запуск автозагрузки через метод /autoload/v1/upload.

        Внимание: Autoload API не принимает сам XML-файл в теле этого запроса.
        Файл берётся по ссылке, указанной в настройках автозагрузки в профиле Авито
        (upload_url / feeds_data). Здесь мы только даём команду «запустить выгрузку».
        """
        config_error = self._validate_config()
        if config_error:
            raise RuntimeError(config_error)

        token = await self._get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.upload_url, headers=headers)

        status = resp.status_code
        try:
            payload: Any = resp.json()
        except Exception:
            payload = {"raw": resp.text}

        if status >= 400:
            raise RuntimeError(f"Ошибка Autoload API (HTTP {status}): {payload}")

        return {"status_code": status, "response": payload}

    def _auth_error_detail(self, response: httpx.Response) -> str:
        """Текст ошибки с телом ответа для отладки 401/403."""
        try:
            body = response.json()
            return f"HTTP {response.status_code}: {body}"
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:500]}"

    async def get_last_completed_report_items(self) -> Dict[str, Any]:
        """
        Получает данные по объявлениям из последнего завершённого отчёта автозагрузки.
        Использует:
        - GET /autoload/v3/reports/last_completed_report
        - GET /autoload/v2/reports/{report_id}/items
        """
        # Токен с scope для доступа к отчётам (см. swagger Autoload API)
        token = await self._get_access_token(scope="autoload:reports")
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Последний завершённый отчёт
            last_url = f"{self.base_url}/autoload/v3/reports/last_completed_report"
            r_last = await client.get(last_url, headers=headers)
            if r_last.status_code == 401:
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

            # Все объявления из отчёта, с пагинацией
            page = 0
            per_page = 200
            items: list[dict[str, Any]] = []
            while True:
                items_url = f"{self.base_url}/autoload/v2/reports/{report_id}/items"
                params = {"page": page, "per_page": per_page}
                r_items = await client.get(items_url, headers=headers, params=params)
                r_items.raise_for_status()
                data = r_items.json()
                batch = data.get("items") or []
                meta = data.get("meta") or {}
                items.extend(batch)
                pages = int(meta.get("pages") or 0)
                if page + 1 >= pages:
                    break
                page += 1

        return {"report_id": report_id, "items": items}

