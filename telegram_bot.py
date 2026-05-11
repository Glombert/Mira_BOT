"""
telegram_bot.py — Telegram-интерфейс для Mira.

Запуск:
    python telegram_bot.py

Переменные окружения (.env):
    TELEGRAM_BOT_TOKEN  — токен бота от @BotFather
    OWNER_TELEGRAM_ID   — Telegram user_id владельца (получает dev-права)

Архитектура:
    Каждый пользователь — изолированная сессия.
    История хранится в memory/sessions/tg_{id}.json.
    Workspace — workspace/tg_{id}/.
    Файлы из output/ отправляются автоматически после каждого ответа.
"""

import asyncio
import os
import stat
import json
import base64
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

from telegram import (
    Update,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# Проверка прав .env при старте
def _check_env_permissions() -> None:
    for name in (".env", "../.env"):
        path = os.path.abspath(name)
        if not os.path.exists(path):
            continue
        mode = os.stat(path).st_mode
        if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
            import logging as _log
            _log.getLogger("MiraBot").warning(
                f"БЕЗОПАСНОСТЬ: {path} доступен другим пользователям "
                f"(права: {oct(mode & 0o777)}). Исправь: chmod 600 {path}"
            )

_check_env_permissions()

# ---------------------------------------------------------------------------
# Импорт ядра Mira
# ---------------------------------------------------------------------------
import providers as _providers
_providers.init()
import memory_crypto
memory_crypto.init()
import memory_manager
from tools import semantic_memory
from tools.gdrive_tools import (
    is_configured as gdrive_configured,
    is_authorized as gdrive_authorized,
    get_auth_url,
    exchange_code,
    gdrive_list,
    gdrive_read,
    gdrive_write,
    gdrive_status,
    auto_upload_to_drive,
)

from router   import classify
from conclave import Conclave

# agent.py теперь импортируемый — берём всё нужное
from agent import (
    Agent, Profile, SYSTEM_PROMPT, TOOL_SCHEMAS, execute_tool,
    load_principles, load_user_profile, save_user_profile, get_user_profile_path,
    cleanup_temp, cleanup_expired_guests,
    reflect, rollback, list_backups,
    sync_with_git, ensure_dev_branch, release_to_main,
    list_users, approve, reject, block, unblock, set_status,
    blacklist, unblacklist, delete_user,
    notify_owner, notify_new_user,
    should_notify_blacklisted, mark_blacklist_notified,
    get_evolution_stats,
    MEMORY_DIR, WORKSPACE_DIR, MEMORY_SESSIONS_DIR,
)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_TG_ID  = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
MAX_HISTORY  = 40
MAX_MSG_LEN  = 4000   # Telegram ограничивает сообщения ~4096 символами

os.makedirs("logs", exist_ok=True)
_file_handler = TimedRotatingFileHandler(
    "logs/agent.log",
    when="midnight",
    interval=1,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.suffix = "%Y-%m-%d"
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger("MiraBot")

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

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
    base = SYSTEM_PROMPT
    if data and data.get("child_mode"):
        base += _CHILD_PROMPT_ADDON

    summary = memory_manager.get_summary(user_id, load_user_profile)
    if summary:
        base += f"\n\nЧто ты знаешь об этом пользователе из прошлых разговоров:\n{summary}"

    templates = memory_manager.get_templates_prompt(user_id)
    if templates:
        base += f"\n\n{templates}"

    return base


def _session_path(user_id: str) -> str:
    return os.path.join(MEMORY_SESSIONS_DIR, f"{user_id}.json")


def _load_session(user_id: str) -> list:
    sys_prompt = _system_prompt_for(user_id)
    path = _session_path(user_id)
    msgs = memory_crypto.load_json(path)
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
    os.makedirs(MEMORY_SESSIONS_DIR, exist_ok=True)
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
        memory_crypto.save_json(_session_path(user_id), saveable)
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


async def _reply(update: Update, text: str, **kwargs) -> None:
    """Безопасный reply — работает из message и из callback_query."""
    target = _reply_target(update)
    if target is not None:
        await target.reply_text(text, **kwargs)


async def _send_long(update: Update, text: str, **kwargs) -> None:
    target = _reply_target(update)
    if target is None:
        return
    for part in _split_message(text):
        await target.reply_text(part, **kwargs)


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


# ---------------------------------------------------------------------------
# Меню команд
# ---------------------------------------------------------------------------

BASIC_COMMANDS = [
    BotCommand("start",  "Начать / онбординг"),
    BotCommand("help",   "Список команд"),
    BotCommand("whoami", "Мой профиль"),
    BotCommand("files",  "Мои файлы"),
    BotCommand("gdrive", "Мои файлы на Google Drive"),
    BotCommand("clear",  "Очистить историю"),
    BotCommand("forget", "Сбросить профиль"),
    BotCommand("stop",   "Остановить Конклав"),
]

OWNER_COMMANDS = BASIC_COMMANDS + [
    BotCommand("evolve",          "Изменить код агента"),
    BotCommand("reflect",         "Агент читает свой код"),
    BotCommand("rollback",        "Откат agent.py"),
    BotCommand("versions",        "Резервные копии"),
    BotCommand("release",         "Смержить mira-dev в main"),
    BotCommand("git",             "Закоммитить изменения"),
    BotCommand("users",           "Управление пользователями"),
    BotCommand("blacklist",       "Чёрный список"),
    BotCommand("kidmode",         "Детский режим: /kidmode <user_id> on|off"),
    BotCommand("restart",         "Перезапустить бота"),
    BotCommand("evolution_count", "Статистика эволюций"),
]


def _help_keyboard(is_owner: bool) -> InlineKeyboardMarkup:
    """Inline-кнопки быстрых действий."""
    buttons = [
        [
            InlineKeyboardButton("📁 Мои файлы",    callback_data="cmd_files"),
            InlineKeyboardButton("👤 Профиль",       callback_data="cmd_whoami"),
        ],
        [
            InlineKeyboardButton("🗑 Очистить историю", callback_data="cmd_clear"),
            InlineKeyboardButton("🔁 Сброс профиля",   callback_data="cmd_forget"),
        ],
    ]
    if is_owner:
        buttons.append([
            InlineKeyboardButton("⚡ Reflect",  callback_data="cmd_reflect"),
            InlineKeyboardButton("📦 Rollback", callback_data="cmd_rollback"),
            InlineKeyboardButton("🚀 Release",  callback_data="cmd_release"),
        ])
        buttons.append([
            InlineKeyboardButton("👥 Пользователи", callback_data="cmd_users"),
        ])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Обработчики команд
# ---------------------------------------------------------------------------
# Google Drive OAuth
# ---------------------------------------------------------------------------

async def cmd_google_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает OAuth-авторизацию Google Drive для пользователя."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    if not gdrive_configured():
        await _reply(update, "Google Drive не настроен на сервере. Нужен credentials.json от Google Cloud.")
        return

    if gdrive_authorized(user_id):
        gd = gdrive_status(user_id)
        pd = load_user_profile(user_id)
        auto = "вкл" if (pd and pd.get("preferences", {}).get("gdrive_auto_upload")) else "выкл"
        await _reply(update,
            f"Google Drive уже привязан: {gd.get('email', 'ok')}\n"
            f"Авто-загрузка: {auto} (/gdrive_toggle)\n"
            f"/gdrive — список файлов, /gdrive_get <id> — скачать, /google_logout — отвязать."
        )
        return

    url = get_auth_url()
    if not url:
        await _reply(update, "Не удалось создать ссылку для авторизации.")
        return

    await _reply(update,
        "🔐 *Привязка Google Drive*\n\n"
        "1. Открой ссылку ниже\n"
        "2. Войди в Google-аккаунт и разреши доступ\n"
        "3. После редиректа на `localhost:8080` — скопируй `code` из адресной строки\n"
        "4. Отправь боту: `/google_auth твой_код`\n\n"
        f"[Открыть страницу авторизации Google]({url})",
        parse_mode="Markdown",
    )


async def cmd_google_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обменивает authorization code на токены."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    if not gdrive_configured():
        await _reply(update, "Google Drive не настроен на сервере.")
        return

    # Извлекаем код из команды: /google_auth 4/0AanRRr...
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""

    if not code:
        await _reply(update, "Отправь код после команды: `/google_auth 4/0AanRRr...`")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = exchange_code(user_id, code)

    if result.get("ok"):
        await _reply(update,
            f"✅ Google Drive привязан!\nАккаунт: {result.get('email', 'ok')}\n\n"
            f"Команды:\n"
            f"• /gdrive — посмотреть файлы на Drive\n"
            f"• /gdrive_get <id> — скачать файл с Drive\n"
            f"• /gdrive_toggle — вкл/выкл авто-загрузку входящих файлов на Drive"
        )
    else:
        await _reply(update,
            f"❌ Ошибка: {result.get('error', 'неизвестно')}\n\n"
            f"Возможные причины:\n"
            f"• Код введён с ошибкой (попробуй скопировать точнее)\n"
            f"• Код уже использован (одноразовый)\n"
            f"• Слишком много времени прошло\n\n"
            f"Попробуй ещё раз: /google_login"
        )


async def cmd_google_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отвязывает Google Drive аккаунт."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    from tools.gdrive_tools import _delete_token
    _delete_token(user_id)
    await _reply(update, "Google Drive отвязан. Чтобы привязать заново: /google_login")


async def cmd_gdrive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список файлов на Google Drive пользователя."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    if not gdrive_authorized(user_id):
        await _reply(update, "Сначала привяжи Google Drive: /google_login")
        return

    # Извлекаем путь из команды: /gdrive или /gdrive Папка
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    folder = parts[1].strip() if len(parts) > 1 else "root"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = gdrive_list(user_id, folder)

    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return

    files = result.get("files", [])
    if not files:
        await _reply(update, f"Папка пуста: {folder}")
        return

    lines = [f"📁 *{folder}* ({len(files)}):"]
    for f in files[:30]:
        icon = "📁" if f["type"] == "folder" else "📄"
        size = f" • {f['size']}" if f.get("size") else ""
        lines.append(f"{icon} `{f['name']}`{size}")
        lines.append(f"  id: `{f['id']}`")
    if len(files) > 30:
        lines.append(f"… и ещё {len(files) - 30}")

    await _reply(update, "\n".join(lines), parse_mode="Markdown")


async def cmd_gdrive_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Скачивает файл с Google Drive и отправляет в чат."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    if not gdrive_authorized(user_id):
        await _reply(update, "Сначала привяжи Google Drive: /google_login")
        return

    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    file_id = parts[1].strip() if len(parts) > 1 else ""

    if not file_id:
        await _reply(update, "Укажи ID файла: `/gdrive_get <id>`\nID можно найти через /gdrive.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = gdrive_read(user_id, file_id)

    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return

    # Отправляем файл пользователю
    output_path = os.path.join(WORKSPACE_DIR, user_id, "output", result["file"])
    if os.path.isfile(output_path):
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_path, "rb"),
            caption=f"📥 {result['file']} ({result['size']} bytes)",
        )
    else:
        await _reply(update, f"✅ Файл скачан: `output/{result['file']}` ({result['size']} bytes)",
                     parse_mode="Markdown")


async def cmd_gdrive_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает/выключает авто-загрузку входящих файлов на Google Drive."""
    user_id = _user_id(update.effective_user.id)

    if not _is_approved(user_id):
        await _reply(update, "Google Drive доступен только одобренным пользователям.")
        return

    if not gdrive_authorized(user_id):
        await _reply(update, "Сначала привяжи Google Drive: /google_login")
        return

    profile_data = load_user_profile(user_id)
    prefs = profile_data.get("preferences", {}) if profile_data else {}
    current = prefs.get("gdrive_auto_upload", False)
    new_val = not current
    prefs["gdrive_auto_upload"] = new_val
    if profile_data:
        profile_data["preferences"] = prefs
        save_user_profile(user_id, profile_data)

    if new_val:
        await _reply(update, "✅ Авто-загрузка на Google Drive *включена*.\nВсе входящие файлы будут дублироваться на твой Drive.",
                     parse_mode="Markdown")
    else:
        await _reply(update, "❌ Авто-загрузка на Google Drive *выключена*.\nФайлы остаются только в Telegram. Включить: /gdrive_toggle",
                     parse_mode="Markdown")


# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)

    os.makedirs(MEMORY_DIR, exist_ok=True)
    os.makedirs(MEMORY_SESSIONS_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    cleanup_temp(user_id)

    profile_data = load_user_profile(user_id)
    is_owner = _is_owner(tg_id)

    tg_name = update.effective_user.first_name or ""

    if profile_data is None:
        # Первый запуск
        status = "owner" if is_owner else "guest"
        save_user_profile(user_id, {
            "id": user_id, "name": tg_name, "status": status,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "last_seen":  datetime.now().strftime("%Y-%m-%d"),
            "sessions_count": 1, "about": {}, "preferences": {}, "domain": {},
        })
        if is_owner:
            await _reply(update,
                "Привет! Я Мира. Напиши что-нибудь, начнём работать.",
                reply_markup=_help_keyboard(True),
            )
        else:
            await _reply(update,
                "👋 Привет! Я Мира — персональный AI-помощник.\n\n"
                "Твой доступ пока *гостевой*. Я уже написала владельцу — "
                "он подтвердит твою заявку.\n\n"
                "🔹 *Сейчас тебе доступно:*\n"
                "• 10 пробных сообщений\n"
                "• Разговор, поиск в интернете, чтение файлов\n\n"
                "🔸 *После одобрения откроется:*\n"
                "• Неограниченное общение\n"
                "• Более умная модель (Claude/DeepSeek вместо Flash)\n"
                "• Работа с Excel, запуск Python-кода\n"
                "• Google Drive — хранение и обмен файлами\n"
                "• Сохранение истории и персонализация\n\n"
                "Жди подтверждения!",
                parse_mode="Markdown",
            )
            notify_new_user(user_id, tg_name, "telegram")
    else:
        existing_status = profile_data.get("status", "regular")

        # Проверка чёрного списка
        if existing_status == "blacklisted":
            if should_notify_blacklisted(user_id):
                mark_blacklist_notified(user_id)
                notify_owner(
                    f"Пользователь из чёрного списка пытается войти.\n"
                    f"Имя: {profile_data.get('name', '—')}\nID: {user_id}"
                )
            return  # молчание

        # Отклонённый пользователь
        if existing_status == "rejected":
            await _reply(update,
                "Ранее твой запрос на доступ был отклонён владельцем. "
                "Если это ошибка — обратись к нему напрямую."
            )
            notify_owner(
                f"Отклонённый пользователь пытается войти снова.\n"
                f"Имя: {profile_data.get('name', '—')}\nID: {user_id}",
                user_id=user_id,
                buttons=[
                    {"text": "Одобрить ✅",  "callback_data": f"u_ap_{user_id}"},
                    {"text": "В ЧС 🚫",      "callback_data": f"u_bl_{user_id}"},
                ],
            )
            return

        # Обычный возврат
        if is_owner and existing_status != "owner":
            profile_data["status"] = "owner"
            save_user_profile(user_id, profile_data)
        name = profile_data.get("name") or "снова"
        await _reply(update,
            f"С возвращением, {name}.",
            reply_markup=_help_keyboard(is_owner),
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    is_owner = _is_owner(tg_id)
    text = (
        "Команды:\n"
        "/whoami — профиль\n"
        "/files — файлы\n"
        "/clear — очистить историю\n"
        "/forget — сбросить профиль\n"
        "/stop — остановить Конклав\n"
    )
    if is_owner:
        text += (
            "\n— Разработчик —\n"
            "/evolve <задача> — изменить код\n"
            "/reflect — анализ кода\n"
            "/rollback — откат\n"
            "/versions — резервные копии\n"
            "/release — мердж в main\n"
            "/git [msg] — коммит\n"
            "/users — пользователи\n"
            "/approve <id> — одобрить\n"
            "/block <id> — заблокировать\n"
        )
    await _reply(update,text, reply_markup=_help_keyboard(is_owner))


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update.effective_user.id)
    data = load_user_profile(user_id)
    if not data:
        await _reply(update,"Профиль не найден. Напиши /start.")
        return
    lines = [
        f"👤 *{data.get('name', '—')}*",
        f"Статус: {data.get('status', 'regular')}",
        f"Сессий: {data.get('sessions_count', 0)}",
        f"Последний визит: {data.get('last_seen', '—')}",
    ]
    about = data.get("about", {})
    if about.get("role"):
        lines.append(f"Роль: {about['role']}")
    if about.get("communication_style"):
        lines.append(f"Стиль: {about['communication_style']}")
    if _is_approved(user_id):
        gd = gdrive_status(user_id)
        if gd.get("authorized"):
            auto = " • авто-загрузка вкл" if data.get("preferences", {}).get("gdrive_auto_upload") else ""
            lines.append(f"📎 Google Drive: {gd.get('email', 'привязан')}{auto}")
        elif gdrive_configured():
            lines.append("📎 Google Drive: не привязан. /google_login")
    await _reply(update,"\n".join(lines), parse_mode="Markdown")


async def cmd_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update.effective_user.id)
    lines = []
    for sub in ("inbox", "output"):
        d = os.path.join(WORKSPACE_DIR, user_id, sub)
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if not f.startswith(".")]
            lines.append(f"📁 *{sub}/*: {', '.join(files) if files else 'пусто'}")
    await _reply(update,
        "\n".join(lines) if lines else "Файлов нет.",
        parse_mode="Markdown",
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update.effective_user.id)
    _save_session(user_id, [{"role": "system", "content": SYSTEM_PROMPT}])
    context.user_data.pop("onboarding", None)
    await _reply(update,"История очищена.")


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id(update.effective_user.id)
    path = get_user_profile_path(user_id)
    if os.path.exists(path):
        os.remove(path)
    _save_session(user_id, [{"role": "system", "content": SYSTEM_PROMPT}])
    try:
        semantic_memory.delete_user(user_id)
    except Exception as e:
        logger.warning(f"semantic_memory delete failed: {e}")
    await _reply(update,"Профиль удалён. Напиши /start чтобы познакомиться заново.")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx_conclave = context.user_data.get("conclave")
    if ctx_conclave:
        ctx_conclave.should_stop = True
    await _reply(update,"Стоп — Конклав остановится после текущего шага.")


# ---------------------------------------------------------------------------
# Owner-команды
# ---------------------------------------------------------------------------

async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)
    alpha   = _make_alpha(tg_id, user_id)
    if not alpha:
        await _reply(update,"Ошибка: не удалось создать агента.")
        return
    await _reply(update,"Читаю свой код...")
    msgs = _load_session(user_id)
    reflect(alpha.model_chain, msgs)
    # Последний ответ уже добавлен в msgs
    for m in reversed(msgs):
        if m["role"] == "assistant":
            await _send_long(update, m["content"])
            break
    _save_session(user_id, msgs)


async def cmd_evolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    task = " ".join(context.args) if context.args else ""
    if not task:
        await _reply(update,"Укажи задачу: /evolve <что изменить>")
        return
    await _reply(update,f"Генерирую патч для: «{task}»...")
    # evolve() интерактивная — в Telegram используем упрощённую версию
    # (показываем diff, просим подтверждение через кнопки)
    context.user_data["pending_evolve"] = task
    await _reply(update,
        "⚠️ /evolve в Telegram работает в два шага:\n"
        "1. Генерирую diff\n"
        "2. Присылаю тебе на одобрение\n\n"
        "Подожди...",
    )
    # Запускаем evolve в режиме preview (без интерактивного ввода)
    await _run_evolve_preview(update, context, task)


async def _run_evolve_preview(update, context, task):
    """Генерирует diff и отправляет владельцу для одобрения через кнопки."""
    from agent import read_own_code
    import providers as _providers

    if not ensure_dev_branch():
        await _reply(update,"[!] Не удалось переключиться на mira-dev.")

    principles = load_principles()
    code = read_own_code()
    if not code:
        await _reply(update,"[-] Не удалось прочитать код.")
        return

    tg_id   = update.effective_user.id
    alpha   = _make_alpha(tg_id, _user_id(tg_id))
    if not alpha:
        await _reply(update,"Ошибка создания агента.")
        return

    principles_block = f"\nПринципы:\n{principles}\n" if principles else ""
    prompt = (
        f"Файл agent.py ({len(code.splitlines())} строк). Задача: {task}\n"
        f"{principles_block}\n"
        "Верни unified diff (формат diff -u). Только diff, не весь файл."
    )
    try:
        response = _providers.call(
            alpha.model_chain,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        raw_diff = response.choices[0].message.content.strip()
        if raw_diff.startswith("```"):
            raw_diff = "\n".join(
                l for l in raw_diff.splitlines() if not l.strip().startswith("```")
            ).strip()

        if "@@" not in raw_diff:
            await _reply(update,"Модель не вернула diff. Попробуй другую формулировку.")
            return

        # Сохраняем diff для применения при подтверждении
        context.user_data["evolve_diff"] = raw_diff
        context.user_data["evolve_code"] = code

        # Отправляем diff (обрезаем если слишком длинный)
        diff_preview = raw_diff[:3000] + ("\n...(обрезано)" if len(raw_diff) > 3000 else "")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Применить", callback_data="evolve_apply"),
            InlineKeyboardButton("❌ Отклонить", callback_data="evolve_reject"),
        ]])
        await _reply(update,
            f"```diff\n{diff_preview}\n```",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as e:
        await _reply(update,f"Ошибка: {e}")


async def cmd_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    rollback()
    await _reply(update,"Откат выполнен. Перезапусти бота.")


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перезапускает systemd-сервис mira-bot. Работает только на VPS."""
    if not _is_owner(update.effective_user.id):
        return
    await _reply(update,"Перезапускаю...")
    import subprocess
    try:
        # Запускаем в отдельном процессе — текущий успеет ответить до смерти
        subprocess.Popen(
            ["systemctl", "restart", "mira-bot"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        await _reply(update,f"Ошибка: {e}")


async def cmd_versions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    import io, sys
    buf = io.StringIO()
    old = sys.stdout
    try:
        sys.stdout = buf
        list_backups()
    finally:
        sys.stdout = old
    await _reply(update, buf.getvalue() or "Резервных копий нет.")


async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, мерджим", callback_data="release_confirm"),
        InlineKeyboardButton("❌ Отмена",       callback_data="release_cancel"),
    ]])
    await _reply(update,
        "Смержить mira-dev → main и запушить?",
        reply_markup=keyboard,
    )


