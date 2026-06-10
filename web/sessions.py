"""web/sessions.py — сессии, системный промпт и профиль для веб-слоя.

Вынесено из web/app.py: эти функции не зависят от FastAPI и нужны
и HTTP-роутам, и WS-хендлерам, и фоновым задачам (ритуалы).
"""

import os
import logging
from datetime import datetime

import memory_manager
from agent import (
    SYSTEM_PROMPT, MEMORY_DIR, WORKSPACE_DIR,
    load_user_profile, save_user_profile, notify_new_user, time_context,
)
from web.deps import OWNER_TG_ID

logger = logging.getLogger("MiraWeb")

MAX_HISTORY = 20

MANNER_TRAITS = [
    "тёплая", "вдумчивая", "немногословная", "игривая",
    "формальная", "дерзкая", "заботливая", "прямая",
]

_migrated_users: set[str] = set()


def _migrate_legacy_web_session(user_id: str) -> None:
    """Сливает web_<user_id> в <user_id> и удаляет legacy-запись.

    Стратегия: чья updated_at старше → в начало, моложе → в конец.
    Дедуп смежных дублей по (role, content). После — legacy удаляется.
    Идемпотентно: повторный вызов ничего не делает (legacy уже нет).
    """
    if user_id in _migrated_users:
        return
    _migrated_users.add(user_id)
    from tools import db
    legacy_key = f"web_{user_id}"
    legacy = db.load_session(legacy_key)
    if not legacy:
        return
    current = db.load_session(user_id) or []
    legacy_ts  = db.get_session_updated_at(legacy_key)  or ""
    current_ts = db.get_session_updated_at(user_id)     or ""
    if legacy_ts <= current_ts:
        merged = legacy + current
    else:
        merged = current + legacy
    # System-prompt пересчитывается при каждом _load_session, в БД ему делать
    # нечего. Дедупим смежные дубли (могут возникнуть на стыке двух сессий).
    out: list = []
    prev: tuple | None = None
    for m in merged:
        if m.get("role") == "system":
            continue
        key = (m.get("role"), m.get("content"))
        if key != prev:
            out.append(m)
            prev = key
    db.save_session(user_id, out)
    db.delete_session(legacy_key)
    logger.info(f"migrate: web_{user_id} ({len(legacy)}) + {user_id} ({len(current)}) → {len(out)}")


def _load_session(user_id: str) -> list:
    _migrate_legacy_web_session(user_id)
    sys_prompt = _system_prompt_for(user_id)
    from tools import db
    msgs = db.load_session(user_id)
    if isinstance(msgs, list):
        for m in msgs:
            if m.get("role") == "system":
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

    def _strip(m):
        c = m.get("content")
        if isinstance(c, list):
            texts = [p.get("text", "") for p in c if p.get("type") == "text"]
            return {**m, "content": " ".join(t for t in texts if t) or "[медиа]"}
        return m

    saveable = [
        _strip(m) for m in trimmed
        if isinstance(m.get("content"), (str, list))
        and m.get("role") != "tool"
        and not m.get("tool_calls")
    ]

    try:
        from tools import db
        db.save_session(user_id, saveable)
    except Exception as e:
        logger.warning(f"save_session {user_id}: {e}")


def _persona_block(profile: dict | None) -> str:
    """Блок системного промпта из анкеты пользователя (заполняет он сам)."""
    f = (profile or {}).get("form") or {}
    parts: list[str] = []
    addr = (f.get("addressing") or "").strip()
    form = (f.get("address_form") or "").strip()
    if addr or form:
        s = "Обращайся к собеседнику"
        if addr:
            s += f" «{addr}»"
        if form:
            s += f", на «{form}»"
        parts.append(s + ".")
    manner = [m for m in (f.get("manner") or []) if m in MANNER_TRAITS]
    if manner:
        parts.append(
            "Манера общения именно с ним: " + ", ".join(manner) + ". "
            "Это только тон — ты остаёшься собой, твой характер выше неизменен; "
            "подстрой регистр под человека, не противореча себе."
        )
    bio = []
    if (f.get("origin") or "").strip():
        bio.append(f"откуда: {f['origin'].strip()}")
    if (f.get("occupation") or "").strip():
        bio.append(f"занятие: {f['occupation'].strip()}")
    if bio:
        parts.append("О собеседнике — " + "; ".join(bio) + ".")
    notes = (f.get("notes") or "").strip()
    if notes:
        parts.append(f"Что он сам рассказал о себе: {notes[:500]}")
    if not parts:
        return ""
    return ("Анкета собеседника (он заполнил её сам — подстройся, оставаясь собой):\n"
            + "\n".join("— " + p for p in parts))


