"""
tools/access_tools.py — управление доступом пользователей.

Статусы:
    owner   — всё, включая /evolve, /release, управление пользователями
    regular — полный доступ к workspace и Конклаву
    guest   — только разговор, 10 сообщений, ждёт одобрения
    blocked — полный запрет

Хранится в поле "status" файла memory/{user_id}.json.
"""

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("Ouroborus")

MEMORY_DIR    = "memory"
GUEST_LIMIT   = 10       # сообщений до блокировки
GUEST_TTL_DAYS = 3       # дней до авто-удаления без одобрения
VALID_STATUSES = ("owner", "regular", "guest", "blocked")


# ---------------------------------------------------------------------------
# Чтение / запись профилей
# ---------------------------------------------------------------------------

def _load_profile(user_id: str) -> dict | None:
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"access_tools: ошибка чтения {user_id}: {e}")
        return None


def _save_profile(user_id: str, data: dict) -> bool:
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"access_tools: ошибка записи {user_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Публичный интерфейс
# ---------------------------------------------------------------------------

def get_status(user_id: str) -> str:
    """Возвращает статус пользователя. 'regular' если профиль не найден."""
    profile = _load_profile(user_id)
    if profile is None:
        return "regular"
    return profile.get("status", "regular")


def set_status(user_id: str, status: str) -> bool:
    """Устанавливает статус пользователя."""
    if status not in VALID_STATUSES:
        return False
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = status
    return _save_profile(user_id, profile)


def list_users() -> list[dict]:
    """
    Возвращает список всех пользователей из memory/.

    Каждый элемент: {"id", "name", "status", "last_seen", "sessions_count"}
    """
    if not os.path.isdir(MEMORY_DIR):
        return []
    users = []
    for fname in sorted(os.listdir(MEMORY_DIR)):
        if not fname.endswith(".json") or fname == "sessions":
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
            })
    return users


def approve(user_id: str, new_name: str = "") -> bool:
    """Одобряет гостя — ставит статус regular, опционально переименовывает."""
    profile = _load_profile(user_id)
    if profile is None:
        return False
    profile["status"] = "regular"
    if new_name:
        profile["name"] = new_name
    profile.pop("guest_message_count", None)
    logger.info(f"access: одобрен {user_id} → regular")
    return _save_profile(user_id, profile)


def reject(user_id: str) -> bool:
    """Удаляет профиль гостя — он может начать заново."""
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return False
    os.remove(path)
    logger.info(f"access: отклонён и удалён {user_id}")
    return True


def block(user_id: str) -> bool:
    """Блокирует пользователя."""
    return set_status(user_id, "blocked")


def unblock(user_id: str) -> bool:
    """Снимает блокировку → regular."""
    return set_status(user_id, "regular")


def increment_guest_counter(user_id: str, profile: dict) -> tuple[int, int]:
    """
    Увеличивает счётчик сообщений гостя.
    Возвращает (текущий счётчик, лимит).
    """
    count = profile.get("guest_message_count", 0) + 1
    profile["guest_message_count"] = count
    _save_profile(user_id, profile)
    return count, GUEST_LIMIT


def cleanup_expired_guests() -> int:
    """
    Удаляет профили гостей старше GUEST_TTL_DAYS дней.
    Возвращает количество удалённых.
    """
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


def notify_owner(message: str) -> None:
    """
    Уведомление владельцу. Сейчас пишет в лог и decisions.log.
    В Этапе 4 будет отправлять в Telegram.
    """
    logger.info(f"[OWNER NOTIFY] {message}")
    decisions_log = os.path.join(MEMORY_DIR, "decisions.log")
    os.makedirs(MEMORY_DIR, exist_ok=True)
    entry = {
        "ts":    datetime.now().isoformat(),
        "event": "owner_notification",
        "msg":   message,
    }
    try:
        with open(decisions_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
