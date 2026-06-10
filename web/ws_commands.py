"""web/ws_commands.py — обработчики WS-сообщений type=command и type=profile_save.

Каждая cmd-ветка изолирована от состояния соединения — ей достаточно
websocket + user_id/tg_id (+ флаги owner/approved).
"""

import os
import asyncio
import logging
import threading
from datetime import datetime

from fastapi import WebSocket

from agent import Agent, Profile, WORKSPACE_DIR, load_user_profile, save_user_profile
from tools import semantic_memory
from tools.gdrive_tools import (
    is_configured as gdrive_configured,
    is_authorized as gdrive_authorized,
    get_auth_url, gdrive_list, gdrive_read, gdrive_status,
    gcal_list, gcal_quick_add, gsheet_read, gsheet_create,
)
from tools.scheduler import schedule_reminder, list_reminders, cancel_reminder, list_tasks
from tools.rituals import load_rituals
from web.deps import OWNER_TG_ID
from web.meta import mira_version
from web.sessions import (
    MANNER_TRAITS, _is_approved, _load_session, _save_session, _system_prompt_for,
)
from web.panels import _collect_backups_data
from web.ritual_runner import _run_ritual_background
from web.ws_protocol import (
    ProfileDataMessage, ProfileData, Files, FileEntry, UsersList, UserEntry,
    PermissionsUpdate, GdriveAuthUrl, ProfileSaved,
    MetricsData, MetricsModelStat, MetricsDayStat, RitualsData, RitualEntry,
    RemindersData, ReminderEntry, TasksData, TaskEntry, ws_payload as _wsp,
)

logger = logging.getLogger("MiraWeb")


async def _ws_profile_save(websocket: WebSocket, data: dict, user_id: str) -> None:
    """WS type=profile_save: анкета пользователя (Aurora-профиль)."""
    _f = data.get("form", {}) or {}
    p = load_user_profile(user_id) or {}
    form = p.get("form", {}) or {}
    form["addressing"] = str(_f.get("addressing", ""))[:80]
    form["address_form"] = _f.get("address_form") if _f.get("address_form") in ("ты", "вы") else ""
    form["manner"] = [m for m in (_f.get("manner") or []) if m in MANNER_TRAITS][:8]
    form["origin"] = str(_f.get("origin", ""))[:120]
    form["occupation"] = str(_f.get("occupation", ""))[:120]
    form["notes"] = str(_f.get("notes", ""))[:600]
    form["onboarded"] = True
    p["form"] = form
    # имя из «как обращаться», если задано (для отображения)
    if form["addressing"]:
        p["name"] = form["addressing"]
    save_user_profile(user_id, p)
    # часовой пояс — отдельной валидацией
    _tzv = str(_f.get("timezone", "")).strip()
    if _tzv:
        try:
            from tools.access_tools import set_user_timezone
            set_user_timezone(user_id, _tzv)
        except Exception as e:
            logger.warning(f"profile_save tz: {e}")
    # обновляем системный промпт активной сессии (персона применится сразу)
    try:
        _sess = _load_session(user_id)
        if _sess and _sess[0].get("role") == "system":
            _sess[0] = {"role": "system", "content": _system_prompt_for(user_id)}
            _save_session(user_id, _sess)
    except Exception as e:
        logger.warning(f"profile_save session refresh: {e}")
    logger.info(f"profile_save: {user_id} onboarded manner={form['manner']}")
    # ack отдельным типом — не сыплем в чат
    await websocket.send_json(_wsp(ProfileSaved()))


