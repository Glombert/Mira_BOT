"""Регресс: load_persona не должен падать в дефолт из-за reflections.

Баг (найден ритуалом log_audit): БД отдаёт reflection с ключом 'content',
а код читал r['text'] → KeyError → вся персона уходила в _PERSONA_FALLBACK.
"""

import os

os.environ.setdefault("MIRA_ALLOW_UNSANDBOXED", "1")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "t")

import pytest

import agent


@pytest.fixture(autouse=True)
def _isolate_overlay(monkeypatch):
    # не трогаем реальный memory/persona_overlay.json во время теста
    monkeypatch.setattr(agent, "_ensure_persona_overlay_from_base", lambda: None)
    monkeypatch.setattr(agent, "_load_persona_overlay", lambda: {})


def test_content_keyed_reflection_does_not_break_persona(monkeypatch):
    monkeypatch.setattr(agent, "load_reflections",
                        lambda: [{"date": "2026-05-09", "content": "я заметила деталь"}])
    out = agent.load_persona()
    assert out != agent._PERSONA_FALLBACK
    assert "я заметила деталь" in out


def test_legacy_text_key_still_works(monkeypatch):
    monkeypatch.setattr(agent, "load_reflections",
                        lambda: [{"date": "2026-05-01", "text": "старый формат"}])
    out = agent.load_persona()
    assert "старый формат" in out


def test_malformed_reflections_do_not_break_persona(monkeypatch):
    # запись без text/content, пустая, не-dict — персона всё равно грузится
    monkeypatch.setattr(agent, "load_reflections",
                        lambda: [{"date": "x"}, {"content": ""}, "мусор"])
    out = agent.load_persona()
    assert out != agent._PERSONA_FALLBACK
