"""Характеризующие тесты providers.call — fallback, non-retriable, метрики,
prompt-caching split. Фиксируют текущее поведение перед рефакторингом монолитов.

Реальные API не вызываются: PROVIDERS подменяется фейковыми клиентами с
интерфейсом client.chat.completions.create(**kwargs).
"""

import pytest

from core import providers


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


# --- temperature удалён у новых Anthropic-моделей -----------------------------

@pytest.mark.parametrize("model,accepts", [
    ("claude-sonnet-4-6", True),
    ("claude-opus-4-6", True),
    ("claude-opus-4-7", False),
    ("claude-opus-4-8", False),
    ("claude-fable-5", False),
])
def test_anthropic_accepts_temperature(model, accepts):
    assert providers.anthropic_accepts_temperature(model) is accepts


def test_anthropic_native_omits_temperature_on_new_models(monkeypatch):
    captured = {}

    class _FakeAnthropicMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop after capture")

    class _FakeAnthropicClient:
        messages = _FakeAnthropicMessages()

    monkeypatch.setattr(providers, "_anthropic_client", _FakeAnthropicClient())

    with pytest.raises(RuntimeError):
        providers._call_anthropic_native(
            "claude-opus-4-8", [{"role": "user", "content": "hi"}], 0.2, 100)
    assert "temperature" not in captured

    captured.clear()
    with pytest.raises(RuntimeError):
        providers._call_anthropic_native(
            "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.2, 100)
    assert captured["temperature"] == 0.2


# --- стриминг (on_delta) -------------------------------------------------------

class _FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChunkChoice:
    def __init__(self, delta):
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta=None, usage=None):
        self.choices = [_FakeChunkChoice(delta)] if delta else []
        self.usage = usage


class _FakeTCDelta:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": arguments})()


def test_streamed_response_accumulates_text_and_calls_on_delta():
    chunks = [
        _FakeChunk(_FakeDelta(content="При")),
        _FakeChunk(_FakeDelta(content="вет")),
        _FakeChunk(_FakeDelta(content=", мир")),
        _FakeChunk(usage=_FakeUsage(prompt=7, completion=3)),
    ]
    seen = []
    resp = providers._StreamedResponse(iter(chunks), seen.append)
    assert resp.choices[0].message.content == "Привет, мир"
    assert resp.choices[0].message.tool_calls is None
    assert seen == ["При", "Привет", "Привет, мир"]
    assert resp.usage.prompt_tokens == 7


def test_streamed_response_accumulates_tool_calls():
    chunks = [
        _FakeChunk(_FakeDelta(tool_calls=[_FakeTCDelta(0, id="call_1", name="get_weather", arguments='{"ci')])),
        _FakeChunk(_FakeDelta(tool_calls=[_FakeTCDelta(0, arguments='ty": "Хабаровск"}')])),
    ]
    resp = providers._StreamedResponse(iter(chunks), lambda _t: None)
    tcs = resp.choices[0].message.tool_calls
    assert len(tcs) == 1
    assert tcs[0].id == "call_1"
    assert tcs[0].function.name == "get_weather"
    assert tcs[0].function.arguments == '{"city": "Хабаровск"}'


def test_streamed_response_swallows_on_delta_errors():
    def boom(_t):
        raise RuntimeError("ui умер")
    chunks = [_FakeChunk(_FakeDelta(content="ok"))]
    resp = providers._StreamedResponse(iter(chunks), boom)
    assert resp.choices[0].message.content == "ok"