async def _ws_command(websocket: WebSocket, data: dict, *, user_id: str, tg_id: int,
                      is_owner_ws: bool, is_approved_ws: bool) -> None:
    """WS type=command: меню, интеграции (GDrive/GCal/GSheets), owner-панели.

    Вынесено из endpoint chat(): каждая cmd-ветка изолирована от состояния
    соединения — ей достаточно websocket + user_id/tg_id.
    """
    cmd = data.get("cmd", "")
    logger.info(f"WS command: {user_id} → {cmd}")
    if cmd == "clear":
        _save_session(user_id, [{"role": "system", "content": _system_prompt_for(user_id)}])
        await websocket.send_json({"type": "system", "content": "История очищена."})

    elif cmd == "whoami":
        p = load_user_profile(user_id) or {}
        about = p.get("about", {})
        lines = [f"Имя: {p.get('name', '—')}",
                 f"Статус: {p.get('status', 'regular')}"]
        if about.get("role"):    lines.append(f"Роль: {about['role']}")
        if about.get("project"): lines.append(f"Проект: {about['project']}")
        summary = p.get("conversation_summary", "")
        if summary: lines.append(f"\nЧто Мира знает о тебе:\n{summary[:400]}")
        if _is_approved(user_id):
            gd = gdrive_status(user_id)
            if gd.get("authorized"):
                lines.append(f"Google Drive: {gd.get('email', 'привязан')}")
            elif gdrive_configured():
                lines.append("Google Drive: не привязан")
        await websocket.send_json({"type": "system", "content": "\n".join(lines)})

    elif cmd == "profile_data":
        # Структурированный профиль для экрана «Профиль» (Aurora).
        p = load_user_profile(user_id) or {}
        about = p.get("about", {}) or {}
        try:
            from tools.access_tools import get_user_timezone
            _tz = get_user_timezone(user_id) or ""
        except Exception:
            _tz = ""
        _gd = gdrive_status(user_id) if _is_approved(user_id) else {}
        try:
            _mem = semantic_memory.count(user_id)
        except Exception:
            _mem = 0
        try:
            _conv = sum(1 for m in (_load_session(user_id) or [])
                        if m.get("role") == "user")
        except Exception:
            _conv = 0
        _role = "owner" if is_owner_ws else (p.get("status") or "regular")
        _form = p.get("form", {}) or {}
        try:
            _days = (datetime.now() - datetime.strptime(
                p.get("created_at", "")[:10], "%Y-%m-%d")).days
        except Exception:
            _days = 0
        # Анкета = что Мира знает. Поля пользователя (form) приоритетны,
        # иначе подставляем выученное Мирой (about).
        _addressing = _form.get("addressing") or p.get("name", "")
        _occupation = _form.get("occupation") or about.get("role", "")
        _origin = _form.get("origin") or about.get("location", "")
        _filled_by_mira = []
        if not _form.get("occupation") and about.get("role"):
            _filled_by_mira.append("occupation")
        if not _form.get("origin") and about.get("location"):
            _filled_by_mira.append("origin")
        await websocket.send_json(_wsp(ProfileDataMessage(profile=ProfileData(
            id=user_id,
            name=p.get("name", ""),
            role=_role,
            status=p.get("status", "regular"),
            timezone=_tz,
            telegram=p.get("telegram", "") or p.get("username", ""),
            about_role=about.get("role", ""),
            about_project=about.get("project", ""),
            summary=(p.get("conversation_summary", "") or "")[:600],
            gdrive_linked=bool(_gd.get("authorized")),
            gdrive_email=_gd.get("email", "") if _gd.get("authorized") else "",
            memory_facts=_mem,
            conversations=_conv,
            days_together=max(_days, 0),
            # анкета (form пользователя + выученное Мирой)
            onboarded=bool(_form.get("onboarded")),
            addressing=_addressing,
            address_form=_form.get("address_form", ""),
            manner=_form.get("manner", []) or [],
            origin=_origin,
            occupation=_occupation,
            notes=_form.get("notes", ""),
            manner_options=MANNER_TRAITS,
            filled_by_mira=_filled_by_mira,
            version=mira_version(),
        ))))

    elif cmd == "files":
        files = []
        for subdir in ("inbox", "output"):
            d = os.path.join(WORKSPACE_DIR, user_id, subdir)
            if os.path.isdir(d):
                for fname in sorted(os.listdir(d)):
                    fpath = os.path.join(d, fname)
                    if os.path.isfile(fpath) and not fname.startswith("."):
                        files.append({
                            "name": fname,
                            "dir":  subdir,
                            "size": os.path.getsize(fpath),
                        })
        await websocket.send_json(_wsp(Files(files=[FileEntry(**f) for f in files])))

    elif cmd == "forget":
        from agent import delete_user_profile
        delete_user_profile(user_id)
        _save_session(user_id, [{"role": "system", "content": _system_prompt_for(user_id)}])
        try:
            semantic_memory.delete_user(user_id)
        except Exception as e:
            logger.warning(f"semantic_memory delete: {e}")
        await websocket.send_json({"type": "system", "content": "Профиль и история сброшены."})

    # --- Google Drive ---
    elif cmd == "gdrive_login":
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Google Drive доступен только одобренным пользователям."})
        elif not gdrive_configured():
            await websocket.send_json({"type": "system", "content": "Google Drive не настроен на сервере."})
        elif gdrive_authorized(user_id):
            gd = gdrive_status(user_id)
            await websocket.send_json({"type": "system", "content": f"Google Drive уже привязан: {gd.get('email', 'ok')}\n/gdrive — список файлов."})
        else:
            url = get_auth_url(state=user_id)
            if url:
                await websocket.send_json(_wsp(GdriveAuthUrl(url=url)))
            else:
                await websocket.send_json({"type": "system", "content": "Не удалось создать ссылку для авторизации."})

    elif cmd == "gdrive_status":
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        elif not gdrive_authorized(user_id):
            await websocket.send_json({"type": "system", "content": "Google Drive не привязан. Нажми «Привязать Drive» чтобы начать."})
        else:
            gd = gdrive_status(user_id)
            await websocket.send_json({"type": "system", "content": f"Google Drive: {gd.get('email', 'привязан')}"})

    elif cmd.startswith("gdrive_list"):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        elif not gdrive_authorized(user_id):
            await websocket.send_json({"type": "system", "content": "Сначала привяжи Google Drive."})
        else:
            folder = cmd[11:].strip() or "root"
            result = gdrive_list(user_id, folder)
            if result.get("ok"):
                files = result.get("files", [])
                if not files:
                    await websocket.send_json({"type": "system", "content": f"Папка пуста: {folder}"})
                else:
                    lines = [f"Google Drive · {folder} ({len(files)})"]
                    for f in files[:20]:
                        icon = "📁" if f["type"] == "folder" else "📄"
                        size = f" · {f['size']}" if f.get("size") else ""
                        lines.append(f"{icon} {f['name']}{size}")
                        lines.append(f"  id: {f['id']}")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            else:
                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    elif cmd.startswith("gdrive_get "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        elif not gdrive_authorized(user_id):
            await websocket.send_json({"type": "system", "content": "Сначала привяжи Google Drive."})
        else:
            file_id = cmd[10:].strip()
            if not file_id:
                await websocket.send_json({"type": "system", "content": "Укажи ID файла: gdrive_get <id>"})
            else:
                result = gdrive_read(user_id, file_id)
                if result.get("ok"):
                    fname = result.get("file", "file")
                    await websocket.send_json({"type": "system", "content": f"Файл скачан в output/: {fname} ({result.get('size', 0)} bytes)"})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    # --- Google Calendar ---
    elif cmd == "gcal" or cmd.startswith("gcal "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            parts = cmd.split()
            n = 10
            if len(parts) > 1:
                try: n = max(1, min(int(parts[1]), 50))
                except ValueError: pass
            result = gcal_list(user_id, max_results=n)
            if result.get("ok"):
                events = result.get("events", [])
                if not events:
                    await websocket.send_json({"type": "system", "content": "Календарь пуст."})
                else:
                    lines = [f"Ближайшие события ({len(events)})"]
                    for e in events:
                        start = e.get("start", "")[:16].replace("T", " ")
                        lines.append(f"  {start} — {e.get('summary', '')}")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            else:
                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    elif cmd.startswith("gcal_create "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            text = cmd[12:].strip()
            if not text:
                await websocket.send_json({"type": "system", "content": "Напиши: gcal_create Встреча с Колей завтра в 15:00"})
            else:
                result = gcal_quick_add(user_id, text)
                if result.get("ok"):
                    await websocket.send_json({"type": "system", "content": f"Событие создано: {result.get('summary')}"})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    # --- Google Sheets ---
    elif cmd.startswith("gsheet "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            args = cmd[7:].strip().split()
            if not args:
                await websocket.send_json({"type": "system", "content": "Укажи ID таблицы: gsheet <id> [диапазон]"})
            else:
                sid, rng = args[0], args[1] if len(args) > 1 else "A1:Z100"
                result = gsheet_read(user_id, sid, rng)
                if result.get("ok"):
                    values = result.get("values", [])
                    if not values:
                        await websocket.send_json({"type": "system", "content": "Таблица пуста."})
                    else:
                        lines = [f"Таблица ({result.get('rows', 0)} строк)"]
                        for row in values[:20]:
                            lines.append(" | ".join(str(c)[:40] for c in row))
                        await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    elif cmd.startswith("gsheet_create "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            title = cmd[14:].strip() or "Новая таблица"
            result = gsheet_create(user_id, title)
            if result.get("ok"):
                await websocket.send_json({"type": "system", "content": f"Таблица создана: {result.get('title')}\n{result.get('url')}"})
            else:
                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    # --- Reminders ---
    elif cmd.startswith("remind "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            args = cmd[7:].strip().split(maxsplit=1)
            if len(args) < 2:
                await websocket.send_json({"type": "system", "content": "Формат: remind <ISO-дата> <текст>\nПример: remind 2026-05-13T05:10 Пора на работу!"})
            else:
                trigger_at = args[0]
                if "T" not in trigger_at and len(trigger_at) == 10:
                    trigger_at += "T09:00:00"
                result = schedule_reminder(user_id, trigger_at, args[1])
                if result.get("ok"):
                    t = result["task"]
                    await websocket.send_json({"type": "system", "content": f"Напоминание создано!\nID: {t['id']}\nКогда: {t['trigger_at']}\nТекст: {t['message']}"})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    elif cmd == "reminders":
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            result = list_reminders(user_id)
            if result.get("ok"):
                reminders = result.get("reminders", [])
                if not reminders:
                    await websocket.send_json({"type": "system", "content": "Активных напоминаний нет."})
                else:
                    lines = [f"Напоминания ({len(reminders)})"]
                    for r in reminders:
                        lines.append(f"  {r['id']} — {r['trigger_at'][:16].replace('T', ' ')} — {r['message'][:60]}")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            else:
                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    elif cmd.startswith("remind_cancel "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            task_id = cmd[14:].strip()
            if not task_id:
                await websocket.send_json({"type": "system", "content": "Укажи ID: remind_cancel <id>"})
            else:
                result = cancel_reminder(user_id, task_id)
                if result.get("ok"):
                    await websocket.send_json({"type": "system", "content": result["message"]})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

    # --- Scheduled tasks (/task) ---
    elif cmd.startswith("task_cancel "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            t = cmd[12:].strip()
            if not t:
                await websocket.send_json({"type": "system", "content": "Укажи ID: task_cancel <id>"})
            else:
                r = cancel_reminder(user_id, t)
                if r.get("ok"):
                    await websocket.send_json({"type": "system", "content": r["message"]})
                else:
                    await websocket.send_json({"type": "system", "content": f"Ошибка: {r.get('error')}"})

    elif cmd == "tasks":
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            r = list_tasks(user_id)
            tasks = r.get("tasks", [])
            if not tasks:
                await websocket.send_json({"type": "system", "content": "Запланированных задач нет."})
            else:
                lines = [f"Задачи ({len(tasks)}):"]
                for t in tasks:
                    lines.append(f"  {t['id']} — {t['trigger_at'][:16].replace('T', ' ')} — {t['message'][:80]}")
                await websocket.send_json({"type": "system", "content": "\n".join(lines)})

    elif cmd == "reminders_data":
        # Структурный список напоминаний для экрана Aurora.
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            try:
                r = list_reminders(user_id)
                entries = [
                    ReminderEntry(
                        id=str(t.get("id", "")),
                        title=t.get("message", ""),
                        at=t.get("trigger_at", ""),
                        done=(t.get("status") not in ("pending", None)),
                    )
                    for t in (r.get("reminders") or [])
                ]
                await websocket.send_json(_wsp(RemindersData(reminders=entries)))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"reminders_data: {e}"})

    elif cmd == "tasks_data":
        # Структурный список задач для экрана Aurora.
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            try:
                r = list_tasks(user_id)
                entries = [
                    TaskEntry(
                        id=str(t.get("id", "")),
                        message=t.get("message", ""),
                        at=t.get("trigger_at", ""),
                        status=t.get("status", "pending"),
                    )
                    for t in (r.get("tasks") or [])
                ]
                await websocket.send_json(_wsp(TasksData(tasks=entries)))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"tasks_data: {e}"})

    # --- /tz: показать или установить часовую зону ---
    elif cmd == "tz" or cmd.startswith("tz "):
        from tools.access_tools import get_user_timezone, set_user_timezone
        arg = cmd[3:].strip() if cmd.startswith("tz ") else ""
        if not arg:
            cur = get_user_timezone(user_id)
            await websocket.send_json({
                "type": "system",
                "content": (
                    f"Твоя зона: {cur}\n"
                    f"Поменять: tz Asia/Khabarovsk (или Europe/Moscow, UTC, Europe/Berlin)"
                ),
            })
        else:
            ok, msg = set_user_timezone(user_id, arg)
            await websocket.send_json({"type": "system", "content": ("✓ " if ok else "✗ ") + msg})

    # --- /rename (owner-only): переименовать другого пользователя ---
    elif cmd.startswith("rename "):
        is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
            rest = cmd[7:].strip()
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                await websocket.send_json({"type": "system", "content": "Формат: rename <user_id> <новое имя>"})
            else:
                # load_user_profile/save_user_profile уже на top-level (L48).
                # Локальный import шадовил бы их в ВСЕЙ функции chat() — то же
                # самое произошло с Profile в прошлый раз.
                target_id, new_name = parts[0].strip(), parts[1].strip()
                p = load_user_profile(target_id)
                if not p:
                    await websocket.send_json({"type": "system", "content": f"Пользователь {target_id} не найден"})
                else:
                    old_name = p.get("name", "—")
                    p["name"] = new_name
                    save_user_profile(target_id, p)
                    await websocket.send_json({"type": "system", "content": f"✓ {target_id}: «{old_name}» → «{new_name}»"})

    elif cmd.startswith("task "):
        if not _is_approved(user_id):
            await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
            rest = cmd[5:].strip()
            if not rest:
                await websocket.send_json({"type": "system", "content": "Формат: task <когда> <задача>\nПример: task завтра 8:00 проверь календарь"})
            else:
                from tools.time_parse import extract_time_and_rest
                from tools.access_tools import get_user_timezone
                ok_parsed, trigger_or_err, prompt = extract_time_and_rest(rest, get_user_timezone(user_id))
                if not ok_parsed:
                    await websocket.send_json({"type": "system", "content": trigger_or_err})
                else:
                    r = schedule_reminder(user_id, trigger_or_err, prompt, kind="task")
                    if r.get("ok"):
                        t = r["task"]
                        await websocket.send_json({"type": "system", "content": f"Задача создана!\nID: {t['id']}\nКогда: {t['trigger_at']}\nЧто: {t['message'][:120]}"})
                    else:
                        await websocket.send_json({"type": "system", "content": f"Ошибка: {r.get('error')}"})

    # --- Rituals ---
    elif cmd == "rituals":
        is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
        else:
            from tools import db as _db
            rituals = load_rituals()
            runs = _db.load_ritual_runs()
            if not rituals:
                await websocket.send_json({"type": "system", "content": "Ритуалов не найдено."})
            else:
                lines = [f"Ритуалы ({len(rituals)}):"]
                for r in rituals:
                    run = runs.get(r["name"], {})
                    last = run.get("last_run", "—")[:16].replace("T", " ") if run.get("last_run") else "—"
                    lines.append(f"  {r['name']} | расписание: {r['schedule']} | last: {last}")
                await websocket.send_json({"type": "system", "content": "\n".join(lines)})

    elif cmd.startswith("ritual_run "):
        is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
        else:
            rname = cmd[11:].strip()
            rituals = {r["name"]: r for r in load_rituals()}
            if rname not in rituals:
                await websocket.send_json({"type": "system", "content": f"Ритуал '{rname}' не найден."})
            else:
                await websocket.send_json({"type": "system", "content": f"Запускаю ритуал '{rname}' в фоне..."})
                threading.Thread(target=_run_ritual_background, args=(rituals[rname], user_id), daemon=True).start()

    # ---------- Owner-only команды (read-only) ----------
    # is_owner здесь = тот же критерий что в Telegram (OWNER_TELEGRAM_ID).
    # Деструктивные (/evolve, /rollback, /release, /git, /restart) НЕ
    # пробрасываются в WS — они требуют интерактивных подтверждений
    # и контекста, оставлены только в Telegram.
    elif cmd in ("stats", "users", "users_data", "versions", "evolution_count",
                 "blacklist", "metrics_data", "rituals_data", "backups_data"):
        is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
        elif cmd == "stats":
            try:
                from tools.metrics_tools import metrics_read
                m = metrics_read(1)
                if not m.get("ok"):
                    await websocket.send_json({"type": "system", "content": f"stats: {m.get('error', 'нет данных')}"})
                else:
                    lines = [
                        f"Метрики за {m.get('days')} д.",
                        f"Вызовов: {m.get('total_calls')}",
                        f"Токенов: {m.get('total_tokens')}",
                        f"Оценка: ${m.get('cost_est', 0):.3f}",
                    ]
                    by_model = m.get("by_model") or {}
                    if by_model:
                        lines.append("\nПо моделям:")
                        for model, stat in list(by_model.items())[:10]:
                            lines.append(f"  {model}: {stat.get('calls')} вызовов, {stat.get('tokens')} токенов")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"stats: {e}"})
        elif cmd == "users":
            try:
                from tools.access_tools import list_users
                users = list_users()
                icons = {"owner": "👑", "regular": "✅", "guest": "👤", "rejected": "❌", "blacklisted": "🚫", "blocked": "🚫"}
                lines = [f"Пользователи ({len(users)}):"]
                for u in users:
                    ico = icons.get(u.get("status"), "?")
                    lines.append(f"{ico} {u.get('name') or '—'} [{u.get('status')}]\n   id: {u.get('id')}")
                lines.append("\nПереименовать: /rename <id> <новое имя>")
                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"users: {e}"})
        elif cmd == "users_data":
            # Структурный список для раскрывающегося меню в сайдбаре
            try:
                from tools.access_tools import list_users
                users = [
                    {"id": u.get("id"), "name": u.get("name") or "", "status": u.get("status") or "guest"}
                    for u in list_users()
                ]
                await websocket.send_json(_wsp(UsersList(users=[UserEntry(**u) for u in users])))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"users_data: {e}"})
        elif cmd == "metrics_data":
            # Структурные метрики LLM для owner-экрана Aurora.
            try:
                from tools.metrics_tools import metrics_read
                _days = 7
                m = metrics_read(_days)
                by_model = [
                    MetricsModelStat(
                        model=k,
                        calls=v.get("calls", 0),
                        tokens=v.get("prompt_tokens", 0) + v.get("completion_tokens", 0),
                        cost=round(v.get("cost_est", 0.0), 4),
                    )
                    for k, v in sorted(m.get("by_model", {}).items(),
                                       key=lambda kv: -kv[1].get("cost_est", 0))
                ]
                by_day = [
                    MetricsDayStat(day=k, calls=v.get("calls", 0),
                                   cost=round(v.get("cost_est", 0.0), 4))
                    for k, v in sorted(m.get("by_day", {}).items())
                ]
                await websocket.send_json(_wsp(MetricsData(
                    days=_days,
                    total_calls=m.get("total_calls", 0),
                    total_tokens=m.get("total_tokens", 0),
                    cost_est=round(m.get("cost_est", 0.0), 4),
                    by_model=by_model, by_day=by_day,
                )))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"metrics_data: {e}"})
        elif cmd == "rituals_data":
            # Структурные ритуалы для owner-экрана: расписание, дни недели,
            # последний/следующий запуск (через croniter).
            try:
                from tools.db import load_ritual_runs
                runs = load_ritual_runs()
                try:
                    from croniter import croniter
                except ImportError:
                    croniter = None
                _now = datetime.now()
                _entries = []
                for r in load_rituals():
                    _name = r.get("name", "")
                    _sched = r.get("schedule", "")
                    _days = [False] * 7
                    _next = None
                    if croniter and _sched:
                        try:
                            _it = croniter(_sched, _now)
                            _first = None
                            for _ in range(40):
                                _nxt = _it.get_next(datetime)
                                if _first is None:
                                    _first = _nxt
                                if (_nxt - _now).days > 31:
                                    break
                                _days[_nxt.weekday()] = True
                            _next = _first.isoformat() if _first else None
                        except Exception:
                            pass
                    _entries.append(RitualEntry(
                        id=_name, name=_name,
                        description=(r.get("prompt", "") or "")[:140],
                        schedule=_sched, days=_days, enabled=True,
                        last_run=runs.get(_name, {}).get("last_run"),
                        next_run=_next,
                    ))
                await websocket.send_json(_wsp(RitualsData(rituals=_entries)))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"rituals_data: {e}"})
        elif cmd == "backups_data":
            # rclone-листинг архива — в потоке, чтобы не блокировать loop.
            try:
                _bd = await asyncio.to_thread(_collect_backups_data, user_id)
                await websocket.send_json(_wsp(_bd))
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"backups_data: {e}"})
        elif cmd == "versions":
            try:
                import io as _io, sys as _sys
                from agent import list_backups
                buf = _io.StringIO(); old = _sys.stdout
                try:
                    _sys.stdout = buf
                    list_backups()
                finally:
                    _sys.stdout = old
                await websocket.send_json({"type": "system", "content": buf.getvalue() or "Резервных копий нет."})
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"versions: {e}"})
        elif cmd == "evolution_count":
            try:
                from tools.access_tools import get_evolution_stats
                evo = get_evolution_stats()
                total = evo.get("total", 0)
                success = evo.get("success", 0)
                failed = evo.get("failed", 0)
                rate = f"{round(success/total*100)}%" if total else "—"
                await websocket.send_json({"type": "system", "content":
                    f"Счётчик эволюций:\nВсего: {total}\nУспешных: {success}\n"
                    f"Неуспешных: {failed}\nУспешность: {rate}"})
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"evolution_count: {e}"})
        elif cmd == "blacklist":
            try:
                from tools.access_tools import list_users
                users = [u for u in list_users() if u.get("status") in ("blacklisted", "blocked")]
                if not users:
                    await websocket.send_json({"type": "system", "content": "Чёрный список пуст."})
                else:
                    lines = [f"Чёрный список ({len(users)}):"]
                    for u in users:
                        lines.append(f"🚫 {u.get('name') or u.get('id')} — {u.get('last_seen', '?')}")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
            except Exception as e:
                await websocket.send_json({"type": "system", "content": f"blacklist: {e}"})

    # --- User management WS-commands (owner-only) ---
    elif cmd.startswith("approve "):
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
            uid = cmd[8:].strip()
            if not uid: await websocket.send_json({"type": "system", "content": "approve <user_id>"})
            else:
                from tools.access_tools import approve as _approve
                ok = _approve(uid)
                await websocket.send_json({"type": "system", "content": "Одобрен." if ok else "Не найден."})

    elif cmd.startswith("block "):
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
            uid = cmd[6:].strip()
            if not uid: await websocket.send_json({"type": "system", "content": "block <user_id>"})
            else:
                from tools.access_tools import block as _block
                ok = _block(uid)
                await websocket.send_json({"type": "system", "content": "Заблокирован." if ok else "Не найден."})

    elif cmd.startswith("unblock "):
        if not is_owner_ws:
            await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
            uid = cmd[8:].strip()
            if not uid: await websocket.send_json({"type": "system", "content": "unblock <user_id>"})
            else:
                from tools.access_tools import unblock as _unblock
                ok = _unblock(uid)
                await websocket.send_json({"type": "system", "content": "Разблокирован." if ok else "Не найден."})

    # --- GDrive lifecycle ---
    elif cmd == "gdrive_login":
        if not is_approved_ws:
             await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        elif not gdrive_configured():
             await websocket.send_json({"type": "system", "content": "GDrive не настроен."})
        elif gdrive_authorized(user_id):
             await websocket.send_json({"type": "system", "content": "Drive уже привязан. gdrive_logout — отвязать."})
        else:
             url = get_auth_url(state=user_id)
             if url:
                 await websocket.send_json({"type": "system", "content": f"Открой в браузере:\n{url}\nПосле авторизации вернись в приложение."})
             else:
                 await websocket.send_json({"type": "system", "content": "Не удалось создать ссылку."})

    elif cmd == "gdrive_logout":
        if not is_approved_ws:
             await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
             from tools.gdrive_tools import _delete_token
             _delete_token(user_id)
             # Уведомить клиент о смене статуса Drive
             await websocket.send_json(_wsp(PermissionsUpdate(gdrive_authorized=False, gdrive_email="")))
             await websocket.send_json({"type": "system", "content": "Google Drive отвязан."})

    elif cmd == "gdrive_toggle":
        if not is_approved_ws:
             await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        elif not gdrive_authorized(user_id):
             await websocket.send_json({"type": "system", "content": "Сначала привяжи Drive: gdrive_login."})
        else:
             pd = load_user_profile(user_id) or {}
             prefs = pd.get("preferences", {})
             cur = prefs.get("gdrive_auto_upload", False)
             new_val = not cur
             prefs["gdrive_auto_upload"] = new_val
             pd["preferences"] = prefs
             save_user_profile(user_id, pd)
             state = "включена" if new_val else "выключена"
             await websocket.send_json({"type": "system", "content": f"Авто-загрузка на Drive {state}."})

    # --- Kidmode (owner-only) ---
    elif cmd.startswith("kidmode "):
        if not is_owner_ws:
             await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
             parts = cmd[8:].strip().split()
             if len(parts) < 2:
                 await websocket.send_json({"type": "system", "content": "kidmode <user_id> on|off"})
             else:
                 uid, toggle = parts[0], parts[1].lower()
                 if toggle not in ("on", "off"):
                     await websocket.send_json({"type": "system", "content": "on или off."})
                 else:
                     data = load_user_profile(uid)
                     if not data:
                         await websocket.send_json({"type": "system", "content": "Пользователь не найден."})
                     else:
                         data["child_mode"] = (toggle == "on")
                         save_user_profile(uid, data)
                         await websocket.send_json({"type": "system", "content": f"Детский режим {toggle} для {uid}."})

    # --- Reflect (owner-only) ---
    elif cmd == "reflect":
        if not is_owner_ws:
             await websocket.send_json({"type": "system", "content": "Только для владельца."})
        else:
             # Agent и Profile уже импортированы на верху файла (строка 48).
             # Локальный import шадовил бы Profile как локальную для всей
             # функции chat() → UnboundLocalError в обычной ветке сообщений.
             msgs = _load_session(user_id)
             prompt = (
                 "Проанализируй свой код (agent.py, conclave.py, providers.py, router.py, "
                 "telegram_bot.py, web/app.py, tools/) через read_self/list_self. "
                 "Найди риски, баги, устаревший код, дублирование. Отвечай конкретно."
             )
             msgs.append({"role": "user", "content": prompt})
             profile_dev = Profile("dev")
             try:
                 alpha_refl = Agent.from_config_file("alpha", profile_dev, user_id, _system_prompt_for(user_id))
                 answer = await asyncio.to_thread(alpha_refl.run, msgs)
                 await websocket.send_json({"type": "message", "content": answer})
                 msgs.append({"role": "assistant", "content": answer})
                 _save_session(user_id, msgs)
             except Exception as e:
                 await websocket.send_json({"type": "error", "content": f"Reflect: {e}"})

    # --- Image generation (approved) ---
    elif cmd.startswith("image "):
        if not is_approved_ws:
             await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
        else:
             prompt = cmd[6:].strip()
             if not prompt:
                 await websocket.send_json({"type": "system", "content": "image <описание картинки>"})
             else:
                 from tools import image_tools
                 await websocket.send_json({"type": "thinking"})
                 result = await asyncio.to_thread(image_tools.generate_image, user_id, prompt)
                 if result.get("ok"):
                     fname = os.path.basename(result.get("path", ""))
                     await websocket.send_json({
                         "type": "message",
                         "content": f"Картинка готова: {fname}",
                         "attachments": [{"name": fname, "dir": "output", "size": result.get("size", 0)}],
                     })
                 else:
                     await websocket.send_json({"type": "error", "content": result.get("error", "Ошибка генерации")})
