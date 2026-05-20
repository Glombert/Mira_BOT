"""Тесты миграции БД: колонка kind в reminders, таблица ritual_runs.

Использует isolated_cwd fixture из conftest.py для временной БД в tmp_path.
"""

import pytest
from tools import db


pytestmark = pytest.mark.usefixtures("isolated_cwd")


class TestRemindersKindColumn:
    def test_kind_column_exists_after_init(self):
        """После init_db колонка kind присутствует."""
        conn = db.get_conn()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)")}
        assert "kind" in cols

    def test_kind_defaults_to_reminder(self):
        """Новые записи без явного kind получают 'reminder'."""
        task = db.add_reminder("tg_test", "2026-12-01T09:00:00", "test")
        conn = db.get_conn()
        row = conn.execute("SELECT kind FROM reminders WHERE id = ?", (task["id"],)).fetchone()
        assert row["kind"] == "reminder"

    def test_kind_task_stored(self):
        task = db.add_reminder("tg_test", "2026-12-01T09:00:00", "do stuff", kind="task")
        conn = db.get_conn()
        row = conn.execute("SELECT kind FROM reminders WHERE id = ?", (task["id"],)).fetchone()
        assert row["kind"] == "task"

    def test_double_init_is_idempotent(self):
        """Повторный init_db не должен падать из-за ALTER TABLE."""
        db.init_db()  # второй вызов
        conn = db.get_conn()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)")}
        assert "kind" in cols


class TestRitualRunsTable:
    def test_table_exists(self):
        conn = db.get_conn()
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "ritual_runs" in tables

    def test_save_and_load(self):
        db.save_ritual_run("self_review", "2026-06-01T09:00:00", "all ok #IMPORTANCE: NONE")
        runs = db.load_ritual_runs()
        assert "self_review" in runs
        assert runs["self_review"]["last_run"] == "2026-06-01T09:00:00"
        assert runs["self_review"]["last_output"] == "all ok #IMPORTANCE: NONE"

    def test_update_existing(self):
        db.save_ritual_run("test_rit", "2026-01-01T00:00:00", "first")
        db.save_ritual_run("test_rit", "2026-06-15T12:00:00", "second")
        runs = db.load_ritual_runs()
        assert runs["test_rit"]["last_run"] == "2026-06-15T12:00:00"
        assert runs["test_rit"]["last_output"] == "second"
