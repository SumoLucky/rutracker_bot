# tests/test_main.py
import sys
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import app


@pytest.fixture(autouse=True)
def mock_config():
    """Подменяем конфиг для тестов"""
    with patch('main.config', autospec=True) as mock:
        mock.TELEGRAM_TOKEN = "test_token"
        mock.WEBHOOK_URL = "https://test.timeweb.app"
        mock.CHECK_INTERVAL_MINUTES = 1
        mock.RUN_ON_START = True
        mock.DEBUG = False
        mock.DB_PATH = tempfile.mktemp(suffix='.db')
        yield mock


@pytest.fixture
def client():
    """Тестовый клиент FastAPI"""
    with TestClient(app) as client:
        yield client


def test_endpoints(client):
    """Проверка базовых эндпоинтов"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Rutracker Bot is running", "status": "ok"}

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response = client.post("/webhook", json={"update_id": 123})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_setup(mock_config):
    """Проверяем, что webhook устанавливается, если задан WEBHOOK_URL"""
    # Создаём асинхронный мок для приложения
    mock_app = AsyncMock()
    mock_app.bot.set_webhook = AsyncMock()

    # Создаём builder, который вернёт mock_app
    mock_builder = MagicMock()
    mock_builder.token.return_value.connect_timeout.return_value.read_timeout.return_value.build.return_value = mock_app

    with patch('main.Application.builder', return_value=mock_builder):
        with patch('main.BackgroundScheduler') as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler

            # Запускаем lifespan
            async with app.router.lifespan_context(app):
                # Проверяем вызов set_webhook
                mock_app.bot.set_webhook.assert_awaited_once_with("https://test.timeweb.app/webhook")


@pytest.mark.asyncio
async def test_webhook_skip_if_empty(mock_config):
    """Если WEBHOOK_URL пустой, set_webhook не вызывается"""
    mock_config.WEBHOOK_URL = ""

    mock_app = AsyncMock()
    mock_app.bot.set_webhook = AsyncMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value.connect_timeout.return_value.read_timeout.return_value.build.return_value = mock_app

    with patch('main.Application.builder', return_value=mock_builder):
        with patch('main.BackgroundScheduler') as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler

            async with app.router.lifespan_context(app):
                mock_app.bot.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_started(mock_config):
    """Проверяем, что планировщик запускается с правильным интервалом"""
    mock_app = AsyncMock()
    mock_app.bot.set_webhook = AsyncMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value.connect_timeout.return_value.read_timeout.return_value.build.return_value = mock_app

    mock_scheduler = MagicMock()
    with patch('main.Application.builder', return_value=mock_builder):
        with patch('main.BackgroundScheduler') as mock_scheduler_cls:
            mock_scheduler_cls.return_value = mock_scheduler

            async with app.router.lifespan_context(app):
                mock_scheduler.add_job.assert_called_once()
                args, kwargs = mock_scheduler.add_job.call_args
                assert kwargs.get('minutes') == 1  # CHECK_INTERVAL_MINUTES

                next_run = kwargs.get('next_run_time')
                assert next_run is not None
                # Проверяем, что next_run_time примерно сейчас (RUN_ON_START=True)
                assert abs((next_run - datetime.now()).total_seconds()) < 2


def test_main_entrypoint():
    """Проверяем, что main.py содержит запуск uvicorn (без реального выполнения)"""
    # Просто проверяем, что в файле есть вызов uvicorn.run
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
        assert 'uvicorn.run' in content