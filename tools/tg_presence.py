"""tg_presence.py — «живое» присутствие Миры в Telegram: реакции и аватар-настроение.

Инструменты работают из рабочего потока агента, поэтому Telegram зовём
напрямую по HTTP (как tools/messaging._deliver_telegram), без PTB-объектов
и event loop.
"""

import os
import json
import time
import logging
import threading
import urllib.request
from pathlib import Path

from tools.paths import at_root

logger = logging.getLogger("MiraBot")

# Последнее сообщение пользователя в TG: user_id → (chat_id, message_id).
# Пишется из bot/chat.py на каждом входящем, читается инструментом tg_react.
_last_messages: dict[str, tuple[int, int]] = {}
_lock = threading.Lock()

AVATAR_DIR = Path(at_root("assets", "avatars"))
AVATAR_MOODS = ("default", "joy", "curiosity", "focus", "frustration")
# Аватар — глобальное «лицо» бота; чаще раза в полчаса менять его — дёрганье.
_AVATAR_COOLDOWN_S = 1800
_avatar_state = {"ts": 0.0, "mood": ""}


def remember_message(user_id: str, chat_id: int, message_id: int) -> None:
    with _lock:
        _last_messages[user_id] = (chat_id, message_id)


def _api(method: str, payload: dict) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN не задан"}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": str(e)}


def _api_multipart(method: str, fields: dict[str, str],
                   file_field: str, filename: str, data: bytes) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN не задан"}
    boundary = f"----mira{int(time.time() * 1000)}"
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": str(e)}


def react(user_id: str, emoji: str) -> dict:
    """Ставит эмодзи-реакцию на последнее сообщение пользователя в Telegram."""
    from telegram.constants import ReactionEmoji
    valid = {e.value for e in ReactionEmoji}
    if emoji not in valid:
        return {
            "ok": False,
            "error": f"'{emoji}' нет среди стандартных реакций Telegram",
            "allowed_sample": "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🎉 ⚡ 🙏 💯 😢 🤗",
        }
    with _lock:
        ref = _last_messages.get(user_id)
    if not ref:
        return {"ok": False,
                "error": "Не знаю, на какое сообщение реагировать — реакции работают только в Telegram-чате"}
    chat_id, message_id = ref
    r = _api("setMessageReaction", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}],
    })
    if not r.get("ok"):
        return {"ok": False, "error": f"Telegram отказал: {r.get('description')}"}
    return {"ok": True, "reacted": emoji}


def set_mood_avatar(mood: str) -> dict:
    """Меняет аватар бота на вариант под настроение (глобально, для всех)."""
    if mood not in AVATAR_MOODS:
        return {"ok": False, "error": f"Неизвестное настроение '{mood}'",
                "available": list(AVATAR_MOODS)}
    if mood == _avatar_state["mood"]:
        return {"ok": True, "unchanged": True, "mood": mood}
    left = _AVATAR_COOLDOWN_S - (time.time() - _avatar_state["ts"])
    if left > 0:
        return {"ok": False,
                "error": f"Аватар менялся недавно, подожди ещё {int(left // 60) + 1} мин"}
    path = AVATAR_DIR / f"{mood}.png"
    if not path.is_file():
        return {"ok": False, "error": f"Нет файла аватара для '{mood}'"}
    r = _api_multipart(
        "setMyProfilePhoto",
        {"photo": json.dumps({"type": "static", "photo": "attach://avatar"})},
        "avatar", f"{mood}.png", path.read_bytes(),
    )
    if not r.get("ok"):
        return {"ok": False, "error": f"Telegram отказал: {r.get('description')}"}
    _avatar_state.update(ts=time.time(), mood=mood)
    logger.info(f"tg_presence: аватар → {mood}")
    return {"ok": True, "mood": mood}
