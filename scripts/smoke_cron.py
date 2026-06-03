#!/usr/bin/env python3
"""smoke_cron.py — обёртка для запуска smoke-suite по cron'у на VPS.

Запускает scripts/smoke.sh --local --quiet. При fail (exit != 0) —
шлёт владельцу уведомление через notify_owner (Telegram + FCM).

Cron-установка (06:00 UTC = 09:00 МСК = 16:00 Хабаровск):
  crontab -e
  0 6 * * * /root/mira_agent/venv/bin/python /root/mira_agent/scripts/smoke_cron.py >> /root/mira_smoke.log 2>&1
"""
import subprocess
import sys
import os
import re
import time
from datetime import datetime

# ANSI-цвета smoke.sh (\x1b[..m) не нужны в Telegram/FCM — режут читаемость.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
# REPO нужен в sys.path, чтобы импортировать memory_crypto / tools.*
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# Подгружаем .env чтобы tools.access_tools.notify_owner смог отправить
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))

import memory_crypto
memory_crypto.init()


def _run_smoke():
    return subprocess.run(
        ["./scripts/smoke.sh", "--local", "--quiet"],
        capture_output=True, text=True, timeout=120,
    )


def main() -> int:
    print(f"[{datetime.utcnow().isoformat()}Z] smoke-suite start")
    result = _run_smoke()
    # Транзиентный сетевой блип (curl got: 000) не должен дёргать владельца
    # ложной тревогой. Реальный сбой провалится и со второй попытки.
    if result.returncode != 0:
        print("smoke fail — перепроверяю через 20с (отсев транзиента)…")
        time.sleep(20)
        result = _run_smoke()
    ok = result.returncode == 0
    summary = _ANSI.sub("", result.stdout or "")[-1500:]
    print(summary)
    if result.stderr:
        print("STDERR:", result.stderr[-500:])
    print(f"[{datetime.utcnow().isoformat()}Z] smoke-suite {'OK' if ok else 'FAIL'} ({result.returncode})")

    if not ok:
        try:
            from tools.access_tools import notify_owner
            # Берём последние 1200 символов вывода + заголовок.
            # FCM и Telegram оба покажут.
            tail = "\n".join(summary.splitlines()[-30:])
            notify_owner(
                f"⚠ Smoke-suite упал на проде ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC)\n\n"
                f"{tail}\n\n"
                f"Полный лог: /root/mira_smoke.log"
            )
        except Exception as e:
            print(f"notify_owner failed: {e}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
