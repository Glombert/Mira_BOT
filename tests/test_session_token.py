"""Тесты session token web (web/security.py).

Что проверяем:
- Валидный токен возвращает тот же tg_id
- Подделанный токен → None
- Истёкший токен → None
- Случайный мусор → None
"""

import time
import pytest

from web.security import make_session, verify_session, SESSION_MAX_AGE


BOT = "test_bot_token_1234567890"


def test_roundtrip():
    token = make_session(BOT, 12345, "Alice")
    assert verify_session(BOT, token) == 12345


def test_tampered_signature():
    token = make_session(BOT, 12345, "Alice")
    bad = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert verify_session(BOT, bad) is None


def test_tampered_payload():
    token = make_session(BOT, 12345, "Alice")
    parts = token.split(":")
    parts[0] = "99999"
    bad = ":".join(parts)
    assert verify_session(BOT, bad) is None


def test_other_bot_token_rejected():
    token = make_session(BOT, 12345, "Alice")
    assert verify_session("different_bot_token", token) is None


def test_garbage_token():
    assert verify_session(BOT, "") is None
    assert verify_session(BOT, "not-a-token") is None
    assert verify_session(BOT, "a:b:c") is None
    assert verify_session(BOT, "12345::abcdef") is None


def test_expired_token():
    token = make_session(BOT, 12345, "Alice")
    fake_now = time.time() + SESSION_MAX_AGE + 86400
    assert verify_session(BOT, token, now=fake_now) is None


def test_fresh_token_still_valid():
    token = make_session(BOT, 12345, "Alice")
    fake_now = time.time() + SESSION_MAX_AGE - 86400
    assert verify_session(BOT, token, now=fake_now) == 12345
