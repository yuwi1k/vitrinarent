"""Pytest fixtures: клиент приложения для тестов."""
import os

import pytest
from fastapi.testclient import TestClient

# До импорта app: включаем NullPool для async БД в тестах (избегаем "another operation is in progress")
os.environ["TESTING"] = "1"

from app.main import app


@pytest.fixture
def client():
    """Синхронный тестовый клиент (сессия и БД — реальные, если подняты)."""
    return TestClient(app)
