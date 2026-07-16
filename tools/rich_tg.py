"""rich_tg.py — нативные Rich Messages Telegram (Bot API 10.1) для ответов Миры.

Раньше markdown Миры перед отправкой в TG зачищался (_strip_md_for_tg):
таблицы и заголовки превращались в кашу. sendRichMessage рендерит их
нативно, причём InputRichMessage принимает поле `markdown` — Telegram сам
парсит GFM (заголовки, таблицы, списки, чек-листы, цитаты, код, hr).
PTB 22.8 метода ещё не знает — зовём API напрямую.

Использование: rich только для ответов СО структурой (таблица/заголовок/
список/код) — обычная беседа остаётся в стиле чанков. Любая ошибка API
(фича раскатывается постепенно) → False, вызывающий falls back на
старый plain-путь.
"""

import os
import re
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger("MiraBot")

_STRUCTURE_RE = re.compile(r"^(#{1,6} |\|.+\||```|[-*] |\d+\. |> )", re.M)

# Лимит Rich Message по документации — 32768 символов текста.
_MAX_RICH_CHARS = 32000


def has_rich_structure(md: str) -> bool:
    """Есть ли в markdown структура, ради которой стоит слать rich-сообщение."""
    return bool(_STRUCTURE_RE.search(md or ""))


def send_rich(chat_id: int, md_text: str) -> bool:
    """Шлёт rich-сообщение. False — не вышло (вызывающий шлёт по-старому)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not (md_text or "").strip():
        return False
    if len(md_text) > _MAX_RICH_CHARS:
        return False
    payload = {"chat_id": chat_id, "rich_message": {"markdown": md_text}}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendRichMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = bool(json.loads(resp.read().decode()).get("ok"))
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode()).get("description", "")
        except Exception:
            desc = str(e)
        logger.info(f"rich_tg: sendRichMessage отказ ({e.code}: {desc}) — фолбэк на plain")
        return False
    except Exception as e:
        logger.info(f"rich_tg: sendRichMessage недоступен ({e}) — фолбэк на plain")
        return False
    return ok
