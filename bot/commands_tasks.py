"""bot/commands_tasks.py — Команды задач и настройки: /task, /tz, /rename, ритуалы."""

from agent import load_user_profile
from agent import save_user_profile
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import OWNER_TG_ID
from bot.helpers import _is_approved, _is_owner, _reply, _user_id


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/rename <user_id> <новое имя> — переименовать пользователя (owner-only).

    Удобно для тестеров: видишь в /users понятные имена вместо подтянутых
    из Telegram. На бизнес-логику не влияет — меняется display-name в профиле.
    """
    if not _is_owner(update.effective_user.id):
        return
    args = (update.message.text or "").strip()
    if args.startswith("/rename"):
        args = args[len("/rename"):].strip()
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(update, "Формат: /rename <user_id> <новое имя>\nПример: /rename tg_12345 Иван (тестер)")
        return
    target_id, new_name = parts[0].strip(), parts[1].strip()
    p = load_user_profile(target_id)
    if not p:
        await _reply(update, f"Пользователь {target_id} не найден.")
        return
    old_name = p.get("name", "—")
    p["name"] = new_name
    save_user_profile(target_id, p)
    await _reply(update, f"✓ {target_id}: «{old_name}» → «{new_name}»")


async def cmd_tz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tz — показывает текущую зону. /tz <IANA-name> — устанавливает."""
    from tools.access_tools import get_user_timezone, set_user_timezone
    tg_id = update.effective_user.id
    user_id = _user_id(tg_id)
    args = (update.message.text or "").strip()
    args = args[3:].strip() if args.startswith("/tz") else args
    if not args:
        cur = get_user_timezone(user_id)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        try:
            now = datetime.now(ZoneInfo(cur)) if cur != "UTC" else datetime.now()
            sample = now.strftime("%H:%M")
        except Exception:
            sample = "?"
        await _reply(update,
            f"Твоя зона: `{cur}`\nСейчас по ней: `{sample}`\n\n"
            f"Поменять: `/tz Asia/Khabarovsk` (или Europe/Moscow, UTC, Europe/Berlin и т.п.)",
            parse_mode="Markdown")
        return
    ok, msg = set_user_timezone(user_id, args)
    await _reply(update, ("✓ " if ok else "✗ ") + msg)


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user_id = _user_id(tg_id)
    if not _is_approved(user_id):
        await _reply(update, "Требуется одобрение.")
        return
    from tools.time_parse import extract_time_and_rest as _etr
    from tools.scheduler import schedule_reminder as _sched
    from tools.access_tools import get_user_timezone as _gut
    args = (update.message.text or "").strip()
    prefix = "/task"
    if args.startswith(prefix):
        args = args[len(prefix):].strip()
    if not args:
        await _reply(update, "Формат: /task <когда> <задача>\nПример: /task завтра 8:00 проверь календарь")
        return
    ok_p, trigger_or_err, prompt = _etr(args, _gut(user_id))
    if not ok_p:
        await _reply(update, trigger_or_err)
        return
    r = _sched(user_id, trigger_or_err, prompt, kind="task")
    if r.get("ok"):
        t = r["task"]
        await _reply(update,
            f"Задача создана!\nID: `{t['id']}`\nКогда: {t['trigger_at']}\nЧто: {t['message'][:120]}",
            parse_mode="Markdown",
        )
    else:
        await _reply(update, f"Ошибка: {r.get('error')}")


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user_id = _user_id(tg_id)
    if not _is_approved(user_id):
        await _reply(update, "Требуется одобрение.")
        return
    from tools.scheduler import list_tasks as _lt
    r = _lt(user_id)
    tasks = r.get("tasks", [])
    if not tasks:
        await _reply(update, "Запланированных задач нет.")
        return
    lines = [f"Задачи ({len(tasks)}):"]
    for t in tasks:
        lines.append(f"  `{t['id']}` — {t['trigger_at'][:16].replace('T', ' ')} — {t['message'][:80]}")
    await _reply(update, "\n".join(lines), parse_mode="Markdown")


async def cmd_task_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user_id = _user_id(tg_id)
    if not _is_approved(user_id):
        await _reply(update, "Требуется одобрение.")
        return
    from tools.scheduler import cancel_reminder as _cancel
    args = (update.message.text or "").replace("/task_cancel", "").strip()
    if not args:
        await _reply(update, "Укажи ID задачи: /task_cancel <id>")
        return
    r = _cancel(user_id, args)
    if r.get("ok"):
        await _reply(update, r["message"])
    else:
        await _reply(update, f"Ошибка: {r.get('error')}")


async def cmd_rituals_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    from tools.rituals import load_rituals as _lr
    from tools import db as _db
    rituals = _lr()
    runs = _db.load_ritual_runs()
    if not rituals:
        await _reply(update, "Ритуалов не найдено.")
        return
    lines = [f"Ритуалы ({len(rituals)}):"]
    for r in rituals:
        run = runs.get(r["name"], {})
        last = run.get("last_run", "—")[:16].replace("T", " ") if run.get("last_run") else "—"
        lines.append(f"  {r['name']} | schedule: {r['schedule']} | last: {last}")
    await _reply(update, "\n".join(lines))


async def cmd_ritual_run_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_user.id):
        return
    import threading
    from web.ritual_runner import _run_ritual_background as _rrb
    rname = " ".join(context.args) if context.args else ""
    if not rname:
        await _reply(update, "Укажи имя ритуала: /ritual_run <name>")
        return
    from tools.rituals import load_rituals as _lr
    rituals = {r["name"]: r for r in _lr()}
    if rname not in rituals:
        await _reply(update, f"Ритуал '{rname}' не найден.")
        return
    user_id = f"tg_{OWNER_TG_ID}" if OWNER_TG_ID else _user_id(update.effective_user.id)
    await _reply(update, f"Запускаю ритуал '{rname}' в фоне...")
    threading.Thread(target=_rrb, args=(rituals[rname], user_id), daemon=True).start()
