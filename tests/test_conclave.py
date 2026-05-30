"""Характеризующие тесты Conclave — парсинг оценки critic и защиты цикла QA
(ранний выход при PASS_SCORE, fallback при ошибках, should_stop).

_call и _load_config подменяются, реальные API/конфиги не трогаем.
"""

import pytest

import conclave
from conclave import Conclave, _parse_score


# --- _parse_score ------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("OK: 8", 8),
    ("ok: 9", 9),
    ("SCORE: 6", 6),
    ("score: 3", 3),
    ("Результат отличный, 10 из 10", 10),
    ("так себе, 4", 4),
    ("совсем непонятный ответ без цифр", 5),
    ("OK: 99", 10),   # клампится сверху
    ("OK: 8 а ещё SCORE: 2", 8),  # OK имеет приоритет
])
def test_parse_score(text, expected):
    assert _parse_score(text) == expected


# --- run_with_qa: ранний выход и fallback ------------------------------------

def _make_conclave(monkeypatch, call_fn):
    monkeypatch.setattr(conclave, "_load_config", lambda name: {
        "model_chain": [{"provider": "openrouter", "model": "m"}],
        "system_prompt": "",
        "allowed_tools": [],
    })
    monkeypatch.setattr(conclave, "_call", call_fn)
    return Conclave()


def test_accept_on_high_score_stops_early(monkeypatch):
    calls = {"n": 0}

    def _call(config, messages):
        calls["n"] += 1
        user = messages[-1]["content"]
        if "Оцени результат" in user:
            return "OK: 9"
        return "готовый результат"

    c = _make_conclave(monkeypatch, _call)
    out = c.run_with_qa("задача", executor_name="coder", skip_editor=True)
    assert out == "готовый результат"
    # executor + critic = 2 вызова; цикл не пошёл на вторую итерацию
    assert calls["n"] == 2


def test_critic_error_yields_neutral_score(monkeypatch):
    monkeypatch.setattr(conclave, "_load_config", lambda name: {
        "model_chain": [{"provider": "openrouter", "model": "m"}],
        "system_prompt": "",
    })

    def _boom(config, messages):
        raise RuntimeError("critic down")

    monkeypatch.setattr(conclave, "_call", _boom)
    c = Conclave()
    score, feedback = c._run_critic("задача", "результат")
    assert score == 5


def test_executor_failure_without_progress_returns_error(monkeypatch):
    def _call(config, messages):
        raise RuntimeError("specialist offline")

    c = _make_conclave(monkeypatch, _call)
    out = c.run_with_qa("задача", executor_name="coder", skip_editor=True)
    assert "Ошибка" in out and "coder" in out


def test_should_stop_before_loop_returns_placeholder(monkeypatch):
    def _call(config, messages):
        raise AssertionError("не должно вызываться при should_stop")

    c = _make_conclave(monkeypatch, _call)
    c.should_stop = True
    out = c.run_with_qa("задача", executor_name="coder", skip_editor=True)
    assert out == "[Конклав не смог получить результат]"