def _changelog_augment(user_id: str) -> str:
    """Подсказка Мире про новые возможности, если профиль их ещё «не видел».

    Сравнивает mtime WHATS_NEW.md с profile.last_changelog_seen.
    Возвращает строку, которую WS handler аугментирует к system-промпту
    ОДНОРАЗОВО — после успешного ответа _mark_changelog_seen фиксирует
    текущий mtime, и следующая итерация подсказку уже не добавит.
    """
    from tools.whats_new import changelog_mtime, latest_entries_since
    mtime = changelog_mtime()
    if mtime <= 0:
        return ""
    profile = load_user_profile(user_id) or {}
    seen = float(profile.get("last_changelog_seen") or 0.0)
    if seen >= mtime:
        return ""
    audience = "owner" if profile.get("status") == "owner" else "all"
    entries = latest_entries_since(seen, audience=audience, limit=5)
    if not entries:
        return ""
    bullets = "\n".join(f"- ({e['date']}) {e['text']}" for e in entries)
    return (
        "У тебя появились новые возможности с момента, когда этот собеседник "
        "тебя в последний раз видел. Если уместно по теме разговора — кратко "
        "упомяни самое релевантное (без рекламы и без полного списка). Если не "
        "уместно — молчи. Список свежих фич:\n" + bullets
    )


def _incoming_augment(user_id: str) -> str:
    """Подсказка Мире о непрочитанных входящих от других пользователей.

    Возвращает блок «У тебя N писем от X: «...»; от Y: «...»». Зачитай
    их собеседнику уместно — не списком, а живой репликой».
    Сразу НЕ помечает как seen — это сделает _mark_incoming_seen после
    успешного ответа Миры.
    """
    from tools import db as _db
    msgs = _db.list_unseen_messages(user_id, limit=5)
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        body = (m.get("body") or "").strip()
        preview = body if len(body) <= 220 else (body[:220] + "…")
        lines.append(f"— от {m['from_name']}: «{preview}»")
    return (
        "Тебе передали через тебя сообщения (ещё не зачитанные). "
        "Зачитай вслух от имени отправителя в подходящий момент разговора — "
        "своими словами, не в виде списка, без служебных пометок. Не выдумывай "
        "то, чего нет в тексте. После — спроси, хочет ли собеседник ответить.\n"
        + "\n".join(lines)
    )


def _mark_incoming_seen(user_id: str) -> None:
    """Помечает входящие как зачитанные после успешного ответа Миры."""
    try:
        from tools import db as _db
        _db.mark_messages_seen(user_id)
    except Exception as e:
        logger.warning(f"_mark_incoming_seen {user_id}: {e}")


def _mark_changelog_seen(user_id: str) -> None:
    """Фиксирует, что Мира уже учла последний апдейт для этого пользователя."""
    from tools.whats_new import changelog_mtime
    mtime = changelog_mtime()
    if mtime <= 0:
        return
    profile = load_user_profile(user_id)
    if not profile:
        return
    profile["last_changelog_seen"] = mtime
    try:
        save_user_profile(user_id, profile)
    except Exception as e:
        logger.warning(f"_mark_changelog_seen {user_id}: {e}")


def _system_prompt_for(user_id: str) -> str:
    """Собирает system-промпт. Между статичным ядром (характер + регламент,
    кэшируется через cache_control) и динамической частью (время, профиль,
    summary, шаблоны) ставим маркер DYNAMIC_MARKER — providers разрезает по
    нему и кэширует только static."""
    from providers import DYNAMIC_MARKER
    profile   = load_user_profile(user_id)
    static    = SYSTEM_PROMPT
    dyn       = time_context(user_id)
    persona   = _persona_block(profile)
    summary   = memory_manager.get_summary(user_id, load_user_profile)
    templates = memory_manager.get_templates_prompt(user_id)
    if persona:
        dyn += f"\n\n{persona}"
    if summary:
        dyn += f"\n\nЧто ты знаешь об этом пользователе из прошлых разговоров:\n{summary}"
    if templates:
        dyn += f"\n\n{templates}"
    return f"{static}\n\n{DYNAMIC_MARKER}\n\n{dyn}"


def _is_approved(user_id: str) -> bool:
    """Только owner и regular имеют полный доступ."""
    data = load_user_profile(user_id)
    if not data:
        return False
    return data.get("status") in ("owner", "regular")


def _ensure_profile(user_id: str, tg_name: str = "") -> bool:
    """Создаёт профиль если не существует. Возвращает True если профиль новый."""
    if load_user_profile(user_id):
        return False
    # Определяем статус: владелец → owner, остальные → guest
    raw_uid = user_id.replace("tg_", "")
    is_owner = OWNER_TG_ID and raw_uid.isdigit() and int(raw_uid) == OWNER_TG_ID
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    save_user_profile(user_id, {
        "id":           user_id,
        "name":         tg_name,
        "status":       "owner" if is_owner else "guest",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "last_seen":    datetime.now().strftime("%Y-%m-%d"),
        "sessions_count": 1,
        "guest_message_count": 0,
        "about":        {},
        "preferences":  {"language": "ru"},
        "domain":       {},
    })
    if not is_owner:
        notify_new_user(user_id, tg_name, "web")
    return True
