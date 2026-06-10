"""Тесты tools/model_watch — дифф каталога моделей для ритуала agent_versions."""

import json

import pytest

from tools import model_watch as mw


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    path = tmp_path / "model_catalog.json"
    monkeypatch.setattr(mw, "SNAPSHOT_PATH", str(path))
    return path


def _catalog(*ids):
    return [{"id": i, "name": i.split("/")[-1]} for i in ids]


def test_first_run_creates_snapshot(snapshot, monkeypatch):
    monkeypatch.setattr(mw, "_fetch_catalog", lambda: _catalog("anthropic/claude-sonnet-4.6"))
    r = mw.model_catalog_diff()
    assert isinstance(r, str) and "Снимок каталога" in r
    assert r.rstrip().endswith("#IMPORTANCE: NONE")
    assert json.loads(snapshot.read_text()) == {"anthropic/claude-sonnet-4.6": "claude-sonnet-4.6"}


def test_no_diff_no_llm(snapshot, monkeypatch):
    monkeypatch.setattr(mw, "_fetch_catalog", lambda: _catalog("anthropic/claude-sonnet-4.6"))
    mw.model_catalog_diff()
    r = mw.model_catalog_diff()
    assert isinstance(r, str) and "нет" in r
    assert r.rstrip().endswith("#IMPORTANCE: NONE")


def test_diff_goes_to_llm(snapshot, monkeypatch):
    monkeypatch.setattr(mw, "_fetch_catalog", lambda: _catalog("anthropic/claude-sonnet-4.6"))
    mw.model_catalog_diff()
    monkeypatch.setattr(mw, "_fetch_catalog",
                        lambda: _catalog("anthropic/claude-sonnet-4.6", "anthropic/claude-fable-5"))
    r = mw.model_catalog_diff()
    assert isinstance(r, dict)
    assert "claude-fable-5" in r["llm_prompt"]
    assert "#IMPORTANCE" in r["llm_prompt"]
    # снимок обновлён — повторный запуск уже без диффа
    r2 = mw.model_catalog_diff()
    assert isinstance(r2, str)


def test_ignores_other_vendors(snapshot, monkeypatch):
    monkeypatch.setattr(mw, "_fetch_catalog", lambda: _catalog("anthropic/claude-sonnet-4.6"))
    mw.model_catalog_diff()
    monkeypatch.setattr(mw, "_fetch_catalog",
                        lambda: _catalog("anthropic/claude-sonnet-4.6", "somevendor/tiny-model"))
    r = mw.model_catalog_diff()
    assert isinstance(r, str)  # чужой вендор — не повод будить LLM


def test_catalog_unavailable(snapshot, monkeypatch):
    monkeypatch.setattr(mw, "_fetch_catalog", lambda: [])
    r = mw.model_catalog_diff()
    assert "недоступен" in r
    assert r.rstrip().endswith("#IMPORTANCE: MINOR")
