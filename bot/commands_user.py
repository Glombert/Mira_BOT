"""bot/commands_user.py — Команды для всех пользователей: вход, Google-интеграции, напоминания, базовые."""

import os
from agent import MEMORY_DIR
from agent import MEMORY_SESSIONS_DIR
from agent import SYSTEM_PROMPT
from agent import WORKSPACE_DIR
from agent import cleanup_temp
from agent import load_user_profile
from agent import mark_blacklist_notified
from agent import notify_new_user
from agent import notify_owner
from agent import save_user_profile
from agent import should_notify_blacklisted
from datetime import datetime
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes
from tools import semantic_memory
from tools.gdrive_tools import exchange_code
from tools.gdrive_tools import gcal_list
from tools.gdrive_tools import gcal_quick_add
from tools.gdrive_tools import gdrive_list
from tools.gdrive_tools import gdrive_read
from tools.gdrive_tools import gdrive_status
from tools.gdrive_tools import get_auth_url
from tools.gdrive_tools import gsheet_create
from tools.gdrive_tools import gsheet_read
from tools.gdrive_tools import is_authorized as gdrive_authorized
from tools.gdrive_tools import is_configured as gdrive_configured
from tools.scheduler import cancel_reminder
from tools.scheduler import list_reminders
from tools.scheduler import schedule_reminder

from bot.config import _MIRA_PUBLIC_URL, logger
from bot.helpers import _is_approved, _is_owner, _reply, _save_session, _user_id
from bot.menu import _help_keyboard


