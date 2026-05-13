"""Общие fixtures для тестов.

Не загружаем .env: тесты должны быть полностью изолированы. Ставим минимальный
набор env vars. chdir на tmp_path делает только fixture isolated_cwd, потому
что некоторые модули агента при импорте читают persona.json и profiles/ из cwd.
"""

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Фейковые секреты для всех тестов. Без chdir."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token_1234567890")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "0")


@pytest.fixture
def isolated_cwd(monkeypatch, tmp_path):
    """Тесты, работающие с относительными путями (memory/, workspace/),
    запрашивают этот fixture явно."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "memory").mkdir()
    (tmp_path / "workspace").mkdir()
    return tmp_path
