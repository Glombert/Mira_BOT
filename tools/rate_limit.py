"""In-memory rate limiter — sliding window per (user_id, action).

Дизайн:
- Sliding window: храним временные метки попыток, чистим старше window_sec
- check_and_record(user_id, action) → (allowed, retry_after_sec)
- Owner (OWNER_TELEGRAM_ID) пропускается без проверки

Лимиты по умолчанию:
- "message"  : 60 / 60 сек
- "upload"   : 20 / 60 сек

При превышении возвращается retry_after — сколько секунд до момента когда
старейшая запись выйдет из окна и слот освободится. Используется чтобы
Мира могла сказать "подожди X секунд", а не просто "лимит".
"""

import os
import threading
import time
from collections import deque
from typing import Tuple

LIMITS: dict[str, tuple[int, int]] = {
    "message": (60, 60),   # 60 запросов / 60 секунд
    "upload":  (20, 60),   # 20 файлов / 60 секунд
}

_lock = threading.Lock()
_buckets: dict[tuple[str, str], deque] = {}


def _is_owner(user_id: str) -> bool:
    """Mira owner — без лимитов. user_id формата tg_{int} или просто int."""
    owner = os.getenv("OWNER_TELEGRAM_ID", "0")
    if not owner or owner == "0":
        return False
    raw = user_id.replace("tg_", "")
    return raw == owner


def check_and_record(user_id: str, action: str = "message") -> Tuple[bool, int]:
    """Проверяет лимит и записывает попытку.

    Возвращает (allowed, retry_after_sec).
        allowed=True  → запрос разрешён, попытка записана
        allowed=False → лимит превышен, retry_after = когда освободится слот
    """
    if _is_owner(user_id):
        return True, 0

    limit, window = LIMITS.get(action, LIMITS["message"])
    now = time.time()
    cutoff = now - window
    key = (user_id, action)

    with _lock:
        bucket = _buckets.setdefault(key, deque())
        # Чистим устаревшие
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(bucket[0] + window - now) + 1
            return False, max(retry_after, 1)

        bucket.append(now)
        return True, 0


def reset(user_id: str | None = None) -> None:
    """Сбрасывает все счётчики (для тестов) или для одного user_id."""
    with _lock:
        if user_id is None:
            _buckets.clear()
        else:
            for key in list(_buckets.keys()):
                if key[0] == user_id:
                    del _buckets[key]


def friendly_message(action: str, retry_after: int) -> str:
    """Сообщение от лица Миры при превышении лимита."""
    if action == "upload":
        return (
            f"Многовато файлов сразу — мне нужно немного времени, чтобы успеть "
            f"их обработать. Попробуй через {retry_after} сек."
        )
    if action == "size":
        return (
            "Файл слишком тяжёлый — я могу принимать до 20 МБ. "
            "Можешь сжать или разбить на части?"
        )
    return (
        f"Эй, помедленнее — я ещё не успеваю отвечать. "
        f"Подожди {retry_after} сек и продолжим."
    )
