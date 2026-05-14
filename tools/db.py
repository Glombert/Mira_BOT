"""SQLite-слой для memory/.

Заменяет россыпь JSON-файлов в memory/ единой базой mira.db:
    user_profiles  ← memory/{user_id}.json
    sessions       ← memory/sessions/{user_id}.json
    reminders      ← memory/scheduled_tasks.json (одной таблицей вместо большого списка)
    reflections    ← memory/reflections.json
    gdrive_tokens  ← memory/gdrive/{user_id}.json

Главные дизайн-моменты:
- WAL — одновременные читатели не блокируют писателей (telegram_bot и web/app
  одновременно пишут в один профиль — раньше это была гонка)
- Connection-per-thread через threading.local — стандартный паттерн для sqlite3
- Каждая публичная функция — одна транзакция через `with conn:`

Шифрование (если MEMORY_ENCRYPTION_KEY задан): JSON-строки прозрачно
прогоняются через memory_crypto.encrypt_str/decrypt_str перед записью/чтением.
Сейчас на VPS шифрование выключено — данные хранятся в открытом JSON.
"""

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger("Ouroborus")

DB_PATH = os.path.join("memory", "mira.db")
_thread_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_conn() -> sqlite3.Connection:
    """Возвращает connection текущего потока, открывая при необходимости."""
    if not _initialized:
        init_db()
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = _connect(DB_PATH)
        _thread_local.conn = conn
    return conn


def init_db(path: str | None = None) -> None:
    """Создаёт таблицы. Идемпотентно. Можно звать без аргумента — возьмёт DB_PATH."""
    global _initialized, DB_PATH
    if path:
        DB_PATH = path

    with _init_lock:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = _connect(DB_PATH)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id     TEXT PRIMARY KEY,
                    data        TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    user_id     TEXT PRIMARY KEY,
                    messages    TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id           TEXT PRIMARY KEY,
                    user_id      TEXT NOT NULL,
                    trigger_at   TEXT NOT NULL,
                    message      TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_user_status
                    ON reminders(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_reminders_pending_trigger
                    ON reminders(status, trigger_at);

                CREATE TABLE IF NOT EXISTS reflections (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    date         TEXT NOT NULL,
                    content      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gdrive_tokens (
                    user_id      TEXT PRIMARY KEY,
                    token_data   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
            """)
        finally:
            conn.close()
        _initialized = True


def _close_thread_conn() -> None:
    """Только для тестов — закрывает connection текущего потока."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None


# ---------------------------------------------------------------------------
# JSON-кодек (с опциональным шифрованием)
# ---------------------------------------------------------------------------

def _encode(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False)
    try:
        import memory_crypto
        if memory_crypto.is_enabled():
            # Fernet возвращает base64-bytes — кодируем в str для TEXT-колонки
            return memory_crypto._fernet.encrypt(raw.encode("utf-8")).decode("ascii")  # type: ignore[attr-defined]
    except Exception:
        pass
    return raw


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        import memory_crypto
        if memory_crypto.is_enabled():
            # Fernet-токены начинаются с 'gAAAA'. Plain JSON — с '{' или '['
            if raw and raw[0] not in ("{", "["):
                decrypted = memory_crypto._fernet.decrypt(raw.encode("ascii"))  # type: ignore[attr-defined]
                return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.warning(f"db._decode: ошибка дешифрования: {e}")
    return json.loads(raw)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

def load_user_profile(user_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT data FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    data = _decode(row["data"])
    return data if isinstance(data, dict) else None


def save_user_profile(user_id: str, data: dict) -> None:
    data["updated_at"] = _now_iso()
    encoded = _encode(data)
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO user_profiles (user_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (user_id, encoded, data["updated_at"]),
        )


def delete_user_profile(user_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
    return cur.rowcount > 0


def list_user_profiles() -> list[tuple[str, dict]]:
    """Возвращает [(user_id, profile_dict), ...] для всех пользователей."""
    rows = get_conn().execute(
        "SELECT user_id, data FROM user_profiles"
    ).fetchall()
    result = []
    for row in rows:
        profile = _decode(row["data"])
        if isinstance(profile, dict):
            result.append((row["user_id"], profile))
    return result


# ---------------------------------------------------------------------------
# Sessions (история диалога)
# ---------------------------------------------------------------------------

def load_session(user_id: str) -> list[dict] | None:
    row = get_conn().execute(
        "SELECT messages FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    data = _decode(row["messages"])
    return data if isinstance(data, list) else None


def save_session(user_id: str, messages: list[dict]) -> None:
    encoded = _encode(messages)
    now = _now_iso()
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO sessions (user_id, messages, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET messages=excluded.messages, updated_at=excluded.updated_at",
            (user_id, encoded, now),
        )


def delete_session(user_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def add_reminder(user_id: str, trigger_at: str, message: str) -> dict:
    task = {
        "id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "trigger_at": trigger_at,
        "message": message,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO reminders (id, user_id, trigger_at, message, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task["id"], user_id, trigger_at, message, "pending", task["created_at"]),
        )
    return task


def list_user_reminders(user_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' "
        "ORDER BY trigger_at",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def cancel_reminder(user_id: str, task_id: str) -> tuple[bool, str]:
    """Возвращает (success, error_or_empty)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT status FROM reminders WHERE id = ? AND user_id = ?",
        (task_id, user_id),
    ).fetchone()
    if row is None:
        return False, f"Напоминание {task_id} не найдено."
    if row["status"] != "pending":
        return False, f"Напоминание уже имеет статус: {row['status']}"
    with conn:
        conn.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ?",
            (task_id,),
        )
    return True, ""


def get_due_reminders() -> list[dict]:
    """Атомарно: помечает due-задачи как 'firing' и возвращает их."""
    now = datetime.now().isoformat()
    conn = get_conn()
    with conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND trigger_at <= ?",
            (now,),
        ).fetchall()
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE reminders SET status = 'firing' WHERE id IN ({placeholders})",
            ids,
        )
    return [dict(r) for r in rows]


def mark_reminder_done(task_id: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?",
            (task_id,),
        )


# ---------------------------------------------------------------------------
# Reflections (плоский список глобальных рефлексий с датой)
# ---------------------------------------------------------------------------

def load_reflections() -> list[dict]:
    rows = get_conn().execute(
        "SELECT date, content FROM reflections ORDER BY id"
    ).fetchall()
    return [{"date": r["date"], "content": r["content"]} for r in rows]


def add_reflection(content: str, date: str | None = None) -> None:
    if date is None:
        date = _now_iso()
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO reflections (date, content) VALUES (?, ?)",
            (date, content),
        )


# ---------------------------------------------------------------------------
# Google Drive токены (refresh_token и пр.)
# ---------------------------------------------------------------------------

def load_gdrive_token(user_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT token_data FROM gdrive_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    data = _decode(row["token_data"])
    return data if isinstance(data, dict) else None


def save_gdrive_token(user_id: str, token_data: dict) -> None:
    encoded = _encode(token_data)
    now = _now_iso()
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO gdrive_tokens (user_id, token_data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET token_data=excluded.token_data, updated_at=excluded.updated_at",
            (user_id, encoded, now),
        )


def delete_gdrive_token(user_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM gdrive_tokens WHERE user_id = ?", (user_id,))
    return cur.rowcount > 0
