"""tools/server_health.py — снимок здоровья сервера.

Собирает факты прямым кодом, а не через run_python: firejail-песочница
не видит memory/, из-за чего LLM-проверка в ритуале server_health давала
ложные «mira.db не найдена» и спамила владельцу.
"""

import os
import shutil
import time

from tools.db import DB_PATH

MEMORY_DIR = os.path.dirname(DB_PATH) or "memory"
HEARTBEAT_BOT = os.path.join(MEMORY_DIR, ".heartbeat")
HEARTBEAT_WEB = os.path.join(MEMORY_DIR, ".heartbeat_web")

# Метки пишутся каждые 30 сек; 120 — запас на GC-паузы и нагрузку.
HEARTBEAT_MAX_AGE = 120

DISK_MIN_FREE_GB = 1.0


def _heartbeat(path: str) -> dict:
    if not os.path.exists(path):
        return {"ok": False, "status": "missing"}
    age = round(time.time() - os.path.getmtime(path))
    return {"ok": age <= HEARTBEAT_MAX_AGE, "status": "fresh" if age <= HEARTBEAT_MAX_AGE else "stale", "age_seconds": age}


def server_health() -> dict:
    db = {"ok": os.path.exists(DB_PATH), "path": DB_PATH}
    if db["ok"]:
        db["size_mb"] = round(os.path.getsize(DB_PATH) / 1024 / 1024, 2)

    usage = shutil.disk_usage(MEMORY_DIR if os.path.isdir(MEMORY_DIR) else ".")
    free_gb = usage.free / 1024 ** 3
    disk = {
        "ok": free_gb >= DISK_MIN_FREE_GB,
        "total_gb": round(usage.total / 1024 ** 3, 1),
        "free_gb": round(free_gb, 1),
        "used_percent": round(usage.used / usage.total * 100),
    }

    heartbeats = {"bot": _heartbeat(HEARTBEAT_BOT), "web": _heartbeat(HEARTBEAT_WEB)}

    return {
        "ok": db["ok"] and disk["ok"] and all(h["ok"] for h in heartbeats.values()),
        "db": db,
        "disk": disk,
        "heartbeats": heartbeats,
    }
