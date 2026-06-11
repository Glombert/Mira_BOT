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
На проде ключ задан — потеря MEMORY_ENCRYPTION_KEY означает потерю памяти.
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("Ouroboros")

from tools.paths import at_root

DB_PATH = at_root("memory", "mira.db")
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

                CREATE TABLE IF NOT EXISTS push_tokens (
                    -- Одна строка = одно устройство пользователя.
                    -- Хранится FCM-токен, который выдал Firebase данному
                    -- устройству при регистрации. token может меняться при
                    -- переустановке/чистке данных приложения — поэтому
                    -- UNIQUE по (user_id, token) и обновление по updated_at.
                    user_id      TEXT NOT NULL,
                    token        TEXT NOT NULL,
                    platform     TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    PRIMARY KEY (user_id, token)
                );

                CREATE TABLE IF NOT EXISTS server_metrics (
                    -- Сэмплы здоровья сервера (раз в 5 мин, retention 7 дней)
                    -- для графиков owner-экрана «Сервер».
                    ts            TEXT PRIMARY KEY,
                    load1         REAL NOT NULL,
                    mem_percent   INTEGER NOT NULL,
                    swap_mb       INTEGER NOT NULL,
                    disk_percent  INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS vpn_peer_samples (
                    -- Срез wg dump раз в 5 мин: кумулятивные байты на пира.
                    ts        TEXT NOT NULL,
                    pubkey    TEXT NOT NULL,
                    rx_bytes  INTEGER NOT NULL,
                    tx_bytes  INTEGER NOT NULL,
                    online    INTEGER NOT NULL,
                    PRIMARY KEY (ts, pubkey)
                );

                CREATE TABLE IF NOT EXISTS vpn_bridge_samples (
                    -- Доступность РУ-моста (TCP-проверка) раз в 5 мин.
                    ts          TEXT PRIMARY KEY,
                    ok          INTEGER NOT NULL,
                    latency_ms  INTEGER
                );

                CREATE TABLE IF NOT EXISTS ritual_runs (
                    -- Хранит last_run и краткий вывод для каждого ритуала.
                    name         TEXT PRIMARY KEY,
                    last_run     TEXT,
                    last_output  TEXT
                );

                CREATE TABLE IF NOT EXISTS mobile_auth_codes (
                    -- Одноразовые коды для /m/auth deep-link: заменяют
                    -- session token в URL (чтобы не утекал в nginx-логи).
                    -- ОБЯЗАТЕЛЬНО в БД, а не в памяти: код генерит процесс
                    -- mira-bot, а гасит mira-web — память процессов не общая.
                    code         TEXT PRIMARY KEY,
                    token        TEXT NOT NULL,
                    expiry       REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_messages (
                    -- Письма между пользователями (через Миру как посредника).
                    -- delivered: True когда доставлено получателю (БД +
                    -- TG-DM + WS push). seen: True когда Мира зачитала
                    -- получателю в разговоре.
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id TEXT NOT NULL,
                    from_name    TEXT NOT NULL DEFAULT '',
                    to_user_id   TEXT NOT NULL,
                    body         TEXT NOT NULL,
                    ts           TEXT NOT NULL,
                    delivered    INTEGER NOT NULL DEFAULT 0,
                    seen         INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_user_messages_to
                    ON user_messages(to_user_id, seen, ts);

                CREATE TABLE IF NOT EXISTS pending_sends (
                    -- Промежуточная очередь: send_to_user кладёт сюда,
                    -- confirm_send переносит в user_messages и доставляет.
                    -- Двухфактор: один зов готовит, второй отправляет.
                    -- TTL 10 минут.
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id TEXT NOT NULL,
                    to_user_id   TEXT NOT NULL,
                    target_name  TEXT NOT NULL DEFAULT '',
                    body         TEXT NOT NULL,
                    ts           TEXT NOT NULL,
                    expires_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS owner_inbox (
                    -- Технический канал владельца: ритуалы, ошибки,
                    -- approval_request и пр. system-сообщения. Двусторонний
                    -- чат «Техника» в приложении читает отсюда.
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           TEXT NOT NULL,
                    type         TEXT NOT NULL,
                    importance   TEXT NOT NULL DEFAULT 'NONE',
                    title        TEXT NOT NULL DEFAULT '',
                    body         TEXT NOT NULL,
                    payload      TEXT,
                    is_read      INTEGER NOT NULL DEFAULT 0,
                    action       TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_owner_inbox_ts ON owner_inbox(ts);
                CREATE INDEX IF NOT EXISTS idx_owner_inbox_unread
                    ON owner_inbox(is_read, ts);
            """)
            # Миграция: добавляем колонку kind в reminders (v2.0).
            # Идемпотентно — проверяем PRAGMA table_info перед ALTER.
            try:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)").fetchall()}
                if "kind" not in cols:
                    conn.execute("ALTER TABLE reminders ADD COLUMN kind TEXT NOT NULL DEFAULT 'reminder'")
                    logger.info("db: миграция — reminders.kind добавлен")
                if "dedup_key" not in cols:
                    conn.execute("ALTER TABLE reminders ADD COLUMN dedup_key TEXT")
                    logger.info("db: миграция — reminders.dedup_key добавлен")
            except Exception as e:
                logger.warning(f"db: миграция reminders пропущена: {e}")
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
    # Намеренно без try/except: если шифрование включено и сломалось,
    # молчаливый фолбэк записал бы данные открытым текстом (fail-open).
    # Лучше громкая ошибка, чем тихая утечка.
    from core import memory_crypto
    if memory_crypto.is_enabled():
        return memory_crypto.encrypt_str(raw)
    return raw


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        from core import memory_crypto
        if memory_crypto.is_enabled():
            # Fernet-токены начинаются с 'gAAAA'. Plain JSON — с '{' или '['
            if raw and raw[0] not in ("{", "["):
                return json.loads(memory_crypto.decrypt_str(raw))
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
# Одноразовые коды /m/auth (кросс-процессно: bot пишет, web гасит)
# ---------------------------------------------------------------------------

def store_mobile_auth_code(code: str, token: str, expiry: float) -> None:
    """Сохраняет одноразовый код /m/auth с epoch-сроком жизни."""
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO mobile_auth_codes (code, token, expiry) "
            "VALUES (?, ?, ?)",
            (code, token, expiry),
        )


def pop_mobile_auth_code(code: str) -> str | None:
    """Возвращает token по коду и сразу удаляет код (one-time).
    None если код не найден или истёк. Заодно чистит протухшие коды."""
    now = time.time()
    conn = get_conn()
    with conn:
        row = conn.execute(
            "SELECT token, expiry FROM mobile_auth_codes WHERE code = ?", (code,)
        ).fetchone()
        conn.execute("DELETE FROM mobile_auth_codes WHERE code = ?", (code,))
        conn.execute("DELETE FROM mobile_auth_codes WHERE expiry < ?", (now,))
    if row is None or row["expiry"] < now:
        return None
    return row["token"]


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


def delete_sessions_older_than(cutoff_iso: str) -> int:
    """Retention: удаляет сессии, не обновлявшиеся с cutoff_iso (по updated_at,
    который save_session переписывает при каждом сообщении). Возвращает число
    удалённых строк."""
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff_iso,))
    return cur.rowcount


def get_session_updated_at(user_id: str) -> str | None:
    """Возвращает updated_at сессии в ISO-формате или None если сессии нет.

    Нужен для миграции «по timestamp» — какая из двух сессий свежее.
    """
    row = get_conn().execute(
        "SELECT updated_at FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["updated_at"] if row else None


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def _normalize_trigger(trigger_at: str) -> str:
    """Гарантирует что trigger_at содержит tz-info. Без TZ → +00:00 (UTC).

    Дефолтная зона для naive-строк теперь UTC (storage convention).
    Если parse_time на верхнем уровне получил `user_tz`, он уже отдал
    ISO с правильным offset'ом — нам в DB остаётся только убедиться что
    TZ-info есть. Голые naive здесь возможны только из ручного ввода
    через прямой вызов (тесты, миграции).
    """
    trigger_at = trigger_at.strip()
    if '+' in trigger_at[10:] or trigger_at.endswith('Z') or '-' in trigger_at[10:]:
        return trigger_at
    return trigger_at + "+00:00"


def _dedup_key(user_id: str, trigger_at: str, message: str) -> str:
    """Хэш для дедупликации: (user_id, trigger, сообщение без эмодзи)."""
    import re as _re, hashlib as _hl
    normalized = _re.sub(r'[^\w\s]', '', message).strip().lower()
    raw = f"{user_id}|{trigger_at[:19]}|{normalized[:80]}"
    return _hl.sha256(raw.encode()).hexdigest()[:16]


def add_reminder(user_id: str, trigger_at: str, message: str,
                 kind: str = "reminder") -> dict:
    trigger_at = _normalize_trigger(trigger_at)
    dkey = _dedup_key(user_id, trigger_at, message)

    conn = get_conn()
    # Проверяем дубликат за последние 5 минут с тем же dedup_key + status=pending
    existing = conn.execute(
        "SELECT id, created_at FROM reminders "
        "WHERE user_id=? AND dedup_key=? AND status='pending' "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id, dkey),
    ).fetchone()
    if existing:
        return {
            "id": existing["id"],
            "user_id": user_id,
            "trigger_at": trigger_at,
            "message": message,
            "status": "pending",
            "kind": kind,
            "created_at": existing["created_at"],
            "deduped": True,
        }

    task_id = str(uuid.uuid4())[:8]
    now_iso = datetime.now().isoformat()
    with conn:
        conn.execute(
            "INSERT INTO reminders (id, user_id, trigger_at, message, status, kind, created_at, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, user_id, trigger_at, message, "pending", kind, now_iso, dkey),
        )
    return {
        "id": task_id,
        "user_id": user_id,
        "trigger_at": trigger_at,
        "message": message,
        "status": "pending",
        "kind": kind,
        "created_at": now_iso,
    }


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
    """Атомарно: помечает due-задачи как 'firing' и возвращает их.

    TZ-aware сравнение: trigger_at хранится с tz-info (+03:00),
    now берётся в UTC. fromisoformat корректно переводит +03:00 в UTC
    для сравнения. Старые записи без TZ интерпретируются как МСК.
    """
    now_utc = datetime.now(timezone.utc)
    conn = get_conn()
    with conn:
        all_pending = conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending'"
        ).fetchall()
        due_ids = []
        for row in all_pending:
            trigger_str = row["trigger_at"]
            try:
                t = datetime.fromisoformat(trigger_str)
            except ValueError:
                continue
            if t.tzinfo is None:
                # Naive-запись (только из тестов / прямых вставок) — считаем UTC
                t = t.replace(tzinfo=timezone.utc)
            if t <= now_utc:
                due_ids.append(row["id"])
        if not due_ids:
            return []
        placeholders = ",".join("?" * len(due_ids))
        conn.execute(
            f"UPDATE reminders SET status = 'firing' WHERE id IN ({placeholders})",
            due_ids,
        )
        logger.info(
            f"db: get_due_reminders — {len(due_ids)} due "
            f"(now_utc={now_utc.isoformat()})"
        )
    # Повторно читаем затронутые строки
    rows = conn.execute(
        f"SELECT * FROM reminders WHERE id IN ({placeholders})",
        due_ids,
    ).fetchall()
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


# ---------------------------------------------------------------------------
# Push-токены устройств (FCM/APNs)
# ---------------------------------------------------------------------------

def save_push_token(user_id: str, token: str, platform: str = "android") -> None:
    """Регистрирует/обновляет push-токен устройства пользователя.

    Один пользователь может иметь несколько устройств (телефон, планшет) —
    PRIMARY KEY (user_id, token) допускает мульти-токен. При повторной
    регистрации того же токена обновляется только updated_at.
    """
    now = _now_iso()
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO push_tokens (user_id, token, platform, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, token) DO UPDATE SET updated_at=excluded.updated_at, platform=excluded.platform",
            (user_id, token, platform, now),
        )


def list_push_tokens(user_id: str) -> list[dict]:
    """Возвращает все активные push-токены пользователя."""
    rows = get_conn().execute(
        "SELECT token, platform, updated_at FROM push_tokens WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    return [{"token": r["token"], "platform": r["platform"], "updated_at": r["updated_at"]} for r in rows]


def delete_push_token(user_id: str, token: str) -> bool:
    """Удаляет конкретный токен (вызывать при FCM 'invalid registration')."""
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "DELETE FROM push_tokens WHERE user_id = ? AND token = ?",
            (user_id, token),
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Ritual runs (хранение last_run для фоновых ритуалов)
# ---------------------------------------------------------------------------

def save_ritual_run(name: str, last_run: str, last_output: str = "") -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO ritual_runs (name, last_run, last_output) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET last_run=excluded.last_run, last_output=excluded.last_output",
            (name, last_run, last_output),
        )


def load_ritual_runs() -> dict[str, dict]:
    """Возвращает {name: {last_run, last_output}, ...} для всех ритуалов."""
    rows = get_conn().execute("SELECT name, last_run, last_output FROM ritual_runs").fetchall()
    return {r["name"]: {"last_run": r["last_run"], "last_output": r["last_output"]} for r in rows}


# ---------------------------------------------------------------------------
# Server metrics (сэмплы для графиков owner-экрана «Сервер»)
# ---------------------------------------------------------------------------

SERVER_METRICS_RETENTION_DAYS = 7


def save_server_metric(load1: float, mem_percent: int, swap_mb: int, disk_percent: int) -> None:
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=SERVER_METRICS_RETENTION_DAYS)).isoformat()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO server_metrics (ts, load1, mem_percent, swap_mb, disk_percent) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), load1, mem_percent, swap_mb, disk_percent),
        )
        conn.execute("DELETE FROM server_metrics WHERE ts < ?", (cutoff,))


def load_server_metrics(hours: int = 24) -> list[dict]:
    """Сэмплы за последние N часов, по возрастанию времени."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = get_conn().execute(
        "SELECT ts, load1, mem_percent, swap_mb, disk_percent FROM server_metrics "
        "WHERE ts >= ? ORDER BY ts", (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_vpn_sample(peers: list[dict], bridge_ok: bool, bridge_latency_ms: int | None) -> None:
    conn = get_conn()
    ts = datetime.now().isoformat()
    cutoff = (datetime.now() - timedelta(days=SERVER_METRICS_RETENTION_DAYS)).isoformat()
    with conn:
        for p in peers:
            conn.execute(
                "INSERT OR REPLACE INTO vpn_peer_samples (ts, pubkey, rx_bytes, tx_bytes, online) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, p["pubkey"], p["rx_bytes"], p["tx_bytes"], 1 if p["online"] else 0),
            )
        conn.execute(
            "INSERT OR REPLACE INTO vpn_bridge_samples (ts, ok, latency_ms) VALUES (?, ?, ?)",
            (ts, 1 if bridge_ok else 0, bridge_latency_ms),
        )
        conn.execute("DELETE FROM vpn_peer_samples WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM vpn_bridge_samples WHERE ts < ?", (cutoff,))


def load_vpn_peer_samples(hours: int = 24) -> list[dict]:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = get_conn().execute(
        "SELECT ts, pubkey, rx_bytes, tx_bytes, online FROM vpn_peer_samples "
        "WHERE ts >= ? ORDER BY ts", (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_vpn_bridge_samples(hours: int = 24) -> list[dict]:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = get_conn().execute(
        "SELECT ts, ok, latency_ms FROM vpn_bridge_samples WHERE ts >= ? ORDER BY ts",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Owner inbox (технический канал в приложении: ритуалы, одобрения, сбои)
# ---------------------------------------------------------------------------

def append_inbox(
    type_: str,
    body: str,
    title: str = "",
    importance: str = "NONE",
    payload: dict | None = None,
    ts: str | None = None,
) -> int:
    """Добавляет запись в owner_inbox. Возвращает id."""
    ts_v = ts or datetime.now().isoformat()
    payload_v = json.dumps(payload, ensure_ascii=False) if payload else None
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO owner_inbox (ts, type, importance, title, body, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts_v, type_, importance, title, body, payload_v),
        )
        return int(cur.lastrowid or 0)


def list_inbox(since_id: int = 0, limit: int = 200, unread_only: bool = False) -> list[dict]:
    """История тех-чата. since_id — id, после которого вернуть новые."""
    q = "SELECT id, ts, type, importance, title, body, payload, is_read, action FROM owner_inbox WHERE id > ?"
    args: list = [since_id]
    if unread_only:
        q += " AND is_read = 0"
    q += " ORDER BY id ASC LIMIT ?"
    args.append(limit)
    rows = get_conn().execute(q, args).fetchall()
    out = []
    for r in rows:
        out.append({
            "id":         r["id"],
            "ts":         r["ts"],
            "type":       r["type"],
            "importance": r["importance"],
            "title":      r["title"],
            "body":       r["body"],
            "payload":    json.loads(r["payload"]) if r["payload"] else None,
            "is_read":    bool(r["is_read"]),
            "action":     r["action"],
        })
    return out


def mark_inbox_read(id_: int) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("UPDATE owner_inbox SET is_read=1 WHERE id=?", (id_,))
        return cur.rowcount > 0


def set_inbox_action(id_: int, action: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("UPDATE owner_inbox SET action=?, is_read=1 WHERE id=?", (action, id_))
        return cur.rowcount > 0


def cleanup_inbox(older_than_days: int = 30) -> int:
    """Удаляет записи старше N дней. Возвращает удалённое количество."""
    cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM owner_inbox WHERE ts < ?", (cutoff,))
        return cur.rowcount


# ---------------------------------------------------------------------------
# User-to-user messaging (через Миру как посредника)
# ---------------------------------------------------------------------------

def add_pending_send(
    from_user_id: str,
    to_user_id: str,
    target_name: str,
    body: str,
    ttl_seconds: int = 600,
) -> int:
    """Создаёт pending-запись. Возвращает её id."""
    now = datetime.now()
    expires = now + timedelta(seconds=ttl_seconds)
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO pending_sends (from_user_id, to_user_id, target_name, body, ts, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (from_user_id, to_user_id, target_name, body, now.isoformat(), expires.isoformat()),
        )
        return int(cur.lastrowid or 0)


def get_pending_send(pending_id: int, from_user_id: str) -> dict | None:
    """Достаёт pending-запись, ПРИНАДЛЕЖАЩУЮ from_user_id. Защита от чужих id."""
    row = get_conn().execute(
        "SELECT id, from_user_id, to_user_id, target_name, body, ts, expires_at "
        "FROM pending_sends WHERE id = ? AND from_user_id = ?",
        (pending_id, from_user_id),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def delete_pending_send(pending_id: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM pending_sends WHERE id = ?", (pending_id,))


def cleanup_pending_sends() -> int:
    """Удаляет истёкшие pending (TTL). Возвращает количество удалённых."""
    now = datetime.now().isoformat()
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM pending_sends WHERE expires_at < ?", (now,))
        return cur.rowcount


def deliver_user_message(
    from_user_id: str,
    from_name: str,
    to_user_id: str,
    body: str,
) -> int:
    """Сохраняет доставленное сообщение в user_messages. Возвращает id."""
    ts = datetime.now().isoformat()
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO user_messages (from_user_id, from_name, to_user_id, body, ts, delivered, seen) "
            "VALUES (?, ?, ?, ?, ?, 1, 0)",
            (from_user_id, from_name, to_user_id, body, ts),
        )
        return int(cur.lastrowid or 0)


def list_unseen_messages(to_user_id: str, limit: int = 10) -> list[dict]:
    """Сообщения, которые Мира ещё НЕ зачитала получателю."""
    rows = get_conn().execute(
        "SELECT id, from_user_id, from_name, body, ts FROM user_messages "
        "WHERE to_user_id = ? AND seen = 0 ORDER BY id ASC LIMIT ?",
        (to_user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_messages_seen(to_user_id: str) -> int:
    """Помечает все непрочитанные сообщения как seen после того, как Мира
    их зачитала. Возвращает количество отмеченных."""
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "UPDATE user_messages SET seen = 1 WHERE to_user_id = ? AND seen = 0",
            (to_user_id,),
        )
        return cur.rowcount
