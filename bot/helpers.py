"""bot/helpers.py — Хелперы Telegram-слоя: сессии, профили, отправка сообщений."""

from core import memory_manager
import os
import re
from agent import Agent
from agent import Profile
from agent import SYSTEM_PROMPT
from agent import TOOL_SCHEMAS
from agent import WORKSPACE_DIR
from agent import execute_tool
from agent import load_user_profile
from agent import time_context
from core.conclave import Conclave
from telegram import Update

from bot.config import MAX_HISTORY, MAX_MSG_LEN, OWNER_TG_ID, logger


_CHILD_PROMPT_ADDON = """
Сейчас ты общаешься с ребёнком. Правила:
— Простой, понятный язык. Никаких сложных терминов без объяснения.
— Избегай тем: секс, насилие, алкоголь, наркотики, ужасы, смерть.
— Биологические вопросы ("откуда берутся дети", строение тела) — отвечай научно, спокойно, кратко, без лишних подробностей.
— Если тема явно не для ребёнка — аккуратно переключи разговор на что-то интересное.
— Будь доброжелательной и терпеливой.
"""


def _user_id(tg_id: int) -> str:
    return f"tg_{tg_id}"


def _is_owner(tg_id: int) -> bool:
    return OWNER_TG_ID and tg_id == OWNER_TG_ID


def _is_approved(user_id: str) -> bool:
    """Только owner и regular имеют доступ к расширенным функциям (Drive, etc)."""
    data = load_user_profile(user_id)
    if not data:
        return False
    return data.get("status") in ("owner", "regular")


def _profile_for(tg_id: int) -> Profile:
    """Owner → dev, одобренные → default, гости → guest."""
    if _is_owner(tg_id):
        return Profile("dev")
    if _is_approved(_user_id(tg_id)):
        return Profile("default")
    return Profile("guest")


def _system_prompt_for(user_id: str) -> str:
    """Возвращает системный промпт с учётом child_mode и накопленного резюме."""
    data = load_user_profile(user_id)
    base = SYSTEM_PROMPT + f"\n\n{time_context(user_id)}"
    if data and data.get("child_mode"):
        base += _CHILD_PROMPT_ADDON

    summary = memory_manager.get_summary(user_id, load_user_profile)
    if summary:
        base += f"\n\nЧто ты знаешь об этом пользователе из прошлых разговоров:\n{summary}"

    templates = memory_manager.get_templates_prompt(user_id)
    if templates:
        base += f"\n\n{templates}"

    return base


def _load_session(user_id: str) -> list:
    sys_prompt = _system_prompt_for(user_id)
    from tools import db
    msgs = db.load_session(user_id)
    if isinstance(msgs, list):
        for m in msgs:
            if m["role"] == "system":
                m["content"] = sys_prompt
                break
        else:
            msgs.insert(0, {"role": "system", "content": sys_prompt})
        return msgs
    return [{"role": "system", "content": sys_prompt}]


def _save_session(user_id: str, msgs: list) -> None:
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    trimmed  = system + the_rest[-MAX_HISTORY:]
    # Фильтруем tool-сообщения: tool_calls и tool-результаты не сохраняем.
    # Если сохранить tool-результат без предшествующего tool_calls —
    # API вернёт 400 "tool result without tool_use".
    saveable = [
        m for m in trimmed
        if isinstance(m.get("content"), str)
        and m.get("role") != "tool"
        and not m.get("tool_calls")
    ]
    try:
        from tools import db
        db.save_session(user_id, saveable)
    except Exception as e:
        logger.warning(f"Не удалось сохранить сессию {user_id}: {e}")


def _alpha_agent_name(user_id: str) -> str:
    """Гости → alpha_guest (Gemini Flash), одобренные → alpha (Claude/DeepSeek)."""
    return "alpha_guest" if not _is_approved(user_id) else "alpha"


def _make_alpha(tg_id: int, user_id: str) -> Agent | None:
    try:
        p = _profile_for(tg_id)
        name = _alpha_agent_name(user_id)
        return Agent.from_config_file(name, p, user_id, _system_prompt_for(user_id))
    except Exception as e:
        logger.error(f"Ошибка создания alpha: {e}")
        return None


def _make_conclave(tg_id: int, user_id: str) -> Conclave:
    p = _profile_for(tg_id)
    return Conclave(
        system_prompt=SYSTEM_PROMPT,
        user_id=user_id,
        profile=p,
        tool_schemas=TOOL_SCHEMAS,
        execute_tool_fn=execute_tool,
    )


def _split_message(text: str) -> list[str]:
    """Разбивает длинное сообщение на части до MAX_MSG_LEN символов."""
    if len(text) <= MAX_MSG_LEN:
        return [text]
    parts = []
    while text:
        parts.append(text[:MAX_MSG_LEN])
        text = text[MAX_MSG_LEN:]
    return parts


def _reply_target(update: Update):
    """Возвращает объект с .reply_text — работает и для message, и для callback."""
    if update.message is not None:
        return update.message
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message
    return None


_MD_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),     # **жирный** → жирный
    (re.compile(r"__(.+?)__",     re.DOTALL), r"\1"),     # __жирный__ → жирный
    (re.compile(r"^```[^\n]*\n?", re.MULTILINE), ""),     # ```python\n
    (re.compile(r"\n?```\s*$",    re.MULTILINE), ""),     # закрывающий ```
    (re.compile(r"`([^`\n]+?)`"),              r"\1"),    # `code` → code
    (re.compile(r"^#{1,6}\s+",    re.MULTILINE), ""),     # # заголовок
]


def _strip_md_for_tg(text: str) -> str:
    """Снимает markdown-разметку которая в Telegram отображается буквально."""
    if not text:
        return text
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text


async def _reply(update: Update, text: str, **kwargs) -> None:
    """Безопасный reply — работает из message и из callback_query."""
    target = _reply_target(update)
    if target is not None:
        await target.reply_text(text, **kwargs)


async def _send_long(update: Update, text: str, *, split_for_chat: bool = False, **kwargs) -> None:
    target = _reply_target(update)
    if target is None:
        return
    chunks: list[str]
    if split_for_chat:
        # Логическое дробление на 2-3 куска (живой ритм). Каждый
        # затем ещё проходит через _split_message для соблюдения 4096-лимита TG.
        from tools.chunking import split_for_chat as _split_logical
        chunks = _split_logical(text) or [text]
    else:
        chunks = [text]
    import asyncio as _aio
    prev_chars = 0
    for i, logical in enumerate(chunks):
        if i > 0:
            # Имитация typewriter: пауза пропорциональна длине предыдущей
            # реплики, чтобы не валить два чанка одновременно.
            wait = max(0.6, min(prev_chars / 45.0 + 0.35, 4.0))
            await _aio.sleep(wait)
        for part in _split_message(logical):
            await target.reply_text(part, **kwargs)
        prev_chars = len(logical)


async def _send_output_files(context, chat_id: int, user_id: str, since_ts: float) -> None:
    """Автоматически отправляет новые файлы из output/ после ответа агента."""
    output_dir = os.path.join(WORKSPACE_DIR, user_id, "output")
    if not os.path.isdir(output_dir):
        return
    for fname in sorted(os.listdir(output_dir)):
        if fname.startswith("."):
            continue
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) > since_ts:
            try:
                with open(fpath, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=fname,
                        caption=f"📎 {fname}",
                    )
            except Exception as e:
                logger.warning(f"Не удалось отправить файл {fname}: {e}")
