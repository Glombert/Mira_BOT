"""Тест: providers.call ограничивает число одновременных LLM-вызовов семафором."""

import threading
import time

import pytest

import providers


class _SlowClient:
    """Фейковый провайдер: каждый вызов держится ~latency секунд."""

    def __init__(self, counters, latency=0.1):
        self._counters = counters
        self._latency = latency
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kwargs):
        c = self._counters
        with c["lock"]:
            c["active"] += 1
            c["max"] = max(c["max"], c["active"])
        time.sleep(self._latency)
        with c["lock"]:
            c["active"] -= 1
        return type("R", (), {
            "choices": [type("Ch", (), {"message": type("M", (), {"content": "ok", "tool_calls": None})()})()],
            "usage": None,
        })()


def test_semaphore_caps_concurrency(isolated_cwd, monkeypatch):
    counters = {"active": 0, "max": 0, "lock": threading.Lock()}
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": _SlowClient(counters)})
    monkeypatch.setattr(providers, "_notify_switch", lambda *a, **k: None)
    # Жёсткий лимит 2 одновременных
    monkeypatch.setattr(providers, "_llm_semaphore", threading.Semaphore(2))

    chain = [{"provider": "openrouter", "model": "m"}]

    def worker():
        providers.call(chain, [{"role": "user", "content": "x"}])

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counters["max"] <= 2, f"одновременных вызовов было {counters['max']}, ждали ≤2"
    assert counters["max"] >= 2, "лимит не достигнут — тест неинформативен"


def test_call_still_returns_result(isolated_cwd, monkeypatch):
    counters = {"active": 0, "max": 0, "lock": threading.Lock()}
    monkeypatch.setattr(providers, "PROVIDERS", {"openrouter": _SlowClient(counters, latency=0)})
    r = providers.call([{"provider": "openrouter", "model": "m"}], [{"role": "user", "content": "x"}])
    assert r.choices[0].message.content == "ok"