async def _send_session_token(update: Update, tg_id: int, name: str) -> None:
    """Генерит токен, шлёт пользователю с inline-кнопкой «Войти в приложение».

    Кнопка ведёт на /m/auth?code=... — сервер обменивает одноразовый код
    на реальный токен и редиректит в miramobile:// deep link.
    Это предотвращает утечку session token в nginx access-логи и историю браузера.

    Для пользователей без приложения остаётся текстовый токен в кодовом блоке —
    его можно тапнуть для копирования и вставить в любой клиент.
    """
    from web.security import make_session, make_mobile_auth_code, session_signing_key
    token = make_session(session_signing_key(), tg_id, name)
    # Одноразовый код вместо токена в URL — предотвращает утечку в логи
    auth_code = make_mobile_auth_code(token)
    deeplink_url = f"{_MIRA_PUBLIC_URL}/m/auth?code={auth_code}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Войти в приложение", url=deeplink_url)]
    ])
    await _reply(update,
        "Токен сессии (30 дней):\n\n"
        f"`{token}`\n\n"
        "На телефоне нажми кнопку ниже — Мира откроется сама. "
        "Либо вставь токен вручную в поле «У меня есть токен». "
        "Никому не пересылай — он эквивалентен паролю.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отдаёт session-токен для веб/мобильного клиента.

    Альтернатива Telegram Login Widget: на сетях с DPI/RKN-блокировкой
    telegram.org-виджет не грузится, а через бота — работает.
    """
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        await _reply(update, "Команда доступна только одобренным пользователям. Напиши /start.")
        return
    await _send_session_token(update, update.effective_user.id, update.effective_user.first_name or "")


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

    url = get_auth_url(state=user_id)
    if not url:
        await _reply(update, "Не удалось создать ссылку для авторизации.")
        return

    await _reply(update,
        "🔐 *Привязка Google Drive*\n\n"
        "1. Открой ссылку ниже\n"
        "2. Войди в Google-аккаунт и разреши доступ\n"
        "3. Увидишь страницу «✅ Готово!» — всё, Drive привязан\n\n"
        "Если страница не открылась (ошибка «Сервер не найден») — "
        "скопируй адрес из строки браузера и отправь: `/google_auth <адрес>`\n\n"
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

    # Извлекаем код из команды.
    # Можно прислать просто код: /google_auth 4/0AanRRr...
    # Или полный URL из адресной строки после редиректа
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    raw = parts[1].strip() if len(parts) > 1 else ""

    if not raw:
        await _reply(update, "Отправь код или URL после команды: `/google_auth <код>`")
        return

    # Если прислали URL — извлекаем code из query-параметров
    if raw.startswith("http"):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        if codes:
            code = codes[0]
        else:
            await _reply(update, "Не нашёл `code` в URL. Скопируй адрес полностью из строки браузера.")
            return
    else:
        code = raw

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


async def cmd_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ближайшие события календаря."""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        return
    max_r = 10
    args = (update.message.text or "").split()
    if len(args) > 1:
        try:
            max_r = max(1, min(int(args[1]), 50))
        except ValueError:
            pass
    result = gcal_list(user_id, max_results=max_r)
    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return
    events = result.get("events", [])
    if not events:
        await _reply(update, "Календарь пуст — событий не найдено.")
        return
    lines = [f"Ближайшие события ({len(events)}):"]
    for e in events:
        start = e.get("start", "")[:16].replace("T", " ")
        lines.append(f"  {start} — {e.get('summary', '')}")
    await _reply(update, "\n".join(lines))


async def cmd_gcal_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создаёт событие через Quick Add: /gcal_create Встреча с Колей завтра в 15:00"""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        return
    text = (update.message.text or "").strip()
    prefix = "/gcal_create"
    if text.startswith(prefix):
        text = text[len(prefix):].strip()
    if not text:
        await _reply(update, "Напиши: /gcal_create Встреча с Колей завтра в 15:00")
        return
    result = gcal_quick_add(user_id, text)
    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return
    await _reply(update, f"Событие создано: {result.get('summary')}")


async def cmd_gsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Читает Google Sheet: /gsheet <id> [диапазон]"""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        return
    args = (update.message.text or "").split()
    if len(args) < 2:
        await _reply(update, "Укажи ID таблицы: /gsheet <id> [диапазон]")
        return
    sid = args[1]
    rng = args[2] if len(args) > 2 else "A1:Z100"
    result = gsheet_read(user_id, sid, rng)
    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return
    values = result.get("values", [])
    if not values:
        await _reply(update, "Таблица пуста в этом диапазоне.")
        return
    lines = [f"Таблица {sid} ({result.get('rows')} строк):"]
    for row in values[:20]:
        lines.append(" | ".join(str(c)[:40] for c in row))
    if len(values) > 20:
        lines.append(f"... и ещё {len(values) - 20} строк")
    await _reply(update, "\n".join(lines))


async def cmd_gsheet_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создаёт новую Google Таблицу: /gsheet_create Название"""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        return
    text = (update.message.text or "").strip()
    prefix = "/gsheet_create"
    if text.startswith(prefix):
        title = text[len(prefix):].strip()
    else:
        title = "Новая таблица"
    if not title:
        title = "Новая таблица"
    result = gsheet_create(user_id, title)
    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return
    await _reply(update,
        f"Таблица создана: {result.get('title')}\n"
        f"ID: `{result.get('spreadsheet_id')}`\n"
        f"{result.get('url')}",
        parse_mode="Markdown",
    )


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создаёт напоминание: /remind 2026-05-13T05:10 Текст напоминания"""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        await _reply(update, "Напоминания доступны только одобренным пользователям.")
        return
    text = (update.message.text or "").strip()
    prefix = "/remind"
    if text.startswith(prefix):
        text = text[len(prefix):].strip()
    if not text:
        await _reply(update, "Напиши: /remind <ISO-дата> <текст>\nПример: /remind 2026-05-13T05:10 Пора на работу!")
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(update, "Нужны дата/время и текст: /remind 2026-05-13T05:10 Пора на работу!")
        return
    trigger_at, message = parts[0].strip(), parts[1].strip()
    # Позволяем дату без времени: 2026-05-13 → 2026-05-13T09:00:00
    if "T" not in trigger_at and len(trigger_at) == 10:
        trigger_at += "T09:00:00"
    elif "T" not in trigger_at:
        await _reply(update, "Дата должна быть в ISO-формате: 2026-05-13T05:10 или 2026-05-13")
        return
    result = schedule_reminder(user_id, trigger_at, message)
    if not result.get("ok"):
        await _reply(update, f"❌ Ошибка: {result.get('error')}")
        return
    task = result["task"]
    await _reply(update,
        f"✅ Напоминание создано:\n"
        f"ID: `{task['id']}`\n"
        f"Когда: {task['trigger_at']}\n"
        f"Текст: {task['message']}\n\n"
        f"Отменить: /remind_cancel {task['id']}",
        parse_mode="Markdown",
    )


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные напоминания пользователя."""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        await _reply(update, "Напоминания доступны только одобренным пользователям.")
        return
    result = list_reminders(user_id)
    if not result.get("ok"):
        await _reply(update, f"❌ {result.get('error')}")
        return
    reminders = result.get("reminders", [])
    if not reminders:
        await _reply(update, "Активных напоминаний нет.")
        return
    lines = [f"Активные напоминания ({len(reminders)}):"]
    for r in reminders:
        lines.append(f"  `{r['id']}` — {r['trigger_at'][:16].replace('T', ' ')} — {r['message'][:60]}")
    lines.append("\nОтменить: /remind_cancel <id>")
    await _reply(update, "\n".join(lines), parse_mode="Markdown")


async def cmd_remind_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет напоминание: /remind_cancel <id>"""
    user_id = _user_id(update.effective_user.id)
    if not _is_approved(user_id):
        await _reply(update, "Напоминания доступны только одобренным пользователям.")
        return
    text = (update.message.text or "").strip()
    prefix = "/remind_cancel"
    if text.startswith(prefix):
        task_id = text[len(prefix):].strip()
    else:
        task_id = ""
    if not task_id:
        await _reply(update, "Укажи ID напоминания: /remind_cancel <id>\nID можно найти в /reminders.")
        return
    result = cancel_reminder(user_id, task_id)
    if result.get("ok"):
        await _reply(update, result["message"])
    else:
        await _reply(update, f"❌ {result.get('error')}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)

    # Deeplink-payload /start login → шлём токен для мобильного клиента.
    # Так мобильное приложение запускает «Войти через Telegram» одним тапом:
    # tg://resolve?domain=<bot>&start=login открывает чат с этим payload'ом.
    payload = (context.args[0] if context.args else "").strip().lower()
    if payload == "login":
        if not _is_approved(user_id):
            await _reply(update,
                "Привет! Я тебя не помню — сначала нажми /start без параметров, "
                "владелец одобрит, тогда вернёмся к логину.")
            return
        await _send_session_token(update, tg_id, update.effective_user.first_name or "")
        return

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
    from agent import delete_user_profile
    delete_user_profile(user_id)
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