async def cmd_git(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    msg = " ".join(context.args) if context.args else "Auto-commit from Telegram"
    await _reply(update,"Синхронизирую...")
    sync_with_git(msg)
    await _reply(update,"Готово.")


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    users = list_users()
    if not users:
        await _reply(update,"Пользователей нет.")
        return
    status_icons = {"owner": "👑", "regular": "✅", "guest": "👤", "rejected": "❌", "blacklisted": "🚫", "blocked": "🚫"}
    buttons = []
    owner_line = ""
    non_owners = [u for u in users if u["status"] != "owner"]
    for u in users:
        if u["status"] == "owner":
            owner_line = f"👑 {u['name'] or u['id']} [owner]\n"
            continue
        icon = status_icons.get(u["status"], "?")
        buttons.append([InlineKeyboardButton(
            f"{icon} {u['name'] or u['id'][:12]}",
            callback_data=f"u_card_{u['id']}"
        )])
    lines = [f"{owner_line}Пользователи ({len(non_owners)}):"]
    for u in non_owners:
        icon = status_icons.get(u["status"], "?")
        lines.append(f"{icon} {u['name'] or u['id']} [{u['status']}]")
    if not buttons:
        await _reply(update,f"{owner_line}Других пользователей нет.")
        return
    await _reply(update,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_blacklist_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    users = [u for u in list_users() if u["status"] in ("blacklisted", "blocked")]
    if not users:
        await _reply(update,"Чёрный список пуст.")
        return
    buttons = []
    lines = [f"Чёрный список ({len(users)}):"]
    for u in users:
        lines.append(f"🚫 {u['name'] or u['id']} — {u['last_seen']}")
        buttons.append([InlineKeyboardButton(
            f"Убрать из ЧС: {u['name'] or u['id'][:12]}",
            callback_data=f"u_ubl_{u['id']}"
        )])
    await _reply(update,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_evolution_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    evo = get_evolution_stats()
    total, success, failed = evo.get("total", 0), evo.get("success", 0), evo.get("failed", 0)
    rate = f"{round(success/total*100)}%" if total else "—"
    await _reply(update,
        f"Счётчик эволюций:\n"
        f"Всего попыток: {total}\n"
        f"Успешных: {success}\n"
        f"Неуспешных: {failed}\n"
        f"Успешность: {rate}"
    )


def _user_card_keyboard(uid: str, status: str, child_mode: bool) -> InlineKeyboardMarkup:
    """Кнопки карточки пользователя — текущий статус не показывается."""
    btns = []
    status_btns = []
    if status != "regular":    status_btns.append(InlineKeyboardButton("Одобрить ✅", callback_data=f"u_ap_{uid}"))
    if status != "guest":      status_btns.append(InlineKeyboardButton("В гости 👤",  callback_data=f"u_gs_{uid}"))
    if status != "rejected":   status_btns.append(InlineKeyboardButton("Отклонить ❌", callback_data=f"u_rj_{uid}"))
    if status not in ("blacklisted", "blocked"):
        status_btns.append(InlineKeyboardButton("В ЧС 🚫", callback_data=f"u_bl_{uid}"))
    else:
        status_btns.append(InlineKeyboardButton("Из ЧС ↩️", callback_data=f"u_ubl_{uid}"))
    for i in range(0, len(status_btns), 2):
        btns.append(status_btns[i:i+2])
    kids_label = "Дет. режим: вкл 🧒" if child_mode else "Дет. режим: выкл 🧒"
    btns.append([InlineKeyboardButton(kids_label, callback_data=f"u_kids_{uid}")])
    btns.append([
        InlineKeyboardButton("Удалить ⚠️", callback_data=f"u_del_{uid}"),
        InlineKeyboardButton("← Назад",    callback_data="u_list"),
    ])
    return InlineKeyboardMarkup(btns)


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    if not context.args:
        await _reply(update,"Использование: /approve <user_id> [имя]")
        return
    uid  = context.args[0]
    name = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    result = approve(uid, name)
    await _reply(update,"Одобрено." if result else "Пользователь не найден.")


async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    if not context.args:
        await _reply(update,"Использование: /block <user_id>")
        return
    result = block(context.args[0])
    await _reply(update,"В чёрный список." if result else "Не найден.")


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    if not context.args:
        await _reply(update,"Использование: /unblock <user_id>")
        return
    result = unblock(context.args[0])
    await _reply(update,"Статус изменён на regular." if result else "Не найден.")


async def cmd_kidmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает/выключает детский режим для указанного пользователя.

    Использование: /kidmode <user_id> on|off
    Telegram не отдаёт возраст — режим включается вручную владельцем.
    """
    if not _is_owner(update.effective_user.id):
        return
    if len(context.args) < 2:
        await _reply(update,"Использование: /kidmode <user_id> on|off")
        return
    uid    = context.args[0]
    toggle = context.args[1].lower()
    if toggle not in ("on", "off"):
        await _reply(update,"Укажи on или off.")
        return
    data = load_user_profile(uid)
    if not data:
        await _reply(update,f"Пользователь {uid} не найден.")
        return
    data["child_mode"] = (toggle == "on")
    save_user_profile(uid, data)
    state = "включён" if data["child_mode"] else "выключен"
    await _reply(update,f"Детский режим {state} для {uid}.")


# ---------------------------------------------------------------------------
# Callback-кнопки (inline keyboards)
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data    = query.data
    tg_id   = query.from_user.id
    user_id = _user_id(tg_id)

    # --- Быстрые команды из меню ---
    cmd_map = {
        "cmd_files":   cmd_files,
        "cmd_whoami":  cmd_whoami,
        "cmd_clear":   cmd_clear,
        "cmd_reflect": cmd_reflect,
        "cmd_rollback":cmd_rollback,
        "cmd_users":   cmd_users,
    }
    if data in cmd_map:
        await cmd_map[data](update, context)
        return

    if data == "cmd_forget":
        path = get_user_profile_path(user_id)
        if os.path.exists(path):
            os.remove(path)
        _save_session(user_id, [{"role": "system", "content": SYSTEM_PROMPT}])
        await query.edit_message_text("Профиль удалён. Напиши /start.")
        return

    # --- Evolve подтверждение ---
    if data == "evolve_apply":
        if not _is_owner(tg_id):
            return
        diff = context.user_data.get("evolve_diff")
        code = context.user_data.get("evolve_code")
        if not diff or not code:
            await query.edit_message_text("Сессия устарела — запусти /evolve снова.")
            return
        from agent import _apply_unified_diff, validate_code, backup_agent, smoke_test, AGENT_FILE
        import tempfile
        ok, new_code = _apply_unified_diff(code, diff)
        if not ok:
            await query.edit_message_text(f"Не удалось применить diff: {new_code}")
            return
        valid, err = validate_code(new_code)
        if not valid:
            await query.edit_message_text(f"Синтаксическая ошибка: {err}")
            return
        backup_path = backup_agent()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(new_code)
            tmp_path = tmp.name
        passed, error = smoke_test(tmp_path)
        os.unlink(tmp_path)
        if not passed:
            await query.edit_message_text(f"Smoke-test не прошёл: {error[:500]}")
            return
        with open(AGENT_FILE, "w", encoding="utf-8") as f:
            f.write(new_code)
        context.user_data.pop("evolve_diff", None)
        context.user_data.pop("evolve_code", None)
        await query.edit_message_text(f"✅ Код обновлён. Бэкап: {backup_path}\nПерезапусти бота.")

    elif data == "evolve_reject":
        context.user_data.pop("evolve_diff", None)
        context.user_data.pop("evolve_code", None)
        await query.edit_message_text("Изменения отклонены.")

    # --- Release подтверждение ---
    elif data == "release_confirm":
        if not _is_owner(tg_id):
            return
        await query.edit_message_text("Мерджу mira-dev → main...")
        ok, err = release_to_main()
        text = "✅ Релиз выполнен. GitHub Actions задеплоит через ~1 мин." if ok else f"❌ Ошибка при релизе:\n{err}"
        await context.bot.send_message(chat_id=query.message.chat_id, text=text)
    elif data == "release_cancel":
        await query.edit_message_text("Отменено.")

    # --- Управление пользователями ---
    elif data == "u_list":
        if not _is_owner(tg_id):
            return
        users = [u for u in list_users() if u["status"] != "owner"]
        status_icons = {"regular": "✅", "guest": "👤", "rejected": "❌", "blacklisted": "🚫", "blocked": "🚫"}
        buttons = [[InlineKeyboardButton(
            f"{status_icons.get(u['status'], '?')} {u['name'] or u['id'][:12]}",
            callback_data=f"u_card_{u['id']}"
        )] for u in users]
        text = f"Пользователи ({len(users)}):" if users else "Других пользователей нет."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

    elif data.startswith("u_card_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        p = load_user_profile(uid)
        if not p:
            await query.edit_message_text("Пользователь не найден.")
            return
        status = p.get("status", "regular")
        child  = p.get("child_mode", False)
        text = (
            f"👤 {p.get('name', '—')}\n"
            f"ID: {uid}\n"
            f"Статус: {status}\n"
            f"Последний визит: {p.get('last_seen', '—')}\n"
            f"Детский режим: {'вкл' if child else 'выкл'}"
        )
        await query.edit_message_text(text, reply_markup=_user_card_keyboard(uid, status, child))

    elif data.startswith("u_ap_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        if approve(uid):
            await query.edit_message_text(f"✅ {p.get('name', uid)} одобрен.")
            # Уведомление пользователю
            raw_uid = uid.replace("tg_", "")
            if raw_uid.isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(raw_uid),
                        text="Твой доступ одобрен!\n\nТеперь тебе доступны:\n"
                             "— общение с Мирой без ограничений\n"
                             "— работа с файлами (отправляй файлы боту)\n"
                             "— веб-интерфейс\n\n"
                             "Напиши что-нибудь — начнём работать."
                    )
                except Exception:
                    pass
        else:
            await query.edit_message_text("Не найден.")

    elif data.startswith("u_rj_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        if reject(uid):
            await query.edit_message_text(f"❌ {p.get('name', uid)} отклонён.")
            raw_uid = uid.replace("tg_", "")
            if raw_uid.isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(raw_uid),
                        text="К сожалению, владелец не одобрил твой доступ. "
                             "Общение с Мирой будет прекращено."
                    )
                except Exception:
                    pass
        else:
            await query.edit_message_text("Не найден.")

    elif data.startswith("u_gs_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        set_status(uid, "guest")
        await query.edit_message_text("👤 Переведён в гости.")

    elif data.startswith("u_bl_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        blacklist(uid)
        await query.edit_message_text(f"🚫 {p.get('name', uid) if p else uid} добавлен в чёрный список.")

    elif data.startswith("u_ubl_"):
        if not _is_owner(tg_id):
            return
        uid = data[6:]
        p = load_user_profile(uid)
        unblacklist(uid)
        await query.edit_message_text(f"↩️ {p.get('name', uid) if p else uid} убран из чёрного списка.")

    elif data.startswith("u_kids_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        p = load_user_profile(uid)
        if p:
            p["child_mode"] = not p.get("child_mode", False)
            save_user_profile(uid, p)
            state = "включён" if p["child_mode"] else "выключен"
            await query.edit_message_text(
                f"🧒 Детский режим {state} для {p.get('name', uid)}.",
                reply_markup=_user_card_keyboard(uid, p.get("status", "regular"), p["child_mode"])
            )

    elif data.startswith("u_del_"):
        if not _is_owner(tg_id):
            return
        uid = data[6:]
        p = load_user_profile(uid)
        name = p.get("name", uid) if p else uid
        await query.edit_message_text(
            f"Удалить {name} и всю его историю? Это необратимо.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Да, удалить ⚠️", callback_data=f"u_cdel_{uid}"),
                InlineKeyboardButton("Отмена",          callback_data=f"u_card_{uid}"),
            ]])
        )

    elif data.startswith("u_cdel_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        delete_user(uid)
        try:
            semantic_memory.delete_user(uid)
        except Exception as e:
            logger.warning(f"semantic_memory delete failed: {e}")
        await query.edit_message_text(f"Пользователь {uid} удалён.")


# ---------------------------------------------------------------------------
# Обработчик документов (входящие файлы)
# ---------------------------------------------------------------------------

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)
    doc     = update.message.document
    fname   = doc.file_name or f"file_{doc.file_id}"

    logger.info(f"handle_document: пользователь {user_id}, файл={fname}, размер={doc.file_size}")

    inbox = os.path.join(WORKSPACE_DIR, user_id, "inbox")
    os.makedirs(inbox, exist_ok=True)
    dest = os.path.join(inbox, fname)

    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(dest)

    logger.info(f"handle_document: файл {fname} сохранён для {user_id}")

    # Авто-загрузка на Google Drive (только для одобренных + авторизованных)
    if _is_approved(user_id) and gdrive_authorized(user_id):
        profile_data = load_user_profile(user_id)
        if profile_data and profile_data.get("preferences", {}).get("gdrive_auto_upload"):
            auto_upload_to_drive(user_id, f"inbox/{fname}")

    await _reply(update,
        f"📥 Файл сохранён: `inbox/{fname}`\n\nМогу прочитать, проанализировать или обработать — скажи что нужно.",
        parse_mode="Markdown",
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает фото: скачивает, отправляет Claude с vision, сохраняет [фото] в истории."""
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)

    profile_data = load_user_profile(user_id)
    if profile_data and profile_data.get("status") == "blocked":
        return

    logger.info(f"handle_photo: пользователь {user_id}, размер фото={len(update.message.photo)}")

    # Скачиваем фото в наилучшем качестве
    photo   = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    raw     = await tg_file.download_as_bytearray()
    b64     = base64.b64encode(bytes(raw)).decode()

    # Формируем vision-контент
    caption = (update.message.caption or "").strip()
    content = []
    if caption:
        content.append({"type": "text", "text": caption})
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
    })

    msgs  = _load_session(user_id)
    alpha = _make_alpha(tg_id, user_id)
    if not alpha:
        await _reply(update,"Провайдеры не настроены.")
        return

    # Проверяем, поддерживает ли модель vision
    model_chain = alpha.model_chain
    supports_vision = any(
        "claude" in entry.get("model", "").lower() or
        "gemini" in entry.get("model", "").lower() or
        "gpt-4" in entry.get("model", "").lower()
        for entry in model_chain
    )
    if not supports_vision:
        logger.warning(f"handle_photo: модель не поддерживает vision, model_chain={model_chain}")
        await _reply(update,
            "Сейчас не могу посмотреть фото — модель с поддержкой изображений недоступна. "
            "Попробуй позже или опиши словами что на снимке."
        )
        return

    msgs.append({"role": "user", "content": content})
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    msgs     = system + the_rest[-MAX_HISTORY:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        answer = alpha.run(msgs)
        await _send_long(update, answer)

        # Сохраняем историю: заменяем image_url на текстовый placeholder
        def _strip_images(m: dict) -> dict:
            c = m.get("content")
            if not isinstance(c, list):
                return m
            texts = [p.get("text", "") for p in c if p.get("type") == "text"]
            placeholder = " ".join(t for t in texts if t).strip() or "[фото]"
            return {**m, "content": placeholder}

        _save_session(user_id, [_strip_images(m) for m in msgs])
        logger.info(f"handle_photo: успешно обработано для {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        err = str(e).lower()
        if any(k in err for k in ("vision", "image", "multimodal", "unsupported")):
            await _reply(update,
                "Сейчас не могу посмотреть фото — модель с поддержкой изображений недоступна. "
                "Попробуй позже или опиши словами что на снимке."
            )
        else:
            await _reply(update,"Что-то пошло не так. Попробуй ещё раз.")


# ---------------------------------------------------------------------------
# Основной обработчик сообщений
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)
    text    = update.message.text or ""

    logger.info(f"handle_message: пользователь {user_id}, длина сообщения={len(text)}")

    # Онбординг
    if context.user_data.get("onboarding"):
        await _handle_onboarding(update, context, tg_id, user_id, text)
        return

    # Проверка статуса
    profile_data = load_user_profile(user_id)
    if profile_data and profile_data.get("status") == "blocked":
        logger.warning(f"handle_message: заблокированный пользователь {user_id} пытается отправить сообщение")
        await _reply(update,"Доступ закрыт.")
        return

    # Гостевой лимит
    if profile_data and profile_data.get("status") == "guest":
        count = profile_data.get("guest_message_count", 0) + 1
        profile_data["guest_message_count"] = count
        save_user_profile(user_id, profile_data)
        if count > 10:
            logger.info(f"handle_message: гость {user_id} исчерпал лимит сообщений")
            await _reply(update,"Лимит сообщений исчерпан. Ожидай одобрения.")
            return
        elif count >= 8:
            await _reply(update,f"(осталось {10 - count} сообщений из 10)")

    msgs   = _load_session(user_id)
    alpha  = _make_alpha(tg_id, user_id)
    conc   = _make_conclave(tg_id, user_id)
    context.user_data["conclave"] = conc

    msgs.append({"role": "user", "content": text})
    # trim
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    msgs     = system + the_rest[-MAX_HISTORY:]

    # Семантический поиск по прошлым разговорам (Этап v1.3).
    # Augment-блок добавляем только в copy для LLM — в msgs не сохраняем.
    semantic_augment = ""
    try:
        matches = semantic_memory.search(user_id, text, top_k=5)
        semantic_augment = semantic_memory.format_for_prompt(matches)
    except Exception as e:
        logger.warning(f"semantic_memory search failed: {e}")

    def _augmented(orig: list) -> list:
        if not semantic_augment:
            return orig
        out = list(orig)
        if out and out[0].get("role") == "system":
            out[0] = {**out[0], "content": out[0]["content"] + "\n\n" + semantic_augment}
        return out

    task_type = classify(text, alpha.model_chain if alpha else [])
    ts_before = datetime.now().timestamp()

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    _EXECUTOR_FOR = {
        "search":  "scout",
        "code":    "coder",
        "complex": "coder",
    }

    try:
        if task_type in _EXECUTOR_FOR and alpha:
            executor = _EXECUTOR_FOR[task_type]
            # Стартовое сообщение убрано — первый прогресс от Конклава его заменяет
            loop    = asyncio.get_running_loop()
            chat_id = update.effective_chat.id

            def _progress(text: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(chat_id=chat_id, text=text),
                    loop,
                )

            conc.on_progress = _progress
            raw = await asyncio.to_thread(conc.run_with_qa, text, executor)

            presentation = (
                f"Специалисты выполнили задачу. Представь результат:\n\n{raw}"
            )
            sys_with_semantic = SYSTEM_PROMPT + ("\n\n" + semantic_augment if semantic_augment else "")
            # Включаем последние 12 не-системных сообщений чтобы Альфа
            # помнила контекст разговора при подаче результата Конклава.
            recent = [m for m in msgs if m.get("role") != "system"][-12:]
            alpha_msgs = [
                {"role": "system",    "content": sys_with_semantic},
                *recent,
                {"role": "assistant", "content": "[передала специалистам]"},
                {"role": "user",      "content": presentation},
            ]
            answer = _providers.call(
                alpha.model_chain, alpha_msgs, temperature=0.7
            ).choices[0].message.content
            msgs.append({"role": "assistant", "content": answer})
        elif alpha:
            answer = alpha.run(_augmented(msgs))
        else:
            await _reply(update,"Провайдеры не настроены.")
            return

        await _send_long(update, answer)
        await _send_output_files(context, update.effective_chat.id, user_id, ts_before)
        _save_session(user_id, msgs)

        # Фоновые задачи памяти — не блокируют ответ
        model_chain = alpha.model_chain if alpha else []
        msgs_snapshot = list(msgs)
        user_text     = text
        bot_answer    = answer

        def _memory_tasks():
            # 1. Семантическая память — индексируем оба сообщения
            try:
                semantic_memory.index_message(user_id, "user", user_text)
                if bot_answer:
                    semantic_memory.index_message(user_id, "assistant", bot_answer)
            except Exception as e:
                logger.warning(f"semantic_memory index failed: {e}")

            if not model_chain:
                return
            # 2. Суммаризация если история длинная
            updated = memory_manager.maybe_summarize(
                user_id, msgs_snapshot, model_chain,
                load_user_profile, save_user_profile,
            )
            if updated is not msgs_snapshot:
                _save_session(user_id, updated)

            # 3. Обновление профиля новыми фактами
            memory_manager.update_user_profile(
                user_id, msgs_snapshot, model_chain,
                load_user_profile, save_user_profile,
            )

        memory_manager.run_background(_memory_tasks)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        await _reply(update,"Что-то пошло не так. Попробуй снова.")
        if msgs and msgs[-1]["role"] == "user":
            msgs.pop()


async def _handle_onboarding(update, context, tg_id, user_id, text):
    """Онбординг через диалог в Telegram."""
    hist = context.user_data.get("onboarding_history", [])
    hist.append({"role": "user", "content": text})

    alpha = _make_alpha(tg_id, user_id)
    if not alpha:
        context.user_data.pop("onboarding", None)
        return

    try:
        response = _providers.call(alpha.model_chain, hist, temperature=0.7)
        reply = response.choices[0].message.content
        hist.append({"role": "assistant", "content": reply})
        context.user_data["onboarding_history"] = hist

        await _reply(update,reply)

        if "Принято" in reply or "Начинаем" in reply or len(hist) >= 10:
            # Завершаем онбординг — структурируем профиль
            dialog = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in hist if m["role"] in ("user", "assistant")
            )
            today = datetime.now().strftime("%Y-%m-%d")
            struct_prompt = (
                f"Создай JSON-профиль пользователя по диалогу.\n"
                f"Верни ТОЛЬКО JSON.\n\nДиалог:\n{dialog}\n\n"
                f'{{"id":"{user_id}","name":"имя","created_at":"{today}",'
                f'"last_seen":"{today}","sessions_count":1,'
                f'"status":"{"owner" if _is_owner(tg_id) else "regular"}",'
                f'"about":{{"role":"...","communication_style":"..."}},'
                f'"preferences":{{"language":"ru"}},"domain":{{}},"notes":[]}}'
            )
            try:
                r = _providers.call(
                    alpha.model_chain,
                    [{"role": "user", "content": struct_prompt}],
                    temperature=0.1,
                )
                raw = r.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
                data = json.loads(raw)
            except Exception:
                data = {
                    "id": user_id, "name": user_id.replace("tg_", ""),
                    "created_at": today, "last_seen": today, "sessions_count": 1,
                    "status": "owner" if _is_owner(tg_id) else "regular",
                    "about": {}, "preferences": {}, "domain": {}, "notes": [],
                }
            save_user_profile(user_id, data)
            context.user_data.pop("onboarding", None)
            context.user_data.pop("onboarding_history", None)
            await _reply(update,
                "Профиль сохранён. Можем начинать.",
                reply_markup=_help_keyboard(_is_owner(tg_id)),
            )
    except Exception as e:
        logger.error(f"Онбординг: {e}")
        await _reply(update,"Ошибка API. Попробуй снова.")


