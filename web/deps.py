"""web/deps.py — общие примитивы веба: конфиг и сессии.

Вынесено из web/app.py, чтобы будущие модули web/routes/* могли импортировать
auth/session-хелперы без циклической зависимости от web/app.py. Чистый модуль
без FastAPI (как web/security.py) — легко тестируется и импортируется.
"""

import os

from web.security import make_session as _ws_make, verify_session as _ws_verify

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")  # например: MyMiraBot (без @)
OWNER_TG_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))


def make_session(tg_id: int, name: str) -> str:
    return _ws_make(BOT_TOKEN, tg_id, name)


def verify_session(token: str) -> int | None:
    return _ws_verify(BOT_TOKEN, token)


def web_user_id(tg_id: int) -> str:
    """Web и Telegram делят профиль — user_id одинаковый."""
    return f"tg_{tg_id}"


def verify_owner_session(session: str) -> str | None:
    """Возвращает tg_<owner_id> если токен валиден и пользователь — владелец."""
    if not session:
        return None
    tg_id = verify_session(session)
    if not tg_id or not OWNER_TG_ID or tg_id != OWNER_TG_ID:
        return None
    return web_user_id(tg_id)
