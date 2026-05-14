"""Однократная миграция JSON-state → SQLite (memory/mira.db).

Запуск:
    python -m tools.migrate_state            # обычный режим
    python -m tools.migrate_state --dry-run  # без записи, только проверка

Идемпотентно: повторный запуск перезапишет существующие строки тем же
содержимым. JSON-файлы НЕ удаляются — остаются как бэкап.

Мигрируется:
    memory/{user_id}.json           → user_profiles
    memory/sessions/{user_id}.json  → sessions
    memory/scheduled_tasks.json     → reminders (плоский список)
    memory/reflections.json         → reflections
    memory/gdrive/{user_id}.json    → gdrive_tokens

Игнорируется:
    memory/chroma/      — векторная база ChromaDB (свой формат)
    memory/templates/   — шаблоны (пока не мигрируем)
    memory/decisions.log
    memory/.heartbeat*
    memory/evolution_counter.json
    memory/metrics/     — JSONL-файлы метрик
"""

import argparse
import json
import os
import sys

# Импорт db откладываем — нужен корректный CWD для memory/mira.db
SKIP_FILES = {
    "reflections.json",  # обрабатываем отдельно
    "scheduled_tasks.json",  # обрабатываем отдельно
    "evolution_counter.json",
}


def _load_json_file(path: str):
    """Читает JSON-файл с прозрачным расшифрованием через memory_crypto."""
    try:
        import memory_crypto
        return memory_crypto.load_json(path)
    except Exception:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def migrate_profiles(memory_dir: str, dry_run: bool) -> int:
    from tools import db
    count = 0
    for fname in sorted(os.listdir(memory_dir)):
        if not fname.endswith(".json") or fname in SKIP_FILES:
            continue
        path = os.path.join(memory_dir, fname)
        if not os.path.isfile(path):
            continue
        user_id = fname[:-5]
        try:
            data = _load_json_file(path)
        except Exception as e:
            print(f"  [!] {fname}: ошибка чтения — {e}")
            continue
        if not isinstance(data, dict):
            print(f"  [!] {fname}: не dict, пропуск")
            continue
        if not dry_run:
            db.save_user_profile(user_id, data)
        print(f"  [+] profile: {user_id}")
        count += 1
    return count


def migrate_sessions(memory_dir: str, dry_run: bool) -> int:
    from tools import db
    sessions_dir = os.path.join(memory_dir, "sessions")
    if not os.path.isdir(sessions_dir):
        return 0
    count = 0
    for fname in sorted(os.listdir(sessions_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(sessions_dir, fname)
        user_id = fname[:-5]
        try:
            data = _load_json_file(path)
        except Exception as e:
            print(f"  [!] sessions/{fname}: ошибка — {e}")
            continue
        if not isinstance(data, list):
            print(f"  [!] sessions/{fname}: не list, пропуск")
            continue
        if not dry_run:
            db.save_session(user_id, data)
        print(f"  [+] session: {user_id} ({len(data)} сообщений)")
        count += 1
    return count


def migrate_reminders(memory_dir: str, dry_run: bool) -> int:
    from tools import db
    path = os.path.join(memory_dir, "scheduled_tasks.json")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            tasks = json.load(f)
    except Exception as e:
        print(f"  [!] scheduled_tasks.json: {e}")
        return 0
    if not isinstance(tasks, list):
        return 0
    count = 0
    for t in tasks:
        if not isinstance(t, dict) or "id" not in t:
            continue
        if dry_run:
            print(f"  [+] reminder: {t.get('id')} ({t.get('status')})")
            count += 1
            continue
        conn = db.get_conn()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO reminders "
                "(id, user_id, trigger_at, message, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    t["id"],
                    t.get("user_id", ""),
                    t.get("trigger_at", ""),
                    t.get("message", ""),
                    t.get("status", "pending"),
                    t.get("created_at", ""),
                ),
            )
        print(f"  [+] reminder: {t['id']} ({t.get('status')})")
        count += 1
    return count


def migrate_reflections(memory_dir: str, dry_run: bool) -> int:
    from tools import db
    path = os.path.join(memory_dir, "reflections.json")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [!] reflections.json: {e}")
        return 0
    if not isinstance(data, list):
        return 0
    if dry_run:
        return len(data)
    # Чтобы не плодить дубликаты при повторном запуске — очищаем перед вставкой
    conn = db.get_conn()
    with conn:
        conn.execute("DELETE FROM reflections")
        for entry in data:
            if isinstance(entry, dict):
                date    = entry.get("date", "")
                content = entry.get("content", "")
            else:
                date    = ""
                content = str(entry)
            conn.execute(
                "INSERT INTO reflections (date, content) VALUES (?, ?)",
                (date, content),
            )
    print(f"  [+] reflections: {len(data)} записей")
    return len(data)


def migrate_gdrive_tokens(memory_dir: str, dry_run: bool) -> int:
    from tools import db
    gdrive_dir = os.path.join(memory_dir, "gdrive")
    if not os.path.isdir(gdrive_dir):
        return 0
    count = 0
    for fname in sorted(os.listdir(gdrive_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(gdrive_dir, fname)
        user_id = fname[:-5]
        try:
            data = _load_json_file(path)
        except Exception as e:
            print(f"  [!] gdrive/{fname}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        if not dry_run:
            db.save_gdrive_token(user_id, data)
        print(f"  [+] gdrive_token: {user_id}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="не писать в БД")
    parser.add_argument("--memory-dir", default="memory")
    args = parser.parse_args()

    memory_dir = args.memory_dir
    if not os.path.isdir(memory_dir):
        print(f"[-] {memory_dir}/ не найден. Запусти из корня проекта.")
        return 1

    # Загружаем .env чтобы memory_crypto увидел MEMORY_ENCRYPTION_KEY
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # Инициализируем память (для расшифровки старых файлов и шифрования новой БД)
    try:
        import memory_crypto
        memory_crypto.init()
        if memory_crypto.is_enabled():
            print("[*] Шифрование включено — данные будут перешифрованы из JSON в БД.")
    except Exception:
        pass

    from tools import db
    db.init_db()
    print(f"[*] БД: {db.DB_PATH}")
    print(f"[*] Источник: {memory_dir}/")
    if args.dry_run:
        print("[*] DRY-RUN: ничего не записывается\n")

    print("\n--- Профили ---")
    n_profiles = migrate_profiles(memory_dir, args.dry_run)

    print("\n--- Сессии ---")
    n_sessions = migrate_sessions(memory_dir, args.dry_run)

    print("\n--- Напоминания ---")
    n_reminders = migrate_reminders(memory_dir, args.dry_run)

    print("\n--- Рефлексии ---")
    n_refls = migrate_reflections(memory_dir, args.dry_run)

    print("\n--- Google Drive токены ---")
    n_tokens = migrate_gdrive_tokens(memory_dir, args.dry_run)

    print("\n--- Итого ---")
    print(f"  Профилей:      {n_profiles}")
    print(f"  Сессий:        {n_sessions}")
    print(f"  Напоминаний:   {n_reminders}")
    print(f"  Рефлексий:     {n_refls}")
    print(f"  Drive-токенов: {n_tokens}")
    print(f"\n[*] Готово{'. (dry-run, БД не изменена)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
