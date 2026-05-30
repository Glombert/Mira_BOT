"""Тесты для tools/messaging.py — передача сообщений между пользователями."""

import os
import pytest
from unittest.mock import patch
from tools import db
from tools import messaging


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    monkeypatch.setattr(db, "_initialized", False)
    db._close_thread_conn()
    db.init_db(str(db_file))
    # Заглушаем TG-доставку и FCM, чтобы не было реальных сетевых вызовов
    monkeypatch.setattr(messaging, "_deliver_telegram", lambda *a, **k: None)
    yield db
    db._close_thread_conn()


def _make_user(uid, name, status="regular"):
    db.save_user_profile(uid, {"name": name, "status": status})


def test_find_user_exact_match(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    r = messaging.find_user("Андрей", caller_id="tg_2")
    assert r["ok"]
    assert r["user"]["id"] == "tg_1"


def test_find_user_excludes_caller(fresh_db):
    _make_user("tg_1", "Андрей")
    r = messaging.find_user("Андрей", caller_id="tg_1")
    assert not r["ok"]
    assert "Не нашла" in r["error"]


def test_find_user_partial(fresh_db):
    _make_user("tg_1", "Андрей Петров")
    _make_user("tg_2", "Мария")
    r = messaging.find_user("андрей", caller_id="tg_2")
    assert r["ok"]
    assert r["user"]["id"] == "tg_1"


def test_find_user_ambiguous(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Андрей")
    _make_user("tg_3", "Мария")
    r = messaging.find_user("Андрей", caller_id="tg_3")
    assert not r["ok"]
    assert len(r["matches"]) == 2


def test_find_user_only_approved(fresh_db):
    _make_user("tg_1", "Андрей", status="guest")
    _make_user("tg_2", "Мария")
    r = messaging.find_user("Андрей", caller_id="tg_2")
    assert not r["ok"]  # гостям не пишем


def test_send_blocks_guests(fresh_db):
    _make_user("tg_1", "Андрей", status="guest")
    _make_user("tg_2", "Мария")
    r = messaging.send_to_user("Мария", "привет", caller_id="tg_1")
    assert not r["ok"]
    assert "одобренные" in r["error"]


def test_send_creates_pending(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    r = messaging.send_to_user("Мария", "Привет, как ты?", caller_id="tg_1")
    assert r["ok"]
    assert r["needs_confirmation"]
    assert r["target_name"] == "Мария"
    assert "pending_id" in r


def test_confirm_delivers_message(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    prep = messaging.send_to_user("Мария", "Привет!", caller_id="tg_1")
    r = messaging.confirm_send_to_user(prep["pending_id"], caller_id="tg_1")
    assert r["ok"]
    assert r["delivered"]
    # Сообщение в БД получателя
    msgs = db.list_unseen_messages("tg_2")
    assert len(msgs) == 1
    assert msgs[0]["body"] == "Привет!"
    assert msgs[0]["from_name"] == "Андрей"


def test_confirm_rejects_alien_pending(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    _make_user("tg_3", "Иван")
    prep = messaging.send_to_user("Мария", "Привет!", caller_id="tg_1")
    # Иван пытается отправить чужой черновик
    r = messaging.confirm_send_to_user(prep["pending_id"], caller_id="tg_3")
    assert not r["ok"]


def test_block_sender_prevents_send(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    # Мария блокирует Андрея
    r1 = messaging.block_sender("Андрей", caller_id="tg_2")
    assert r1["ok"]
    # Андрей пытается передать
    r2 = messaging.send_to_user("Мария", "привет", caller_id="tg_1")
    assert not r2["ok"]
    assert "не принимает" in r2["error"]


def test_unblock_sender_restores(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    messaging.block_sender("Андрей", caller_id="tg_2")
    messaging.unblock_sender("Андрей", caller_id="tg_2")
    r = messaging.send_to_user("Мария", "привет", caller_id="tg_1")
    assert r["ok"]


def test_cancel_send(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    prep = messaging.send_to_user("Мария", "Привет!", caller_id="tg_1")
    r = messaging.cancel_send_to_user(prep["pending_id"], caller_id="tg_1")
    assert r["ok"]
    # confirm после cancel должен упасть
    r2 = messaging.confirm_send_to_user(prep["pending_id"], caller_id="tg_1")
    assert not r2["ok"]


def test_empty_body_rejected(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    r = messaging.send_to_user("Мария", "   ", caller_id="tg_1")
    assert not r["ok"]
    assert "Пустое" in r["error"]


def test_long_body_rejected(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    r = messaging.send_to_user("Мария", "x" * 5000, caller_id="tg_1")
    assert not r["ok"]


def test_list_unseen_returns_in_order(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    p1 = messaging.send_to_user("Мария", "Первое", caller_id="tg_1")
    messaging.confirm_send_to_user(p1["pending_id"], caller_id="tg_1")
    p2 = messaging.send_to_user("Мария", "Второе", caller_id="tg_1")
    messaging.confirm_send_to_user(p2["pending_id"], caller_id="tg_1")
    unseen = db.list_unseen_messages("tg_2")
    assert [m["body"] for m in unseen] == ["Первое", "Второе"]


def test_mark_seen(fresh_db):
    _make_user("tg_1", "Андрей")
    _make_user("tg_2", "Мария")
    p = messaging.send_to_user("Мария", "Привет!", caller_id="tg_1")
    messaging.confirm_send_to_user(p["pending_id"], caller_id="tg_1")
    assert len(db.list_unseen_messages("tg_2")) == 1
    db.mark_messages_seen("tg_2")
    assert len(db.list_unseen_messages("tg_2")) == 0
