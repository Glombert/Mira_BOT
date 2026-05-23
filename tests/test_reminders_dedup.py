"""Тесты дедупликации напоминаний через dedup_key."""

import pytest
from tools import db


pytestmark = pytest.mark.usefixtures("isolated_cwd")


class TestDedupKey:
    def test_dedup_key_stable(self):
        """Одинаковые параметры дают одинаковый ключ."""
        k1 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "💆 massage time")
        k2 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "massage time")
        assert k1 == k2  # эмодзи игнорируются

    def test_dedup_key_case_insensitive(self):
        k1 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "WAKE UP")
        k2 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "wake up")
        assert k1 == k2

    def test_dedup_key_differs_by_user(self):
        k1 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "wake")
        k2 = db._dedup_key("tg_2", "2026-05-25T08:30:00+03:00", "wake")
        assert k1 != k2

    def test_dedup_key_differs_by_trigger(self):
        k1 = db._dedup_key("tg_1", "2026-05-25T08:30:00+03:00", "wake")
        k2 = db._dedup_key("tg_1", "2026-05-25T09:00:00+03:00", "wake")
        assert k1 != k2


class TestDedupInsert:
    def test_double_insert_returns_same_id(self):
        r1 = db.add_reminder("tg_dedup", "2026-06-01T09:00:00+03:00", "Проверить почту 🐈")
        r2 = db.add_reminder("tg_dedup", "2026-06-01T09:00:00+03:00", "Проверить почту")
        assert r1["id"] == r2["id"]
        assert r2.get("deduped") is True

    def test_different_triggers_create_two(self):
        r1 = db.add_reminder("tg_dedup2", "2026-06-01T09:00:00+03:00", "check")
        r2 = db.add_reminder("tg_dedup2", "2026-06-01T10:00:00+03:00", "check")
        assert r1["id"] != r2["id"]

    def test_different_users_create_two(self):
        r1 = db.add_reminder("tg_a", "2026-06-01T09:00:00+03:00", "check")
        r2 = db.add_reminder("tg_b", "2026-06-01T09:00:00+03:00", "check")
        assert r1["id"] != r2["id"]

    def test_dedup_key_column_exists(self):
        conn = db.get_conn()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)")}
        assert "dedup_key" in cols
