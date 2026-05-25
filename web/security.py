"""Чистые security-хелперы веба.

Вынесены отдельно от web/app.py чтобы:
- не тянуть FastAPI и весь стек агента в тесты
- держать функции легко-аудируемыми (один файл, маленький, без побочных эффектов)

Используется web/app.py — функции реимпортируются там для backward compat
с прежним импорт-путём.
"""

import hmac
import hashlib
import os
import time
import secrets
import threading
from collections import deque

# Session token = HMAC-SHA256 от payload, 32 hex символа (128 бит).
SESSION_SIG_LEN = 32
SESSION_MAX_AGE = 30 * 86400


def make_session(bot_token: str, tg_id: int, name: str) -> str:
    """Создаёт подписанный session token со временем выдачи."""
    payload = f"{tg_id}:{name}:{int(time.time())}"
    sig     = hmac.new(bot_token.encode(), payload.encode(), hashlib.sha256).hexdigest()[:SESSION_SIG_LEN]
    return f"{payload}:{sig}"


def verify_session(bot_token: str, token: str, *, now: float | None = None) -> int | None:
    """Возвращает tg_id если токен валиден и не истёк, иначе None."""
    try:
        *parts, sig = token.split(":")
        payload  = ":".join(parts)
        expected = hmac.new(bot_token.encode(), payload.encode(), hashlib.sha256).hexdigest()[:SESSION_SIG_LEN]
        if not hmac.compare_digest(expected, sig):
            return None
        tg_id  = int(parts[0])
        issued = int(parts[-1])
        current = now if now is not None else time.time()
        if current - issued > SESSION_MAX_AGE:
            return None
        return tg_id
    except Exception:
        return None


# One-time mobile auth codes (for /m/auth deep-link flow)
_MOBILE_AUTH_CODES: dict[str, tuple[str, float]] = {}
_MOBILE_AUTH_LOCK = threading.Lock()
_MOBILE_AUTH_TTL = 300  # 5 minutes


def make_mobile_auth_code(session_token: str) -> str:
    """Создаёт одноразовый код для /m/auth, который заменяет session token в URL.
    Код живёт 5 минут и удаляется при первом использовании."""
    code = secrets.token_urlsafe(32)
    with _MOBILE_AUTH_LOCK:
        _MOBILE_AUTH_CODES[code] = (session_token, time.time() + _MOBILE_AUTH_TTL)
    return code


def redeem_mobile_auth_code(code: str) -> str | None:
    """Возвращает session token и инвалидирует код. None если не найден или истёк."""
    with _MOBILE_AUTH_LOCK:
        entry = _MOBILE_AUTH_CODES.pop(code, None)
    if entry is None:
        return None
    token, expiry = entry
    if time.time() > expiry:
        return None
    return token


def safe_filename(raw: str | None) -> str:
    """Снимает пути и опасные символы, оставляя только имя файла.

    Работает и с POSIX (/), и с Windows (\\) разделителями — последние
    нормализуются до POSIX перед обрезанием пути.
    """
    # Нормализуем windows-разделители до POSIX, чтобы basename отрезал их
    normalized = (raw or "upload").replace("\\", "/")
    name = os.path.basename(normalized).strip().replace("\x00", "")
    if not name or name in (".", ".."):
        name = "upload"
    return name[:255]


def resolve_under(root: str, *parts: str) -> str | None:
    """Возвращает realpath, если он строго внутри root; иначе None.

    Защита от path traversal через .. и symlinks. Сам root не считается
    "внутри" — функция предназначена для разрешения пути К файлу/папке
    в root, а не к самому root.
    """
    candidate = os.path.realpath(os.path.join(root, *parts))
    root_real = os.path.realpath(root)
    if candidate == root_real:
        return None
    if not candidate.startswith(root_real + os.sep):
        return None
    return candidate
