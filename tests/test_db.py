"""Тесты для tools/db.py — SQLite-слой памяти."""

import os
import pytest
from datetime import datetime, timedelta, timezone

from tools import db

MSK = timezone(timedelta(hours=3))


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Создаёт изолированную базу для каждого теста."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    monkeypatch.setattr(db, "_initialized", False)
    db._close_thread_conn()
    db.init_db(str(db_file))
    yield db
    db._close_thread_conn()


# --- user_profiles ---

def test_profile_save_and_load(fresh_db):
    fresh_db.save_user_profile("tg_1", {"name": "Аня", "status": "regular"})
    loaded = fresh_db.load_user_profile("tg_1")
    assert loaded["name"] == "Аня"
    assert loaded["status"] == "regular"
    assert "updated_at" in loaded


def test_profile_load_missing(fresh_db):
    assert fresh_db.load_user_profile("nonexistent") is None


def test_profile_upsert(fresh_db):
    fresh_db.save_user_profile("tg_1", {"name": "Аня"})
    fresh_db.save_user_profile("tg_1", {"name": "Аня", "status": "owner"})
    loaded = fresh_db.load_user_profile("tg_1")
    assert loaded["status"] == "owner"


def test_profile_delete(fresh_db):
    fresh_db.save_user_profile("tg_1", {"name": "Аня"})
    assert fresh_db.delete_user_profile("tg_1") is True
    assert fresh_db.load_user_profile("tg_1") is None
    # Удаление несуществующего — False
    assert fresh_db.delete_user_profile("tg_1") is False


def test_list_user_profiles(fresh_db):
    fresh_db.save_user_profile("tg_1", {"name": "Аня"})
    fresh_db.save_user_profile("tg_2", {"name": "Петя"})
    users = sorted(fresh_db.list_user_profiles())
    assert len(users) == 2
    assert users[0][0] == "tg_1"
    assert users[0][1]["name"] == "Аня"


# --- sessions ---

def test_session_save_and_load(fresh_db):
    msgs = [
        {"role": "system", "content": "Ты Мира"},
        {"role": "user", "content": "Привет"},
    ]
    fresh_db.save_session("tg_1", msgs)
    loaded = fresh_db.load_session("tg_1")
    assert loaded == msgs


def test_session_isolation(fresh_db):
    fresh_db.save_session("a", [{"role": "user", "content": "x"}])
    fresh_db.save_session("b", [{"role": "user", "content": "y"}])
    assert fresh_db.load_session("a")[0]["content"] == "x"
    assert fresh_db.load_session("b")[0]["content"] == "y"


def test_session_delete(fresh_db):
    fresh_db.save_session("tg_1", [{"role": "user", "content": "x"}])
    assert fresh_db.delete_session("tg_1") is True
    assert fresh_db.load_session("tg_1") is None


# --- reminders ---

def test_reminder_add_and_list(fresh_db):
    task = fresh_db.add_reminder("tg_1", "2030-01-01T10:00:00", "Wake up")
    assert task["id"]
    assert task["status"] == "pending"

    pending = fresh_db.list_user_reminders("tg_1")
    assert len(pending) == 1
    assert pending[0]["message"] == "Wake up"


def test_reminder_cancel(fresh_db):
    task = fresh_db.add_reminder("tg_1", "2030-01-01T10:00:00", "x")
    ok, _ = fresh_db.cancel_reminder("tg_1", task["id"])
    assert ok is True
    # Повторная отмена — ошибка
    ok2, msg = fresh_db.cancel_reminder("tg_1", task["id"])
    assert ok2 is False
    assert "cancelled" in msg


def test_reminder_cancel_wrong_user(fresh_db):
    task = fresh_db.add_reminder("tg_1", "2030-01-01T10:00:00", "x")
    ok, msg = fresh_db.cancel_reminder("tg_2", task["id"])
    assert ok is False
    assert "не найден" in msg


