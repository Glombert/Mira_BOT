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

logger = logging.getLogger("Ouroborus")

MEMORY_DIR      = "memory"
WORKSPACE_DIR   = "workspace"
GUEST_LIMIT     = 10
GUEST_TTL_DAYS  = 3
VALID_STATUSES  = ("owner", "regular", "guest", "rejected", "blacklisted", "blocked")

EVOLUTION_FILE  = os.path.join(MEMORY_DIR, "evolution_counter.json")


# ---------------------------------------------------------------------------
# Чтение / запись профилей
# ---------------------------------------------------------------------------

def _load_profile(user_id: str) -> dict | None:
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return None
    try:
        # Используем memory_crypto если доступен и инициализирован
        if _crypto and _crypto.is_enabled():
            data = _crypto.load_json(path)
            return data if isinstance(data, dict) else None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"access_tools: ошибка чтения {user_id}: {e}")
        return None


def _save_profile(user_id: str, data: dict) -> bool:
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    try:
        # memory_crypto.save_json потокобезопасна и работает
        # как с шифрованием так и без (прозрачный fallback на plain JSON)
        if _crypto:
            _crypto.save_json(path, data)
        else:
            # Редкий случай: memory_crypto не импортирован
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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


def set_status(user_id: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        return False
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = status
    if status == "rejected":
        profile["rejected_at"] = datetime.now().strftime("%Y-%m-%d")
    return _save_profile(user_id, profile)


def list_users() -> list[dict]:
    if not os.path.isdir(MEMORY_DIR):
        return []
    users = []
    for fname in sorted(os.listdir(MEMORY_DIR)):
        if not fname.endswith(".json") or fname in ("decisions.log", "evolution_counter.json"):
            continue
        user_id = fname[:-5]
        profile = _load_profile(user_id)
        if profile:
            users.append({
                "id":             user_id,
                "name":           profile.get("name", "—"),
                "status":         profile.get("status", "regular"),
                "last_seen":      profile.get("last_seen", "—"),
                "sessions_count": profile.get("sessions_count", 0),
                "guest_msgs":     profile.get("guest_message_count", 0),
                "child_mode":     profile.get("child_mode", False),
            })
    return users


def approve(user_id: str, new_name: str = "") -> bool:
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


def reject(user_id: str) -> bool:
    """Помечает статус 'rejected' — история сохраняется, может попробовать снова."""
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "rejected"
    profile["rejected_at"] = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"access: отклонён {user_id}")
    return _save_profile(user_id, profile)


def blacklist(user_id: str) -> bool:
    """Добавляет в чёрный список."""
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "blacklisted"
    profile["blacklisted_at"] = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"access: в чёрный список {user_id}")
    return _save_profile(user_id, profile)


def unblacklist(user_id: str) -> bool:
    """Убирает из чёрного списка → rejected (был отклонён, но не в ЧС)."""
    return set_status(user_id, "rejected")


def block(user_id: str) -> bool:
    """Backward compat — алиас blacklist."""
    return blacklist(user_id)


def unblock(user_id: str) -> bool:
    """Backward compat — алиас set_status regular."""
    return set_status(user_id, "regular")


def delete_user(user_id: str) -> bool:
    """Полное удаление: профиль + workspace + сессия."""
    deleted = False
    # Профиль
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    if os.path.exists(path):
        os.remove(path)
        deleted = True
    # Сессия
    sess = os.path.join(MEMORY_DIR, "sessions", f"{user_id}.json")
    if os.path.exists(sess):
        os.remove(sess)
    # Workspace (рекурсивно)
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


def increment_guest_counter(user_id: str, profile: dict) -> tuple[int, int]:
    count = profile.get("guest_message_count", 0) + 1
    profile["guest_message_count"] = count
    _save_profile(user_id, profile)
    return count, GUEST_LIMIT


def cleanup_expired_guests() -> int:
    if not os.path.isdir(MEMORY_DIR):
        return 0
    cutoff = datetime.now() - timedelta(days=GUEST_TTL_DAYS)
    deleted = 0
    for fname in os.listdir(MEMORY_DIR):
        if not fname.endswith(".json"):
            continue
        user_id = fname[:-5]
        profile = _load_profile(user_id)
        if not profile or profile.get("status") != "guest":
            continue
        last_seen_str = profile.get("last_seen", "")
        try:
            last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d")
            if last_seen < cutoff:
                os.remove(os.path.join(MEMORY_DIR, fname))
                logger.info(f"access: гость {user_id} удалён по TTL.")
                deleted += 1
        except ValueError:
            pass
    return deleted


# ---------------------------------------------------------------------------
# Уведомления владельцу
# ---------------------------------------------------------------------------

def notify_owner(message: str, user_id: str = "", buttons: list | None = None) -> None:
    """
    Отправляет уведомление владельцу в Telegram.
    buttons — список кнопок [{"text": "...", "callback_data": "..."}]
    """
    logger.info(f"[OWNER NOTIFY] {message}")
    _log_decision("owner_notification", message)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner = os.getenv("OWNER_TELEGRAM_ID", "")
    if not token or not owner:
        return

    import threading
    def _send():
        try:
            payload: dict = {"chat_id": owner, "text": message}
            if buttons:
                payload["reply_markup"] = json.dumps({
                    "inline_keyboard": [
                        [{"text": b["text"], "callback_data": b["callback_data"]}]
                        for b in buttons
                    ]
                })
            data = urllib.parse.urlencode(payload).encode()
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data, timeout=8,
            )
        except Exception as e:
            logger.warning(f"notify_owner: ошибка отправки: {e}")

    threading.Thread(target=_send, daemon=True).start()


def notify_new_user(user_id: str, name: str, source: str = "telegram") -> None:
    """Уведомляет владельца о новом пользователе с кнопками одобрения."""
    msg = (
        f"Новый пользователь хочет пообщаться!\n"
        f"Имя: {name or '—'}\n"
        f"ID: {user_id}\n"
        f"Источник: {source}"
    )
    notify_owner(msg, user_id=user_id, buttons=[
        {"text": "Одобрить ✅",  "callback_data": f"u_ap_{user_id}"},
        {"text": "Отклонить ❌", "callback_data": f"u_rj_{user_id}"},
    ])


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
