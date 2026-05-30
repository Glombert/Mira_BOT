"""Тесты для providers._apply_prompt_caching — разделение system на
static (кэш) + dynamic (без кэша) по маркеру DYNAMIC_MARKER."""

import pytest
from providers import _apply_prompt_caching, DYNAMIC_MARKER


SYSTEM_STATIC = "Ты Мира. Любопытная, тёплая, прямая."
SYSTEM_DYNAMIC = "Сейчас 12:30 в Хабаровске. Что ты помнишь об этом человеке: ..."


def _make_msgs(system_content: str) -> list:
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "привет"},
    ]


def test_non_anthropic_unchanged():
    msgs = _make_msgs(f"{SYSTEM_STATIC}\n\n{DYNAMIC_MARKER}\n\n{SYSTEM_DYNAMIC}")
    out = _apply_prompt_caching(msgs, "openai", "gpt-4")
    assert out == msgs


def test_anthropic_via_openai_provider_unchanged():
    # openai SDK + anthropic-named model — НЕ openrouter, не кэшируем
    msgs = _make_msgs(SYSTEM_STATIC)
    out = _apply_prompt_caching(msgs, "anthropic", "claude-3-5-sonnet")
    assert out == msgs


def test_openrouter_with_marker_splits_correctly():
    full = f"{SYSTEM_STATIC}\n\n{DYNAMIC_MARKER}\n\n{SYSTEM_DYNAMIC}"
    msgs = _make_msgs(full)
    out = _apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    assert out[0]["role"] == "system"
    blocks = out[0]["content"]
    assert isinstance(blocks, list)
    assert len(blocks) == 2
    # Первый блок — static, с cache_control
    assert blocks[0]["text"] == SYSTEM_STATIC
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    # Второй блок — dynamic, БЕЗ cache_control
    assert blocks[1]["text"] == SYSTEM_DYNAMIC
    assert "cache_control" not in blocks[1]


def test_openrouter_without_marker_caches_all():
    msgs = _make_msgs(SYSTEM_STATIC)
    out = _apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    blocks = out[0]["content"]
    assert len(blocks) == 1
    assert blocks[0]["text"] == SYSTEM_STATIC
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_marker_with_empty_dynamic():
    """Если динамика пустая — только static-блок, без второго пустого."""
    msgs = _make_msgs(f"{SYSTEM_STATIC}\n\n{DYNAMIC_MARKER}\n\n   ")
    out = _apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    blocks = out[0]["content"]
    assert len(blocks) == 1
    assert blocks[0]["text"] == SYSTEM_STATIC


def test_user_message_passes_through():
    msgs = _make_msgs(f"{SYSTEM_STATIC}\n\n{DYNAMIC_MARKER}\n\n{SYSTEM_DYNAMIC}")
    out = _apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    assert out[1] == {"role": "user", "content": "привет"}


def test_non_string_system_skipped():
    """Если system уже список блоков (повторный вызов) — не ломаем."""
    msgs = [
        {"role": "system", "content": [{"type": "text", "text": "x"}]},
        {"role": "user", "content": "y"},
    ]
    out = _apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    assert out == msgs
