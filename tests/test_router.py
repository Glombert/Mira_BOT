"""Характеризующие тесты router.classify — классификация задач и безопасные
fallback'и. providers.call подменяется, реальные API не вызываются.
"""

import pytest

from core import providers
from core import router


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


CHAIN = [{"provider": "openrouter", "model": "m1"}]


def _stub(content, recorder=None):
    def _call(chain, messages, **kw):
        if recorder is not None:
            recorder.append((chain, messages, kw))
        return _Resp(content)
    return _call


def test_empty_chain_returns_chat_without_call(monkeypatch):
    called = []
    monkeypatch.setattr(providers, "call", lambda *a, **k: called.append(1))
    assert router.classify("что угодно", []) == "chat"
    assert called == []


@pytest.mark.parametrize("label", ["chat", "files", "code", "search", "image", "complex"])
def test_valid_labels_passthrough(monkeypatch, label):
    monkeypatch.setattr(providers, "call", _stub(label))
    assert router.classify("сообщение", CHAIN) == label


def test_unknown_label_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(providers, "call", _stub("banana"))
    assert router.classify("сообщение", CHAIN) == "chat"


def test_label_with_punctuation_is_cleaned(monkeypatch):
    monkeypatch.setattr(providers, "call", _stub("CODE."))
    assert router.classify("fix bug", CHAIN) == "code"


def test_provider_error_falls_back_to_chat(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(providers, "call", _boom)
    assert router.classify("сообщение", CHAIN) == "chat"


def test_input_truncated_to_400_chars(monkeypatch):
    rec = []
    monkeypatch.setattr(providers, "call", _stub("chat", recorder=rec))
    router.classify("A" * 500 + "ZZZ", CHAIN)
    prompt = rec[0][1][0]["content"]
    assert "ZZZ" not in prompt  # хвост за пределами 400 символов отрезан


def test_temperature_forced_to_zero(monkeypatch):
    rec = []
    monkeypatch.setattr(providers, "call", _stub("chat", recorder=rec))
    router.classify("hi", [{"provider": "openrouter", "model": "m1", "temperature": 0.9}])
    sent_chain = rec[0][0]
    assert all(e["temperature"] == 0.0 for e in sent_chain)
