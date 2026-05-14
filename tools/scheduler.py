"""scheduler.py — отложенные напоминания для Миры.

Хранит задачи в таблице reminders в memory/mira.db.
Фоновый поток в telegram_bot.py проверяет каждые 30 секунд
и отправляет сообщения пользователям в Telegram.
"""

from tools import db


def schedule_reminder(user_id: str, trigger_at: str, message: str) -> dict:
    """
    Создаёт отложенное напоминание.

    trigger_at — ISO-дата/время: '2026-05-13T05:10:00'
    message   — текст который Мира отправит пользователю

    Возвращает id созданной задачи.
    """
    task = db.add_reminder(user_id, trigger_at, message)
    return {"ok": True, "task": task}


def list_reminders(user_id: str) -> dict:
    """Возвращает все активные напоминания пользователя."""
    user_tasks = db.list_user_reminders(user_id)
    return {"ok": True, "reminders": user_tasks, "count": len(user_tasks)}


def cancel_reminder(user_id: str, task_id: str) -> dict:
    """Отменяет напоминание по ID."""
    ok, msg = db.cancel_reminder(user_id, task_id)
    if ok:
        return {"ok": True, "message": f"Напоминание {task_id} отменено."}
    return {"ok": False, "error": msg}


def get_due_tasks() -> list[dict]:
    """
    Возвращает задачи которые пора выполнить (trigger_at <= сейчас)
    и атомарно помечает их как 'firing'.
    """
    return db.get_due_reminders()


def mark_done(task_id: str) -> None:
    """Помечает задачу как выполненную."""
    db.mark_reminder_done(task_id)
