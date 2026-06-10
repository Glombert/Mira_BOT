"""bot/commands_owner.py — Owner-команды: evolve/reflect, статистика, управление пользователями."""

from agent import approve
from agent import block
from agent import ensure_dev_branch
from agent import get_evolution_stats
from agent import list_backups
from agent import list_users
from agent import load_principles
from agent import load_user_profile
from agent import reflect
from agent import rollback
from agent import save_user_profile
from agent import sync_with_git
from agent import unblock
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import logger
from bot.helpers import (
    _is_owner,
    _load_session,
    _make_alpha,
    _reply,
    _save_session,
    _send_long,
    _user_id,
)


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
    """Генерирует мульти-файл diff и отправляет владельцу для одобрения.

    Мира работает в режиме «исследовать + вернуть diff»: даёт ей read_self,
    list_self, openrouter_list_models, web_search. На write_* блок.
    Возвращённый diff может затрагивать несколько файлов — применит safe_apply.
    """
    from agent import (
        _evolve_build_messages, _evolve_extract_diff, _evolve_make_readonly_agent,
        profile as _profile,
    )
    from tools.diff_tools import parse_multi_diff

    if not ensure_dev_branch():
        await _reply(update, "[!] Не удалось переключиться на mira-dev.")

    principles = load_principles()

    tg_id = update.effective_user.id
    alpha_main = _make_alpha(tg_id, _user_id(tg_id))
    if not alpha_main:
        await _reply(update, "Ошибка создания агента.")
        return

    evolve_agent = _evolve_make_readonly_agent(alpha_main.model_chain, _profile)
    messages = _evolve_build_messages(task, principles)

    try:
        # Мира многораундово читает код и формирует diff. Может занимать 30-90с.
        import asyncio
        response_text = await asyncio.to_thread(evolve_agent.run, messages, 20)
    except Exception as e:
        await _reply(update, f"Ошибка при генерации: {e}")
        logger.error(f"Telegram evolve gen failed: {e}", exc_info=True)
        return

    raw_diff = _evolve_extract_diff(response_text)
    if not raw_diff:
        snippet = response_text[:1000].replace("<", "&lt;").replace(">", "&gt;")
        await _reply(update, f"Мира не вернула diff. Её ответ:\n<pre>{snippet}</pre>",
                     parse_mode="HTML")
        return

    # Парсим diff чтобы показать пользователю краткую сводку
    try:
        changes = parse_multi_diff(raw_diff)
    except ValueError as e:
        await _reply(update, f"Diff не парсится: {e}")
        return

    context.user_data["evolve_diff"] = raw_diff

    # Сводка по затронутым файлам
    file_summary = "\n".join(
        f"  {'➕' if c.action == 'create' else '✏️' if c.action == 'modify' else '❌'} "
        f"{c.action.upper():6} {c.path}"
        for c in changes
    )

    diff_preview = raw_diff[:2800] + ("\n...(обрезано)" if len(raw_diff) > 2800 else "")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Применить", callback_data="evolve_apply"),
        InlineKeyboardButton("❌ Отклонить", callback_data="evolve_reject"),
    ]])
    import html as _html
    await _reply(update,
        f"Затронет <b>{len(changes)}</b> файлов:\n<pre>{_html.escape(file_summary)}</pre>\n\n"
        f"<pre>{_html.escape(diff_preview)}</pre>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


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


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает метрики использования LLM (только owner)."""
    if not _is_owner(update.effective_user.id):
        return
    from tools.metrics_tools import metrics_read as _mr
    days = 1
    args = (update.message.text or "").split()
    if len(args) > 1:
        try:
            days = max(1, min(int(args[1]), 90))
        except ValueError:
            pass
    m = _mr(days)
    if not m.get("ok"):
        await _reply(update, f"Ошибка чтения метрик: {m.get('error')}")
        return
    if m["total_calls"] == 0:
        await _reply(update, f"Нет данных метрик за {days} дн.")
        return

    def _fmt_tok(n: int) -> str:
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000:     return f"{n/1_000:.0f}K"
        return str(n)

    lines = [f"Метрики за {days} дн.:\n"]
    lines.append(f"Вызовов: {m['total_calls']}")
    lines.append(f"Токенов: {_fmt_tok(m['total_tokens'])} (prompt: {_fmt_tok(m['prompt_tokens'])}, completion: {_fmt_tok(m['completion_tokens'])})")
    lines.append(f"Оценка стоимости: ${m['cost_est']:.4f}\n")

    # По моделям
    by_m = sorted(m.get("by_model", {}).items(), key=lambda x: x[1]["cost_est"], reverse=True)
    if by_m:
        lines.append("По моделям:")
        for model, d in by_m[:6]:
            lines.append(f"  {model}: {d['calls']} вызовов, {_fmt_tok(d['prompt_tokens']+d['completion_tokens'])} токенов, ${d['cost_est']:.4f}")

    # По пользователям
    by_u = sorted(m.get("by_user", {}).items(), key=lambda x: x[1]["cost_est"], reverse=True)
    if by_u:
        lines.append("\nПо пользователям:")
        for uid, d in by_u[:10]:
            short = uid.replace("tg_", "")[:12]
            lines.append(f"  {short}: {d['calls']} вызовов, ${d['cost_est']:.4f}")

    await _reply(update, "\n".join(lines))


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
