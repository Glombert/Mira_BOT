"""Тесты для tools/openrouter_tools.py — каталог моделей.

Не лезем в реальный API, мокаем urlopen. Цель — убедиться что фильтр
по подстроке и по capability работают, и что кеш не отдаёт устаревшее.
"""

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from tools import openrouter_tools


_FAKE_CATALOG = {
    "data": [
        {
            "id": "openai/gpt-5-image",
            "name": "OpenAI: GPT-5 Image",
            "context_length": 128000,
            "architecture": {
                "input_modalities":  ["text"],
                "output_modalities": ["image"],
            },
            "pricing": {"prompt": "0.04", "completion": "0.16"},
        },
        {
            "id": "anthropic/claude-sonnet-4.6",
            "name": "Anthropic: Claude Sonnet 4.6",
            "context_length": 200000,
            "architecture": {
                "input_modalities":  ["text", "image"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0.003", "completion": "0.015"},
        },
        {
            "id": "google/gemini-3-pro-image-preview",
            "name": "Google: Gemini 3 Pro Image",
            "context_length": 1000000,
            "architecture": {
                "input_modalities":  ["text", "image"],
                "output_modalities": ["image"],
            },
            "pricing": {"prompt": "0.0", "completion": "0.0"},
        },
    ]
}


@pytest.fixture(autouse=True)
def _reset_cache():
    openrouter_tools._reset_cache()
    yield
    openrouter_tools._reset_cache()


def _fake_urlopen(*args, **kwargs):
    class _R:
        def read(self):
            return json.dumps(_FAKE_CATALOG).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass
    return _R()


def test_returns_all_models_by_default():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models()
    assert result["ok"] is True
    assert result["count"] == 3
    assert result["total_in_catalog"] == 3


def test_filter_by_substring_in_id():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(filter="gemini")
    assert result["count"] == 1
    assert result["models"][0]["id"] == "google/gemini-3-pro-image-preview"


def test_filter_by_substring_in_name():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(filter="anthropic")
    assert result["count"] == 1
    assert "claude" in result["models"][0]["id"].lower()


def test_filter_case_insensitive():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(filter="GPT-5")
    assert result["count"] == 1


def test_capability_image_only():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(capability="image")
    assert result["count"] == 2
    ids = {m["id"] for m in result["models"]}
    assert "openai/gpt-5-image" in ids
    assert "google/gemini-3-pro-image-preview" in ids


def test_capability_text_only():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(capability="text")
    assert result["count"] == 1
    assert result["models"][0]["id"] == "anthropic/claude-sonnet-4.6"


def test_filter_and_capability_combined():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(filter="google", capability="image")
    assert result["count"] == 1
    assert result["models"][0]["id"] == "google/gemini-3-pro-image-preview"


def test_limit_truncates_results():
    with patch("tools.openrouter_tools.urllib.request.urlopen", _fake_urlopen):
        result = openrouter_tools.list_models(limit=2)
    assert result["count"] == 2
    assert result["total_in_catalog"] == 3


def test_network_error_returns_failure():
    def _raise(*args, **kwargs):
        import urllib.error
        raise urllib.error.URLError("no connection")
    with patch("tools.openrouter_tools.urllib.request.urlopen", _raise):
        result = openrouter_tools.list_models()
    assert result["ok"] is False
    assert "OpenRouter" in result["error"]


def test_cache_avoids_second_fetch():
    calls = [0]
    def _counting_urlopen(*args, **kwargs):
        calls[0] += 1
        return _fake_urlopen()
    with patch("tools.openrouter_tools.urllib.request.urlopen", _counting_urlopen):
        openrouter_tools.list_models()
        openrouter_tools.list_models(filter="gpt")
    assert calls[0] == 1, "Кеш должен был отдать второй вызов из памяти"
