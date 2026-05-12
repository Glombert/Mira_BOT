"""
scheduler.py — отложенные напоминания для Миры.

Хранит задачи в memory/scheduled_tasks.json.
Фоновый поток в telegram_bot.py проверяет каждые 30 секунд
и отправляет сообщения пользователям в Telegram.
"""

import json
import os
import uuid
import time
import threading
from datetime import datetime

SCHEDULED_TASKS_FILE = os.path.join("memory", "scheduled_tasks.json")
_LOCK = threading.Lock()


def _load_tasks() -> list[dict]:
    """Загружает все задачи из файла."""
    os.makedirs("memory", exist_ok=True)
    try:
        with open(SCHEDULED_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_tasks(tasks: list[dict]) -> None:
    """Сохраняет задачи в файл. Потокобезопасно."""
    os.makedirs("memory", exist_ok=True)
    with _LOCK:
        tmp = SCHEDULED_TASKS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SCHEDULED_TASKS_FILE)


def schedule_reminder(user_id: str, trigger_at: str, message: str) -> dict:
    """
    Создаёт отложенное напоминание.

    trigger_at — ISO-дата/время: '2026-05-13T05:10:00'
    message   — текст который Мира отправит пользователю

    Возвращает id созданной задачи.
    """
    tasks = _load_tasks()
    task = {
        "id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "trigger_at": trigger_at,
        "message": message,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    tasks.append(task)
    _save_tasks(tasks)
    return {"ok": True, "task": task}


def list_reminders(user_id: str) -> dict:
    """Возвращает все активные напоминания пользователя."""
    tasks = _load_tasks()
    user_tasks = [
        t for t in tasks
        if t["user_id"] == user_id and t["status"] == "pending"
    ]
    # Сортируем по времени срабатывания
    user_tasks.sort(key=lambda t: t["trigger_at"])
    return {"ok": True, "reminders": user_tasks, "count": len(user_tasks)}


def cancel_reminder(user_id: str, task_id: str) -> dict:
    """Отменяет напоминание по ID."""
    tasks = _load_tasks()
    for t in tasks:
        if t["id"] == task_id and t["user_id"] == user_id:
            if t["status"] == "pending":
                t["status"] = "cancelled"
                _save_tasks(tasks)
                return {"ok": True, "message": f"Напоминание {task_id} отменено."}
            else:
                return {"ok": False, "error": f"Напоминание уже имеет статус: {t['status']}"}
    return {"ok": False, "error": f"Напоминание {task_id} не найдено."}


def get_due_tasks() -> list[dict]:
    """
    Возвращает задачи которые пора выполнить (trigger_at <= сейчас)
    и помечает их как 'firing'.
    """
    now = datetime.now().isoformat()
    tasks = _load_tasks()
    due = []
    changed = False
    for t in tasks:
        if t["status"] == "pending" and t["trigger_at"] <= now:
            t["status"] = "firing"
            due.append(t)
            changed = True
    if changed:
        _save_tasks(tasks)
    return due


def mark_done(task_id: str) -> None:
    """Помечает задачу как выполненную."""
    tasks = _load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "done"
            _save_tasks(tasks)
            return
