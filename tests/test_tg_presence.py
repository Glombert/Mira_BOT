"""Тесты tg_presence: валидация реакций, привязка к сообщению, кулдаун аватара."""

import pytest

from tools import tg_presence


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(tg_presence, "_last_messages", {})
    monkeypatch.setattr(tg_presence, "_avatar_state", {"ts": 0.0, "mood": ""})


def test_react_rejects_invalid_emoji():
    r = tg_presence.react("tg_1", "не-эмодзи")
    assert r["ok"] is False
    assert "allowed_sample" in r


def test_react_without_known_message():
    r = tg_presence.react("tg_1", "👍")
    assert r["ok"] is False
    assert "Telegram-чате" in r["error"]


def test_react_calls_api_with_message_ref(monkeypatch):
    calls = {}
    monkeypatch.setattr(tg_presence, "_api", lambda m, p: calls.update(method=m, payload=p) or {"ok": True})
    tg_presence.remember_message("tg_1", 111, 42)
    r = tg_presence.react("tg_1", "🔥")
    assert r == {"ok": True, "reacted": "🔥"}
    assert calls["method"] == "setMessageReaction"
    assert calls["payload"]["chat_id"] == 111
    assert calls["payload"]["message_id"] == 42
    assert calls["payload"]["reaction"] == [{"type": "emoji", "emoji": "🔥"}]


def test_avatar_unknown_mood():
    r = tg_presence.set_mood_avatar("angry")
    assert r["ok"] is False
    assert "available" in r


def test_avatar_cooldown(monkeypatch):
    monkeypatch.setattr(tg_presence, "_api_multipart", lambda *a, **k: {"ok": True})
    r1 = tg_presence.set_mood_avatar("joy")
    assert r1 == {"ok": True, "mood": "joy"}
    # повтор того же настроения — no-op без запроса
    assert tg_presence.set_mood_avatar("joy")["unchanged"] is True
    # другое настроение сразу — кулдаун
    r2 = tg_presence.set_mood_avatar("focus")
    assert r2["ok"] is False
    assert "подожди" in r2["error"]


def test_avatar_files_exist():
    for mood in tg_presence.AVATAR_MOODS:
        assert (tg_presence.AVATAR_DIR / f"{mood}.png").is_file(), mood
