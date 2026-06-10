"""Скрипт миграции: шифрует открытый текст в sessions.messages через Fernet.

Запускается ОДИН раз при включении MEMORY_ENCRYPTION_KEY. Идемпотентный —
повторный запуск не портит уже зашифрованные строки (пропускает префикс 'gAAAA').

ИСПОЛЬЗОВАНИЕ:
    MEMORY_ENCRYPTION_KEY=... python3 scripts/encrypt_db.py [--decrypt]

    --decrypt   обратная миграция (расшифровка).
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.paths import at_root

ENC_KEY = os.getenv("MEMORY_ENCRYPTION_KEY", "")
# Реальная БД лежит в memory/mira.db (см. tools/db.py DB_PATH).
DB_PATH = at_root("memory", "mira.db")

if not ENC_KEY:
    print("ERROR: установи MEMORY_ENCRYPTION_KEY в окружении")
    print("  export MEMORY_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')")
    sys.exit(1)

from cryptography.fernet import Fernet
fernet = Fernet(ENC_KEY.encode() if isinstance(ENC_KEY, str) else ENC_KEY)


def backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"mira.db.backup_before_encrypt_{ts}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"Бэкап создан: {backup_path}")
    return backup_path


def encrypt_db():
    """Шифрует sessions.messages где нет Fernet-префикса."""
    backup()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT user_id, messages FROM sessions")
    rows = cur.fetchall()

    encrypted = 0
    skipped = 0
    for row in rows:
        msg = row["messages"]
        if not msg or msg.startswith("gAAAA"):
            skipped += 1
            continue
        # Шифруем
        encrypted_msg = fernet.encrypt(msg.encode()).decode()
        cur.execute(
            "UPDATE sessions SET messages=? WHERE user_id=?",
            (encrypted_msg, row["user_id"]),
        )
        encrypted += 1

    conn.commit()
    conn.close()
    print(f"Зашифровано: {encrypted} строк, пропущено: {skipped}")


def decrypt_db():
    """Расшифровывает sessions.messages (обратная миграция)."""
    backup()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT user_id, messages FROM sessions")
    rows = cur.fetchall()

    decrypted = 0
    skipped = 0
    for row in rows:
        msg = row["messages"]
        if not msg or not msg.startswith("gAAAA"):
            skipped += 1
            continue
        try:
            plain = fernet.decrypt(msg.encode()).decode()
            cur.execute(
                "UPDATE sessions SET messages=? WHERE user_id=?",
                (plain, row["user_id"]),
            )
            decrypted += 1
        except Exception as e:
            print(f"Ошибка расшифровки {row['user_id']}: {e}")

    conn.commit()
    conn.close()
    print(f"Расшифровано: {decrypted} строк, пропущено: {skipped}")


if __name__ == "__main__":
    if "--decrypt" in sys.argv:
        print("⚠️  ОБРАТНАЯ МИГРАЦИЯ: расшифровка истории. Продолжить? (yes/no)")
        if input().strip().lower() == "yes":
            decrypt_db()
        else:
            print("Отмена.")
    else:
        print("Шифрование открытого текста в sessions.messages...")
        encrypt_db()
    print("Готово.")
