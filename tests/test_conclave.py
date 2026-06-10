"""Характеризующие тесты Conclave — парсинг оценки critic и защиты цикла QA
(ранний выход при PASS_SCORE, fallback при ошибках, should_stop).

_call и _load_config подменяются, реальные API/конфиги не трогаем.
"""

import pytest

from core import conclave
from core.conclave import Conclave, _parse_score, _extract_python


class TestExtractPython:
    def test_fence(self):
        assert _extract_python("текст\n```python\nx = 1\n```\nещё") == "x = 1"

    def test_bare_code(self):
        assert _extract_python("def f():\n    return 1") == "def f():\n    return 1"

    def test_prose_is_none(self):
        assert _extract_python("просто текст без кода") is None


class TestMachineCheck:
    """Кодовая ветка Конклава проверяется машиной, а не только critic'ом."""

    def test_non_coder_returns_none(self):
        assert Conclave()._machine_check("def f(): pass", "scout") is None

    def test_non_code_returns_none(self):
        assert Conclave()._machine_check("обычный текстовый ответ", "coder") is None

    def test_syntax_error_is_hard_fail(self):
        r = Conclave()._machine_check("```python\ndef f(\n```", "coder")
        assert r is not None and r["hard_fail"] and "СИНТАКСИС" in r["note"]

    def test_valid_syntax_not_hard_fail(self, monkeypatch):
        import tools.shell_tools
        monkeypatch.setattr(tools.shell_tools, "run_python",
                            lambda code, uid: {"ok": True, "stdout": ""})
        r = Conclave()._machine_check("```python\nx = 1\n```", "coder")
        assert r is not None and not r["hard_fail"] and "синтаксис валиден" in r["note"]

    def test_run_failure_noted_not_hard_fail(self, monkeypatch):
        import tools.shell_tools
        monkeypatch.setattr(tools.shell_tools, "run_python",
                            lambda code, uid: {"ok": False, "stderr": "NameError: x"})
        r = Conclave()._machine_check("```python\nprint(undefined_var)\n```", "coder")
        # прогон упал, но это не auto-reject (код мог требовать вход) — критик взвесит
        assert r is not None and not r["hard_fail"] and "ПРОГОН УПАЛ" in r["note"]


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
    ("нашёл 3 проблемы, ставлю 8", 8),  # fallback: ПОСЛЕДНЕЕ число, не первое
    ("сначала 2, потом стало лучше — 9", 9),
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
