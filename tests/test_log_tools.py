"""Тесты tools/log_tools.read_logs — дайджест ошибок с группировкой повторов."""

import os

import pytest

from tools import log_tools


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    d.mkdir()
    monkeypatch.setattr(log_tools, "LOGS_DIR", str(d))
    return d


def test_no_logs_returns_note(logs_dir):
    r = log_tools.read_logs()
    assert r["ok"] and r["total_matched"] == 0
    assert "note" in r


def test_groups_recurring_errors(logs_dir):
    # Три одинаковых по сути ошибки (разные id/время) → одна группа count=3
    (logs_dir / "telegram_bot.log").write_text(
        "2026-06-01 10:00:01,123 - MiraBot - ERROR - mirror_to_telegram: user tg_111 failed /a/b\n"
        "2026-06-01 10:05:02,000 - MiraBot - ERROR - mirror_to_telegram: user tg_222 failed /c/d\n"
        "2026-06-01 10:09:03,999 - MiraBot - ERROR - mirror_to_telegram: user tg_333 failed /e/f\n"
        "2026-06-01 11:00:00,000 - MiraBot - INFO - всё хорошо, не ошибка\n",
        encoding="utf-8",
    )
    r = log_tools.read_logs(days=30)
    assert r["total_matched"] == 3
    assert r["unique_groups"] == 1
    assert r["groups"][0]["count"] == 3
    assert "mirror_to_telegram" in r["groups"][0]["sample"]


def test_warnings_excluded_by_default(logs_dir):
    (logs_dir / "web.log").write_text(
        "2026-06-01 10:00:00,000 - MiraWeb - WARNING - что-то подозрительное\n"
        "2026-06-01 10:00:01,000 - MiraWeb - ERROR - настоящая ошибка\n",
        encoding="utf-8",
    )
    assert log_tools.read_logs()["total_matched"] == 1
    assert log_tools.read_logs(include_warnings=True)["total_matched"] == 2


def test_old_files_skipped_by_window(logs_dir):
    f = logs_dir / "telegram_bot.log.2020-01-01"
    f.write_text("2020-01-01 00:00:00,000 - X - ERROR - древняя ошибка\n", encoding="utf-8")
    old = (2020 - 1970) * 365 * 24 * 3600
    os.utime(f, (old, old))
    assert log_tools.read_logs(days=14)["total_matched"] == 0
