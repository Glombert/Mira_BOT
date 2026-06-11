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


def test_health_report_green(memory_dir):
    (memory_dir / "mira.db").write_bytes(b"x" * 1024)
    (memory_dir / ".heartbeat").write_text("ts")
    (memory_dir / ".heartbeat_web").write_text("ts")

    report = sh.health_report()
    assert "Всё в порядке" in report
    assert report.rstrip().endswith("#IMPORTANCE: NONE")


def test_health_report_problems(memory_dir):
    report = sh.health_report()
    assert "НЕ НАЙДЕНА" in report
    assert report.rstrip().endswith("#IMPORTANCE: MAJOR")


def test_ritual_handler_registry():
    from tools.rituals import run_handler
    report = run_handler("server_health")
    assert "#IMPORTANCE:" in report


def test_sample_metrics_sane():
    s = sh.sample_metrics()
    assert 0 <= s["mem_percent"] <= 100
    assert 0 <= s["disk_percent"] <= 100
    assert s["load1"] >= 0
    assert s["mem_total_mb"] > 0


def test_metrics_roundtrip(isolated_cwd):
    from tools import db
    db.save_server_metric(0.42, 55, 128, 33)
    pts = db.load_server_metrics(24)
    assert len(pts) == 1
    p = pts[0]
    assert p["load1"] == 0.42 and p["mem_percent"] == 55
    assert p["swap_mb"] == 128 and p["disk_percent"] == 33
    assert db.load_server_metrics(0) == []
