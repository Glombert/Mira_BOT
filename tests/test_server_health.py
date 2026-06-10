"""Тесты tools/server_health — снимок здоровья сервера вне run_python-песочницы."""

import os
import time

import pytest

from tools import server_health as sh


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    d = tmp_path / "memory"
    d.mkdir()
    monkeypatch.setattr(sh, "MEMORY_DIR", str(d))
    monkeypatch.setattr(sh, "DB_PATH", str(d / "mira.db"))
    monkeypatch.setattr(sh, "HEARTBEAT_BOT", str(d / ".heartbeat"))
    monkeypatch.setattr(sh, "HEARTBEAT_WEB", str(d / ".heartbeat_web"))
    return d


def test_all_green(memory_dir):
    (memory_dir / "mira.db").write_bytes(b"x" * 2048)
    (memory_dir / ".heartbeat").write_text("ts")
    (memory_dir / ".heartbeat_web").write_text("ts")

    r = sh.server_health()
    assert r["ok"]
    assert r["db"]["ok"] and r["db"]["size_mb"] == 0.0
    assert r["disk"]["ok"]
    assert r["heartbeats"]["bot"]["status"] == "fresh"
    assert r["heartbeats"]["web"]["status"] == "fresh"


def test_missing_db_and_heartbeats(memory_dir):
    r = sh.server_health()
    assert not r["ok"]
    assert not r["db"]["ok"]
    assert r["heartbeats"]["bot"] == {"ok": False, "status": "missing"}
    assert r["heartbeats"]["web"] == {"ok": False, "status": "missing"}


def test_stale_heartbeat(memory_dir):
    (memory_dir / "mira.db").write_bytes(b"x")
    hb = memory_dir / ".heartbeat"
    hb.write_text("ts")
    old = time.time() - sh.HEARTBEAT_MAX_AGE - 60
    os.utime(hb, (old, old))
    (memory_dir / ".heartbeat_web").write_text("ts")

    r = sh.server_health()
    assert not r["ok"]
    assert r["heartbeats"]["bot"]["status"] == "stale"
    assert r["heartbeats"]["bot"]["age_seconds"] >= sh.HEARTBEAT_MAX_AGE
    assert r["heartbeats"]["web"]["ok"]
