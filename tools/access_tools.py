"""
tools/access_tools.py — управление доступом пользователей.

Статусы:
    owner       — всё, включая /evolve, /release, управление пользователями
    regular     — полный доступ к workspace и Конклаву
    guest       — только разговор, 10 сообщений, ждёт одобрения
    rejected    — отклонён владельцем (помнит историю отказа)
    blacklisted — чёрный список, молчание + уведомление владельцу раз в сутки
    blocked     — синоним blacklisted (backward compatibility)

Хранится в поле "status" файла memory/{user_id}.json.
"""

import os
import json
import shutil
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

try:
    import memory_crypto as _crypto
except ImportError:
    _crypto = None

logger = logging.getLogger("Ouroboros")

MEMORY_DIR      = "memory"
WORKSPACE_DIR   = "workspace"
GUEST_LIMIT     = 10
GUEST_TTL_DAYS  = 3
VALID_STATUSES  = ("owner", "regular", "guest", "rejected", "blacklisted", "blocked")

EVOLUTION_FILE  = os.path.join(MEMORY_DIR, "evolution_counter.json")

_OWNER_TG = os.getenv("OWNER_TELEGRAM_ID", "0").strip()


def _is_owner_id(caller_id: str) -> bool:
    if not _OWNER_TG or _OWNER_TG == "0":
        return False
    return caller_id in (f"tg_{_OWNER_TG}", f"cli_{_OWNER_TG}")


def _require_owner(caller_id: str) -> None:
    if not _is_owner_id(caller_id):
        raise PermissionError(f"{caller_id} не владелец")


# ---------------------------------------------------------------------------
# Чтение / запись профилей
# ---------------------------------------------------------------------------

def _load_profile(user_id: str) -> dict | None:
    from tools import db
    try:
        return db.load_user_profile(user_id)
    except Exception as e:
        logger.error(f"access_tools: ошибка чтения {user_id}: {e}")
        return None


def _save_profile(user_id: str, data: dict) -> bool:
    from tools import db
    try:
        db.save_user_profile(user_id, data)
        return True
    except Exception as e:
        logger.error(f"access_tools: ошибка записи {user_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Публичный интерфейс: статусы
# ---------------------------------------------------------------------------

def get_status(user_id: str) -> str:
    profile = _load_profile(user_id)
    if profile is None:
        return "regular"
    return profile.get("status", "regular")


def set_status(user_id: str, status: str, caller_id: str = "") -> bool:
    if status not in VALID_STATUSES:
        return False
    if caller_id:
        _require_owner(caller_id)
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = status
    if status == "rejected":
        profile["rejected_at"] = datetime.now().strftime("%Y-%m-%d")
    return _save_profile(user_id, profile)


def list_users() -> list[dict]:
    from tools import db
    users = []
    for user_id, profile in db.list_user_profiles():
        users.append({
            "id":             user_id,
            "name":           profile.get("name", "—"),
            "status":         profile.get("status", "regular"),
            "last_seen":      profile.get("last_seen", "—"),
            "sessions_count": profile.get("sessions_count", 0),
            "guest_msgs":     profile.get("guest_message_count", 0),
            "child_mode":     profile.get("child_mode", False),
        })
    users.sort(key=lambda u: u["id"])
    return users


def approve(user_id: str, new_name: str = "", caller_id: str = "") -> bool:
    if caller_id:
        _require_owner(caller_id)
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "regular"
    if new_name:
        profile["name"] = new_name
    profile.pop("guest_message_count", None)
    profile.pop("rejected_at", None)
    logger.info(f"access: одобрен {user_id} → regular")
    return _save_profile(user_id, profile)


def reject(user_id: str, caller_id: str = "") -> bool:
    """Помечает статус 'rejected' — история сохраняется, может попробовать снова."""
    if caller_id:
        _require_owner(caller_id)
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "rejected"
    profile["rejected_at"] = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"access: отклонён {user_id}")
    return _save_profile(user_id, profile)


def blacklist(user_id: str, caller_id: str = "") -> bool:
    """Добавляет в чёрный список."""
    if caller_id:
        _require_owner(caller_id)
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "blacklisted"
    profile["blacklisted_at"] = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"access: в чёрный список {user_id}")
    return _save_profile(user_id, profile)


def unblacklist(user_id: str, caller_id: str = "") -> bool:
    return set_status(user_id, "rejected", caller_id=caller_id)


def block(user_id: str, caller_id: str = "") -> bool:
    return blacklist(user_id, caller_id=caller_id)


def unblock(user_id: str, caller_id: str = "") -> bool:
    return set_status(user_id, "regular", caller_id=caller_id)


