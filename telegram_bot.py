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


from telegram import (
    Update,
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

from tools.env_guard import check_env_permissions
check_env_permissions()

# ---------------------------------------------------------------------------
# Импорт ядра Mira
# ---------------------------------------------------------------------------
from core import providers as _providers
_providers.init()
from core import memory_crypto
memory_crypto.init()

from agent import notify_owner

from bot.config import TOKEN, logger
from bot.background import post_init
from bot.callbacks import handle_callback
from bot.chat import handle_message
from bot.commands_owner import (
    cmd_approve,
    cmd_blacklist_view,
    cmd_block,
    cmd_evolution_count,
    cmd_evolve,
    cmd_git,
    cmd_kidmode,
    cmd_reflect,
    cmd_release,
    cmd_restart,
    cmd_rollback,
    cmd_stats,
    cmd_unblock,
    cmd_users,
    cmd_versions,
)
from bot.commands_tasks import (
    cmd_rename,
    cmd_ritual_run_tg,
    cmd_rituals_tg,
    cmd_task,
    cmd_task_cancel,
    cmd_tasks,
    cmd_tz,
)
from bot.commands_user import (
    cmd_clear,
    cmd_files,
    cmd_forget,
    cmd_gcal,
    cmd_gcal_create,
    cmd_gdrive,
    cmd_gdrive_get,
    cmd_gdrive_toggle,
    cmd_google_auth,
    cmd_google_login,
    cmd_google_logout,
    cmd_gsheet,
    cmd_gsheet_create,
    cmd_help,
    cmd_login,
    cmd_remind,
    cmd_remind_cancel,
    cmd_reminders,
    cmd_start,
    cmd_stop,
    cmd_whoami,
)
from bot.files import handle_document, handle_photo


async def _global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ловит необработанные исключения из всех handlers, уведомляет владельца."""
    import traceback
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    logger.error(f"Глобальная ошибка бота: {context.error}\n{tb}")
    notify_owner(f"Глобальная ошибка бота: {context.error}"[:500])


def main() -> None:
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_error_handler(_global_error_handler)

    # Команды
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("whoami",   cmd_whoami))
    app.add_handler(CommandHandler("login",    cmd_login))
    app.add_handler(CommandHandler("google_login",  cmd_google_login))
    app.add_handler(CommandHandler("google_auth",   cmd_google_auth))
    app.add_handler(CommandHandler("google_logout", cmd_google_logout))
    app.add_handler(CommandHandler("gdrive",        cmd_gdrive))
    app.add_handler(CommandHandler("gdrive_get",    cmd_gdrive_get))
    app.add_handler(CommandHandler("gdrive_toggle", cmd_gdrive_toggle))
    app.add_handler(CommandHandler("gcal",           cmd_gcal))
    app.add_handler(CommandHandler("gcal_create",     cmd_gcal_create))
    app.add_handler(CommandHandler("gsheet",          cmd_gsheet))
    app.add_handler(CommandHandler("gsheet_create",   cmd_gsheet_create))
    app.add_handler(CommandHandler("remind",         cmd_remind))
    app.add_handler(CommandHandler("reminders",      cmd_reminders))
    app.add_handler(CommandHandler("remind_cancel",  cmd_remind_cancel))
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
    app.add_handler(CommandHandler("stats",          cmd_stats))
    app.add_handler(CommandHandler("approve",         cmd_approve))
    app.add_handler(CommandHandler("block",           cmd_block))
    app.add_handler(CommandHandler("unblock",         cmd_unblock))
    app.add_handler(CommandHandler("kidmode",         cmd_kidmode))
    # Scheduled tasks & rituals
    app.add_handler(CommandHandler("tz",             cmd_tz))
    app.add_handler(CommandHandler("rename",         cmd_rename))
    app.add_handler(CommandHandler("task",           cmd_task))
    app.add_handler(CommandHandler("tasks",          cmd_tasks))
    app.add_handler(CommandHandler("task_cancel",    cmd_task_cancel))
    app.add_handler(CommandHandler("rituals",        cmd_rituals_tg))
    app.add_handler(CommandHandler("ritual_run",     cmd_ritual_run_tg))

    # Файлы и сообщения
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Запускаю polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
