"""Характеризующие тесты providers.call — fallback, non-retriable, метрики,
prompt-caching split. Фиксируют текущее поведение перед рефакторингом монолитов.

Реальные API не вызываются: PROVIDERS подменяется фейковыми клиентами с
интерфейсом client.chat.completions.create(**kwargs).
"""

import pytest

import providers


# --- Фейковый OpenAI-совместимый клиент --------------------------------------

class _FakeUsage:
    def __init__(self, prompt=10, completion=5):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion


class _FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResult:
    def __init__(self, content="ok", usage=None, with_choices=True, error=None):
        if with_choices:
            self.choices = [_FakeChoice(content)]
        else:
            self.choices = None
            self.error = error
        if usage is not None:
            self.usage = usage


class _FakeCompletions:
    def __init__(self, result=None, exc=None, recorder=None):
        self._result = result
        self._exc = exc
        self._recorder = recorder

    def create(self, **kwargs):
        if self._recorder is not None:
            self._recorder.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._result


class _FakeClient:
    def __init__(self, result=None, exc=None, recorder=None):
        self.chat = type("C", (), {"completions": _FakeCompletions(result, exc, recorder)})()


@pytest.fixture(autouse=True)
def _no_notify(monkeypatch):
    """Глушим фоновое уведомление о переключении — иначе тест ходит в сеть."""
    monkeypatch.setattr(providers, "_notify_switch", lambda *a, **k: None)


# --- call: базовые контракты -------------------------------------------------

def test_empty_chain_raises():
    with pytest.raises(ValueError):
        providers.call([], [{"role": "user", "content": "x"}])


def test_success_first_provider(isolated_cwd, monkeypatch):
    client = _FakeClient(result=_FakeResult("привет", usage=_FakeUsage()))
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": client})
    chain = [{"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"}]
    r = providers.call(chain, [{"role": "user", "content": "x"}])
    assert r.choices[0].message.content == "привет"


def test_failover_to_second(isolated_cwd, monkeypatch):
    bad = _FakeClient(exc=RuntimeError("upstream 500"))
    rec = []
    good = _FakeClient(result=_FakeResult("спасён"), recorder=rec)
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": bad, "deepseek": good})
    chain = [
        {"provider": "openrouter", "model": "m1"},
        {"provider": "deepseek", "model": "m2"},
    ]
    r = providers.call(chain, [{"role": "user", "content": "x"}])
    assert r.choices[0].message.content == "спасён"
    assert len(rec) == 1  # второй провайдер вызван ровно один раз
    # Переключение записано в decisions.log
    log = (isolated_cwd / "memory" / "decisions.log").read_text(encoding="utf-8")
    assert "provider_switch" in log


def test_non_retriable_raises_without_failover(isolated_cwd, monkeypatch):
    bad = _FakeClient(exc=RuntimeError("context_length_exceeded: too big"))
    rec = []
    good = _FakeClient(result=_FakeResult("не-должно-дойти"), recorder=rec)
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": bad, "deepseek": good})
    chain = [
        {"provider": "openrouter", "model": "m1"},
        {"provider": "deepseek", "model": "m2"},
    ]
    with pytest.raises(Exception):
        providers.call(chain, [{"role": "user", "content": "x"}])
    assert rec == []  # на резерв НЕ переключились


def test_all_exhausted_raises_last_error(isolated_cwd, monkeypatch):
    bad1 = _FakeClient(exc=RuntimeError("boom1"))
    bad2 = _FakeClient(exc=RuntimeError("boom2"))
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": bad1, "deepseek": bad2})
    chain = [
        {"provider": "openrouter", "model": "m1"},
        {"provider": "deepseek", "model": "m2"},
    ]
    with pytest.raises(RuntimeError, match="boom2"):
        providers.call(chain, [{"role": "user", "content": "x"}])


def test_unconfigured_provider_skipped(isolated_cwd, monkeypatch):
    monkeypatch.setattr(providers, "PROVIDERS", {})
    chain = [{"provider": "openrouter", "model": "m1"}]
    with pytest.raises(RuntimeError, match="ни один провайдер"):
        providers.call(chain, [{"role": "user", "content": "x"}])


def test_null_choices_triggers_failover(isolated_cwd, monkeypatch):
    blip = _FakeClient(result=_FakeResult(with_choices=False, error="upstream blip"))
    good = _FakeClient(result=_FakeResult("ок-после-null"))
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": blip, "deepseek": good})
    chain = [
        {"provider": "openrouter", "model": "m1"},
        {"provider": "deepseek", "model": "m2"},
    ]
    r = providers.call(chain, [{"role": "user", "content": "x"}])
    assert r.choices[0].message.content == "ок-после-null"


def test_metric_kwargs_not_forwarded_to_api(isolated_cwd, monkeypatch):
    rec = []
    client = _FakeClient(result=_FakeResult("ok", usage=_FakeUsage()), recorder=rec)
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": client})
    chain = [{"provider": "openrouter", "model": "m1"}]
    providers.call(
        chain, [{"role": "user", "content": "x"}],
        user_id="u1", agent_name="alpha", max_tokens=50,
    )
    sent = rec[0]
    assert "user_id" not in sent
    assert "agent_name" not in sent
    assert sent["max_tokens"] == 50
    assert sent["model"] == "m1"


# --- prompt caching split ----------------------------------------------------

def test_caching_splits_on_dynamic_marker():
    msgs = [
        {"role": "system", "content": f"СТАТИКА{providers.DYNAMIC_MARKER}ДИНАМИКА"},
        {"role": "user", "content": "hi"},
    ]
    out = providers._apply_prompt_caching(msgs, "openrouter", "anthropic/claude-sonnet-4.6")
    blocks = out[0]["content"]
    assert blocks[0]["text"] == "СТАТИКА"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["text"] == "ДИНАМИКА"
    assert "cache_control" not in blocks[1]
    assert out[1] == {"role": "user", "content": "hi"}


def test_caching_without_marker_caches_whole_system():
    msgs = [{"role": "system", "content": "ВСЁ ЦЕЛИКОМ"}]
    out = providers._apply_prompt_caching(msgs, "openrouter", "anthropic/x")
    blocks = out[0]["content"]
    assert blocks[0]["text"] == "ВСЁ ЦЕЛИКОМ"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_caching_noop_for_non_openrouter():
    msgs = [{"role": "system", "content": "S"}]
    assert providers._apply_prompt_caching(msgs, "deepseek", "deepseek-chat") == msgs


def test_caching_noop_for_non_anthropic_model():
    msgs = [{"role": "system", "content": "S"}]
    assert providers._apply_prompt_caching(msgs, "openrouter", "openai/gpt-4") == msgs
