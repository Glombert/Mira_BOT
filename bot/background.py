"""bot/background.py — post_init: heartbeat, цикл напоминаний и цикл ритуалов."""

import asyncio
import os
from agent import MEMORY_DIR
from agent import cleanup_expired_guests
from agent import notify_owner
from datetime import datetime
from telegram import BotCommandScopeChat
from telegram import BotCommandScopeDefault
from telegram.ext import Application
from tools.scheduler import get_due_tasks
from tools.scheduler import mark_done

from bot.config import OWNER_TG_ID, logger
from bot.menu import BASIC_COMMANDS, OWNER_COMMANDS


async def post_init(app: Application) -> None:
    """Устанавливает меню команд при старте бота и чистит просроченных гостей."""
    import threading, time as _time

    # Heartbeat: фоновый поток пишет метку каждые 30 секунд
    _heartbeat_path = os.path.join(MEMORY_DIR, ".heartbeat")

    def _heartbeat_loop() -> None:
        while True:
            try:
                os.makedirs(MEMORY_DIR, exist_ok=True)
                with open(_heartbeat_path, "w") as f:
                    f.write(str(_time.time()))
            except Exception:
                pass
            _time.sleep(30)

    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    # Scheduler: фоновый поток проверяет отложенные напоминания каждые 30 секунд
    _scheduler_loop_ref = asyncio.get_running_loop()

    def _scheduler_loop() -> None:
        _time.sleep(5)
        _retry_counts: dict = {}   # task_id → число неудачных доставок
        MAX_RETRIES = 5
        while True:
            try:
                due = get_due_tasks()
                for task in due:
                    try:
                        kind = task.get("kind", "reminder")
                        if kind == "task":
                            # Scheduled task: симулируем user message через _run_scheduled_task
                            def _run_task(t=task):
                                from web.ritual_runner import _run_scheduled_task as _rst
                                answer = _rst(t["user_id"], t["message"])
                                # Уведомление владельцу
                                notify_owner(
                                    f"⏰ Задача выполнена\n"
                                    f"Пользователь: {t['user_id']}\n"
                                    f"Задача: {t['message'][:120]}\n"
                                    f"Ответ Миры: {answer[:240]}"
                                )
                                mark_done(t["id"])
                            threading.Thread(target=_run_task, daemon=True).start()
                        else:
                            # Reminder
                            tid = task["id"]
                            raw_uid = task["user_id"].replace("tg_", "")
                            if not raw_uid.isdigit():
                                # Доставить невозможно — не ретраим бесконечно.
                                logger.warning(f"Scheduler: некорректный user_id {task['user_id']} у {tid}, помечаю done")
                                mark_done(tid)
                                continue
                            chat_id = int(raw_uid)
                            text = f"⏰ Напоминание:\n{task['message']}"
                            try:
                                from tools import fcm_tools
                                fcm_tools.send_push(
                                    user_id=task["user_id"],
                                    title="⏰ Напоминание",
                                    body=task["message"][:240],
                                    data={"reminder_id": tid},
                                )
                            except Exception as e:
                                logger.warning(f"Scheduler: FCM не сработал: {e}")
                            # ЖДЁМ подтверждения доставки в Telegram перед mark_done —
                            # иначе при сбое API напоминание терялось бы (помечалось done).
                            fut = asyncio.run_coroutine_threadsafe(
                                app.bot.send_message(chat_id=chat_id, text=text),
                                _scheduler_loop_ref,
                            )
                            fut.result(timeout=20)   # бросит при сбое → except → ретрай
                            mark_done(tid)
                            _retry_counts.pop(tid, None)
                            logger.info(f"Scheduler: отправлено напоминание {tid} → {task['user_id']}")
                    except Exception as e:
                        tid = task.get("id")
                        n = _retry_counts.get(tid, 0) + 1
                        _retry_counts[tid] = n
                        logger.warning(f"Scheduler: доставка {tid} не удалась (попытка {n}/{MAX_RETRIES}): {e}")
                        if n >= MAX_RETRIES:
                            # Dead-letter: сдаёмся, но сообщаем владельцу — не молча.
                            logger.error(f"Scheduler: {tid} — сдаюсь после {n} попыток, помечаю done")
                            mark_done(tid)
                            _retry_counts.pop(tid, None)
                            try:
                                notify_owner(f"⚠ Напоминание {tid} не доставлено после {n} попыток, сдаюсь.")
                            except Exception:
                                pass
                        # иначе НЕ mark_done → повтор через 30с
            except Exception as e:
                logger.warning(f"Scheduler: ошибка цикла: {e}")
            _time.sleep(30)

    threading.Thread(target=_scheduler_loop, daemon=True).start()

    # Rituals: фоновый поток проверяет cron-расписание ритуалов каждые 60 сек
    _ritual_loop_ref = asyncio.get_running_loop()

    def _ritual_loop() -> None:
        _time.sleep(30)  # старт позже чтобы scheduler инициализировался
        from tools.rituals import load_rituals
        from tools import db as _db
        from datetime import datetime as _dt
        from web.ritual_runner import _run_ritual_background
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("Rituals: croniter не установлен. pip install croniter")
            return

        # Защита от дублей: ритуал может выполняться дольше 60с (LLM-вызов),
        # а last_run пишется ПОСЛЕ ответа. На следующей итерации без флага мы
        # запустили бы тот же ритуал повторно.
        running: set[str] = set()
        running_lock = threading.Lock()

        def _wrapped(r, owner_id):
            name = r["name"]
            try:
                _run_ritual_background(r, owner_id)
            finally:
                with running_lock:
                    running.discard(name)

        first_pass = True  # на первом проходе после старта гоним on_startup-ритуалы (selftest)
        while True:
            try:
                rituals = load_rituals()
                runs = _db.load_ritual_runs()
                now = _dt.now()
                owner_id = f"tg_{OWNER_TG_ID}" if OWNER_TG_ID else ""
                for r in rituals:
                    name = r["name"]
                    with running_lock:
                        if name in running:
                            continue
                    is_startup = bool(first_pass and r.get("on_startup"))
                    should_run = False
                    last_run_str = runs.get(name, {}).get("last_run")
                    last_run = _dt.fromisoformat(last_run_str) if last_run_str else None
                    if last_run is None:
                        # Никогда не запускался — гоним, даже если не on_startup
                        # (cron всё равно бы догнал на следующей итерации).
                        should_run = True
                    elif is_startup:
                        # При рестарте on_startup-ритуал запускаем ТОЛЬКО если
                        # очередной запуск по cron уже просрочен. Иначе ждём
                        # своего cron-времени, чтобы не дёргать ритуал каждый
                        # раз когда процесс перезапускают несколько раз за день.
                        cron_past = croniter(r["schedule"], last_run)
                        next_from_last = cron_past.get_next(datetime)
                        if now >= next_from_last:
                            should_run = True
                    else:
                        cron_past = croniter(r["schedule"], last_run)
                        next_from_last = cron_past.get_next(datetime)
                        if now >= next_from_last and (now - last_run).total_seconds() >= 60:
                            should_run = True
                    if should_run:
                        with running_lock:
                            running.add(name)
                        threading.Thread(
                            target=_wrapped, args=(r, owner_id),
                            daemon=True
                        ).start()
                        logger.info(f"Rituals: запущен '{name}'" + (" (startup selftest)" if is_startup else ""))
                first_pass = False
            except Exception as e:
                logger.warning(f"Rituals: ошибка цикла: {e}")
            _time.sleep(60)

    threading.Thread(target=_ritual_loop, daemon=True).start()

    # Стартовое уведомление владельцу
    try:
        notify_owner("Мира запущена на VPS")
    except Exception as e:
        logger.warning(f"Не удалось отправить стартовое уведомление: {e}")

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
