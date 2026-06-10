"""bot/menu.py — Меню команд бота (/help, списки BotCommand)."""

from telegram import BotCommand
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup



BASIC_COMMANDS = [
    BotCommand("start",  "Начать / онбординг"),
    BotCommand("help",   "Список команд"),
    BotCommand("whoami", "Мой профиль"),
    BotCommand("login",  "Токен для веб/мобильного клиента"),
    BotCommand("tz",     "Часовой пояс: /tz или /tz Asia/Khabarovsk"),
    BotCommand("rename", "Переименовать пользователя (owner): /rename <id> <имя>"),
    BotCommand("files",  "Мои файлы"),
    BotCommand("gdrive", "Мои файлы на Google Drive"),
    BotCommand("gcal",   "Мой календарь"),
    BotCommand("gsheet", "Читать Google Таблицу"),
    BotCommand("remind", "Создать напоминание"),
    BotCommand("reminders", "Мои напоминания"),
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
    BotCommand("task",            "Отложить задачу Мире"),
    BotCommand("tasks",           "Список задач"),
    BotCommand("task_cancel",     "Отменить задачу"),
    BotCommand("rituals",         "Список ритуалов"),
    BotCommand("ritual_run",      "Запустить ритуал"),
    BotCommand("restart",         "Перезапустить бота"),
    BotCommand("evolution_count", "Статистика эволюций"),
    BotCommand("stats",           "Метрики использования LLM"),
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
