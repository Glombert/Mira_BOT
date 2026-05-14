"""Тесты для tools/rate_limit.py — sliding window + owner exemption."""

import time
import pytest

from tools import rate_limit


@pytest.fixture(autouse=True)
def _reset():
    rate_limit.reset()
    yield
    rate_limit.reset()


def test_under_limit_passes():
    for _ in range(5):
        allowed, retry = rate_limit.check_and_record("tg_42", "message")
        assert allowed is True
        assert retry == 0


def test_exceeding_limit_blocks():
    limit, _ = rate_limit.LIMITS["message"]
    for _ in range(limit):
        rate_limit.check_and_record("tg_42", "message")
    allowed, retry = rate_limit.check_and_record("tg_42", "message")
    assert allowed is False
    assert retry > 0
    assert retry <= 60


def test_users_isolated():
    limit, _ = rate_limit.LIMITS["message"]
    for _ in range(limit):
        rate_limit.check_and_record("tg_alice", "message")
    # alice исчерпала, bob — нет
    allowed_alice, _ = rate_limit.check_and_record("tg_alice", "message")
    allowed_bob, _ = rate_limit.check_and_record("tg_bob", "message")
    assert allowed_alice is False
    assert allowed_bob is True


def test_actions_isolated():
    limit_msg, _ = rate_limit.LIMITS["message"]
    for _ in range(limit_msg):
        rate_limit.check_and_record("tg_1", "message")
    # message исчерпано, upload — отдельный bucket
    allowed_msg, _ = rate_limit.check_and_record("tg_1", "message")
    allowed_upload, _ = rate_limit.check_and_record("tg_1", "upload")
    assert allowed_msg is False
    assert allowed_upload is True


def test_owner_exempt(monkeypatch):
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "12345")
    # 1000 запросов — Owner должен пройти
    for _ in range(1000):
        allowed, retry = rate_limit.check_and_record("tg_12345", "message")
        assert allowed is True
        assert retry == 0


def test_owner_zero_means_no_exemption(monkeypatch):
    """Если OWNER_TELEGRAM_ID не задан (0/пустой), никто не освобождается."""
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "0")
    limit, _ = rate_limit.LIMITS["message"]
    for _ in range(limit):
        rate_limit.check_and_record("tg_0", "message")
    allowed, _ = rate_limit.check_and_record("tg_0", "message")
    assert allowed is False


def test_window_slides(monkeypatch):
    """Старые попытки должны выйти из окна и слот освободиться."""
    limit, window = rate_limit.LIMITS["upload"]
    real_time = time.time
    base = real_time()

    monkeypatch.setattr("tools.rate_limit.time.time", lambda: base)
    for _ in range(limit):
        rate_limit.check_and_record("tg_x", "upload")

    # На границе окна всё ещё блок
    monkeypatch.setattr("tools.rate_limit.time.time", lambda: base + window - 1)
    allowed, _ = rate_limit.check_and_record("tg_x", "upload")
    assert allowed is False

    # После окна — слоты освободились
    monkeypatch.setattr("tools.rate_limit.time.time", lambda: base + window + 1)
    allowed, _ = rate_limit.check_and_record("tg_x", "upload")
    assert allowed is True


def test_friendly_message_message():
    msg = rate_limit.friendly_message("message", 15)
    assert "15" in msg
    assert "Подожди" in msg or "подожди" in msg


def test_friendly_message_upload():
    msg = rate_limit.friendly_message("upload", 12)
    assert "12" in msg
    assert "файл" in msg.lower()


def test_friendly_message_size():
    msg = rate_limit.friendly_message("size", 0)
    assert "20" in msg  # упоминание лимита 20 МБ
