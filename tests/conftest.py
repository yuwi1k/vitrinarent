"""Pytest fixtures: клиент приложения для тестов."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Синхронный тестовый клиент (сессия и БД — реальные, если подняты)."""
    return TestClient(app)