def delete_user(user_id: str, caller_id: str = "") -> bool:
    """Полное удаление: профиль + сессия + workspace + gdrive + push."""
    if caller_id:
        _require_owner(caller_id)
    from tools import db
    deleted = db.delete_user_profile(user_id)
    db.delete_session(user_id)
    db.delete_session(f"web_{user_id}")
    db.delete_gdrive_token(user_id)
    try:
        from tools import db as _db
        _db.execute("DELETE FROM push_tokens WHERE user_id=?", (user_id,))
    except Exception:
        pass
    ws = os.path.join(WORKSPACE_DIR, user_id)
    if os.path.isdir(ws):
        shutil.rmtree(ws, ignore_errors=True)
        deleted = True
    logger.info(f"access: удалён {user_id} (профиль + workspace)")
    return deleted


def should_notify_blacklisted(user_id: str) -> bool:
    """Возвращает True если с последнего уведомления прошло больше суток."""
    profile = _load_profile(user_id)
    if not profile:
        return True
    last = profile.get("last_blacklist_notify", "")
    if not last:
        return True
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d")
        return (datetime.now() - last_dt).days >= 1
    except ValueError:
        return True


def mark_blacklist_notified(user_id: str) -> None:
    profile = _load_profile(user_id)
    if profile:
        profile["last_blacklist_notify"] = datetime.now().strftime("%Y-%m-%d")
        _save_profile(user_id, profile)


def get_user_timezone(user_id: str) -> str:
    """Возвращает IANA-зону пользователя из профиля. Default 'UTC'.

    Используется time_context (что показать как «сейчас») и parse_time
    (как интерпретировать «завтра 8:00» от пользователя).
    """
    profile = _load_profile(user_id)
    if not profile:
        return "UTC"
    return profile.get("timezone") or "UTC"


def set_user_timezone(user_id: str, tz: str) -> tuple[bool, str]:
    """Валидирует и сохраняет IANA-зону. Возвращает (ok, message)."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            return False, f"Неизвестная зона: {tz}. Примеры: Europe/Moscow, Asia/Khabarovsk, UTC"
    except ImportError:
        # Python < 3.9 — отказ
        return False, "zoneinfo недоступна — обновите Python до 3.9+"

    profile = _load_profile(user_id)
    if profile is None:
        return False, "Профиль не найден"
    profile["timezone"] = tz
    if _save_profile(user_id, profile):
        return True, f"Зона установлена: {tz}"
    return False, "Ошибка записи"


def increment_guest_counter(user_id: str, profile: dict) -> tuple[int, int]:
    count = profile.get("guest_message_count", 0) + 1
    profile["guest_message_count"] = count
    _save_profile(user_id, profile)
    return count, GUEST_LIMIT


def cleanup_expired_guests() -> int:
    from tools import db
    cutoff = datetime.now() - timedelta(days=GUEST_TTL_DAYS)
    deleted = 0
    for user_id, profile in db.list_user_profiles():
        if profile.get("status") != "guest":
            continue
        last_seen_str = profile.get("last_seen", "")
        try:
            last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d")
            if last_seen < cutoff:
                db.delete_user_profile(user_id)
                logger.info(f"access: гость {user_id} удалён по TTL.")
                deleted += 1
        except ValueError:
            pass
    return deleted


# ---------------------------------------------------------------------------
# Уведомления владельцу
# ---------------------------------------------------------------------------

def _tg_split(text: str, limit: int = 3900) -> list[str]:
    """Режет длинный текст на куски ≤ limit, стараясь по \n\n→\n→ пробелу."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def notify_owner(message: str, user_id: str = "", buttons: list | None = None) -> None:
    """
    Отправляет уведомление владельцу.

    Каналы:
    - owner_inbox (БД) — полный текст в тех-чат приложения, всегда
    - FCM push — обрезанный body, если есть зарегистрированные токены
    - Telegram — основной fallback, длинный текст разбивается на чанки

    buttons — Telegram inline-кнопки + сохраняются в payload owner_inbox.
    """
    logger.info(f"[OWNER NOTIFY] {message[:200]}")
    _log_decision("owner_notification", message[:500])

    owner = os.getenv("OWNER_TELEGRAM_ID", "")

    # 0. Тех-чат в приложении (всегда — даже без Telegram-токена)
    try:
        from tools import db as _db
        _db.append_inbox(
            type_="system",
            title="Системное уведомление",
            body=message,
            importance="MINOR",
            payload={"buttons": buttons} if buttons else None,
        )
    except Exception as e:
        logger.warning(f"notify_owner: append_inbox failed: {e}")

    # 0b. WS realtime для приложения
    if owner:
        try:
            from tools.owner_channel import push_to_owner
            push_to_owner({
                "channel": "tech",
                "type": "system",
                "ts": datetime.now().isoformat(),
                "body": message,
                "buttons": buttons or [],
            })
        except Exception as e:
            logger.warning(f"notify_owner: WS push failed: {e}")

    # 1. FCM (push в мобильное приложение, если установлено и юзер залогинен)
    if owner:
        try:
            from tools import fcm_tools
            fcm_tools.send_push(
                user_id=f"tg_{owner}",
                title="Mira",
                body=message[:240],
            )
        except Exception as e:
            logger.warning(f"notify_owner: FCM не сработал: {e}")

    # 2. Telegram (всегда — это основной канал и fallback)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not owner:
        return

    chunks = _tg_split(message)
    reply_markup_json = None
    if buttons:
        reply_markup_json = json.dumps({
            "inline_keyboard": [
                [{"text": b["text"], "callback_data": b["callback_data"]}]
                for b in buttons
            ]
        })

    import threading
    def _send():
        try:
            for i, chunk in enumerate(chunks):
                payload: dict = {"chat_id": owner, "text": chunk}
                # Кнопки крепим только к последнему чанку
                if reply_markup_json and i == len(chunks) - 1:
                    payload["reply_markup"] = reply_markup_json
                data = urllib.parse.urlencode(payload).encode()
                urllib.request.urlopen(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=data, timeout=8,
                )
        except Exception as e:
            logger.warning(f"notify_owner: ошибка отправки: {e}")

    threading.Thread(target=_send, daemon=True).start()