# ---------------------------------------------------------------------------
# Запуск бота
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    """Устанавливает меню команд при старте бота и чистит просроченных гостей."""
    # Базовые команды для всех
    await app.bot.set_my_commands(BASIC_COMMANDS, scope=BotCommandScopeDefault())
    # Расширенные для владельца
    if OWNER_TG_ID:
        try:
            await app.bot.set_my_commands(
                OWNER_COMMANDS,
                scope=BotCommandScopeChat(chat_id=OWNER_TG_ID),
            )
        except Exception as e:
            logger.warning(f"Не удалось установить owner-меню: {e}")

    # Очистка просроченных гостей (старше 3 дней)
    try:
        expired = cleanup_expired_guests()
        if expired:
            logger.info(f"При старте удалено просроченных гостей: {expired}")
    except Exception as e:
        logger.warning(f"cleanup_expired_guests упал: {e}")

    logger.info("Бот запущен. Команды установлены.")


def main() -> None:
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("whoami",   cmd_whoami))
    app.add_handler(CommandHandler("google_login",  cmd_google_login))
    app.add_handler(CommandHandler("google_auth",   cmd_google_auth))
    app.add_handler(CommandHandler("google_logout", cmd_google_logout))
    app.add_handler(CommandHandler("gdrive",        cmd_gdrive))
    app.add_handler(CommandHandler("gdrive_get",    cmd_gdrive_get))
    app.add_handler(CommandHandler("gdrive_toggle", cmd_gdrive_toggle))
    app.add_handler(CommandHandler("files",    cmd_files))
    app.add_handler(CommandHandler("clear",    cmd_clear))
    app.add_handler(CommandHandler("forget",   cmd_forget))
    app.add_handler(CommandHandler("stop",     cmd_stop))
    # Owner
    app.add_handler(CommandHandler("reflect",  cmd_reflect))
    app.add_handler(CommandHandler("evolve",   cmd_evolve))
    app.add_handler(CommandHandler("rollback", cmd_rollback))
    app.add_handler(CommandHandler("versions", cmd_versions))
    app.add_handler(CommandHandler("restart",  cmd_restart))
    app.add_handler(CommandHandler("release",  cmd_release))
    app.add_handler(CommandHandler("git",      cmd_git))
    app.add_handler(CommandHandler("users",           cmd_users))
    app.add_handler(CommandHandler("blacklist",       cmd_blacklist_view))
    app.add_handler(CommandHandler("evolution_count", cmd_evolution_count))
    app.add_handler(CommandHandler("approve",         cmd_approve))
    app.add_handler(CommandHandler("block",           cmd_block))
    app.add_handler(CommandHandler("unblock",         cmd_unblock))
    app.add_handler(CommandHandler("kidmode",         cmd_kidmode))

    # Файлы и сообщения
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Запускаю polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