def test_reminder_get_due(fresh_db):
    # Используем TZ-aware datetime, чтобы тест работал на любой локальной
    # зоне (раньше naive .now() на UTC+10 интерпретировался как МСК →
    # уезжал на 7 часов в будущее).
    past = (datetime.now(MSK) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(MSK) + timedelta(hours=1)).isoformat()
    fresh_db.add_reminder("tg_1", past, "Past")
    fresh_db.add_reminder("tg_1", future, "Future")

    due = fresh_db.get_due_reminders()
    assert len(due) == 1
    assert due[0]["message"] == "Past"

    # Повторный вызов — пусто (статус уже firing)
    assert fresh_db.get_due_reminders() == []


def test_reminder_mark_done(fresh_db):
    task = fresh_db.add_reminder("tg_1", "2030-01-01T10:00:00", "x")
    fresh_db.mark_reminder_done(task["id"])
    assert fresh_db.list_user_reminders("tg_1") == []


# --- reflections ---

def test_reflections_add_and_load(fresh_db):
    fresh_db.add_reflection("Думаю о времени", "2026-05-14")
    fresh_db.add_reflection("Думаю о памяти", "2026-05-14")
    refls = fresh_db.load_reflections()
    assert len(refls) == 2
    assert refls[0]["content"] == "Думаю о времени"


# --- gdrive tokens ---

def test_gdrive_token_save_and_load(fresh_db):
    token = {"refresh_token": "abc", "access_token": "xyz", "expires_at": 12345}
    fresh_db.save_gdrive_token("tg_1", token)
    loaded = fresh_db.load_gdrive_token("tg_1")
    assert loaded == token


def test_gdrive_token_delete(fresh_db):
    fresh_db.save_gdrive_token("tg_1", {"refresh_token": "x"})
    assert fresh_db.delete_gdrive_token("tg_1") is True
    assert fresh_db.load_gdrive_token("tg_1") is None


# --- owner_inbox ---

def test_inbox_append_and_list(fresh_db):
    id1 = fresh_db.append_inbox("ritual", "длинный текст " * 500, title="t1", importance="MAJOR")
    id2 = fresh_db.append_inbox("system", "короткое", title="t2")
    assert id2 > id1
    items = fresh_db.list_inbox()
    assert len(items) == 2
    assert items[0]["id"] == id1
    assert items[0]["title"] == "t1"
    assert items[0]["importance"] == "MAJOR"
    # body не обрезан
    assert len(items[0]["body"]) > 4000


def test_inbox_since_id_pagination(fresh_db):
    id1 = fresh_db.append_inbox("system", "a")
    id2 = fresh_db.append_inbox("system", "b")
    new_items = fresh_db.list_inbox(since_id=id1)
    assert len(new_items) == 1
    assert new_items[0]["id"] == id2


def test_inbox_mark_read_and_unread_filter(fresh_db):
    id1 = fresh_db.append_inbox("system", "a")
    id2 = fresh_db.append_inbox("system", "b")
    fresh_db.mark_inbox_read(id1)
    unread = fresh_db.list_inbox(unread_only=True)
    assert len(unread) == 1
    assert unread[0]["id"] == id2


def test_inbox_set_action(fresh_db):
    id1 = fresh_db.append_inbox("approval_request", "новый юзер",
                                payload={"user_id": "tg_42"})
    assert fresh_db.set_inbox_action(id1, "approve") is True
    items = fresh_db.list_inbox()
    assert items[0]["action"] == "approve"
    assert items[0]["is_read"] is True
    assert items[0]["payload"] == {"user_id": "tg_42"}


def test_inbox_cleanup_old(fresh_db):
    from datetime import datetime, timedelta
    fresh_db.append_inbox("system", "сегодня")
    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    fresh_db.append_inbox("system", "старое", ts=old_ts)
    deleted = fresh_db.cleanup_inbox(older_than_days=30)
    assert deleted == 1
    items = fresh_db.list_inbox()
    assert len(items) == 1
    assert items[0]["body"] == "сегодня"