def notify_new_user(user_id: str, name: str, source: str = "telegram") -> None:
    """Уведомляет владельца о новом пользователе с кнопками одобрения.

    Каналы:
    - owner_inbox (БД) — тип approval_request с user_id/name/source в payload
    - WS — channel=tech, type=approval_request (для drawer/тех-чата)
    - Telegram — sendMessage с inline-кнопками (callback_data)
    """
    msg = (
        f"Новый пользователь хочет пообщаться!\n"
        f"Имя: {name or '—'}\n"
        f"ID: {user_id}\n"
        f"Источник: {source}"
    )
    buttons = [
        {"text": "Одобрить ✅",  "callback_data": f"u_ap_{user_id}"},
        {"text": "Отклонить ❌", "callback_data": f"u_rj_{user_id}"},
    ]
    payload = {"user_id": user_id, "name": name, "source": source, "buttons": buttons}

    # 1. owner_inbox
    inbox_id = 0
    try:
        from tools import db as _db
        inbox_id = _db.append_inbox(
            type_="approval_request",
            title="Новый пользователь",
            body=msg,
            importance="MAJOR",
            payload=payload,
        )
    except Exception as e:
        logger.warning(f"notify_new_user: append_inbox failed: {e}")

    # 2. WS realtime
    try:
        from tools.owner_channel import push_to_owner
        push_to_owner({
            "channel": "tech",
            "type": "approval_request",
            "id": inbox_id,
            "user_id": user_id,
            "name": name,
            "source": source,
            "body": msg,
            "buttons": buttons,
        })
    except Exception as e:
        logger.warning(f"notify_new_user: WS push failed: {e}")

    # 3. Telegram (sendMessage напрямую — мимо notify_owner, чтобы
    #    не дублировать запись в owner_inbox)
    owner = os.getenv("OWNER_TELEGRAM_ID", "")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not owner or not token:
        return
    import threading
    def _send():
        try:
            tg_payload = {
                "chat_id": owner,
                "text": msg,
                "reply_markup": json.dumps({
                    "inline_keyboard": [
                        [{"text": b["text"], "callback_data": b["callback_data"]}]
                        for b in buttons
                    ]
                }),
            }
            data = urllib.parse.urlencode(tg_payload).encode()
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data, timeout=8,
            )
        except Exception as e:
            logger.warning(f"notify_new_user: TG send failed: {e}")
    threading.Thread(target=_send, daemon=True).start()


def _log_decision(event: str, msg: str) -> None:
    decisions_log = os.path.join(MEMORY_DIR, "decisions.log")
    os.makedirs(MEMORY_DIR, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(), "event": event, "msg": msg}
    try:
        with open(decisions_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"_log_decision: не удалось записать {event}: {e}")


# ---------------------------------------------------------------------------
# Счётчик эволюций
# ---------------------------------------------------------------------------

def _load_evo() -> dict:
    if os.path.exists(EVOLUTION_FILE):
        try:
            with open(EVOLUTION_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"_load_evo: повреждён {EVOLUTION_FILE}: {e}")
    return {"total": 0, "success": 0, "failed": 0}


def _save_evo(data: dict) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(EVOLUTION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def increment_evolution(success: bool) -> None:
    """Фиксирует попытку эволюции."""
    evo = _load_evo()
    evo["total"] += 1
    if success:
        evo["success"] += 1
    else:
        evo["failed"] += 1
    _save_evo(evo)
    logger.info(f"evolution: total={evo['total']} success={evo['success']} failed={evo['failed']}")


def get_evolution_stats() -> dict:
    return _load_evo()
