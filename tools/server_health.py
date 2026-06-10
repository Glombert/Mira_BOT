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


def health_report() -> str:
    """Детерминированный отчёт для ритуала server_health — без LLM.

    Проверка здоровья — это сравнение чисел с порогами, нейросеть здесь
    не добавляет ничего, кроме токенов. Формат совместим с доставкой
    ритуалов (#IMPORTANCE в конце).
    """
    r = server_health()
    lines = []

    db = r["db"]
    lines.append(f"mira.db: {db['size_mb']} MB" if db["ok"] else "mira.db: НЕ НАЙДЕНА")

    d = r["disk"]
    lines.append(f"Диск: свободно {d['free_gb']} GB из {d['total_gb']} GB (занято {d['used_percent']}%)")

    hb_names = {"bot": "бот", "web": "веб"}
    for key, hb in r["heartbeats"].items():
        label = hb_names.get(key, key)
        if hb["ok"]:
            lines.append(f"Heartbeat {label}: жив ({hb['age_seconds']}с назад)")
        elif hb["status"] == "stale":
            lines.append(f"Heartbeat {label}: ПРОТУХ ({hb['age_seconds']}с назад)")
        else:
            lines.append(f"Heartbeat {label}: ОТСУТСТВУЕТ")

    verdict = "Всё в порядке." if r["ok"] else "Есть проблемы — смотри выше."
    importance = "NONE" if r["ok"] else "MAJOR"
    return "\n".join(lines) + f"\n{verdict}\n#IMPORTANCE: {importance}"


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
