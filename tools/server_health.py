"""tools/server_health.py — снимок здоровья сервера.

Собирает факты прямым кодом, а не через run_python: firejail-песочница
не видит memory/, из-за чего LLM-проверка в ритуале server_health давала
ложные «mira.db не найдена» и спамила владельцу.

Здесь же — сэмплер метрик (RAM/load/disk раз в 5 минут в SQLite) для
графиков owner-экрана «Сервер».
"""

import logging
import os
import shutil
import threading
import time

logger = logging.getLogger("Ouroboros")

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


SAMPLE_INTERVAL_SEC = 300


def _meminfo() -> dict[str, int]:
    """MemTotal/MemAvailable/SwapTotal/SwapFree из /proc/meminfo, в МБ."""
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                out[key] = int(rest.split()[0]) // 1024
    return out


def sample_metrics() -> dict:
    """Мгновенный срез: load average, RAM %, swap MB, диск %."""
    with open("/proc/loadavg") as f:
        load1 = float(f.read().split()[0])
    mem = _meminfo()
    mem_total = mem.get("MemTotal", 0) or 1
    mem_percent = round((mem_total - mem.get("MemAvailable", 0)) / mem_total * 100)
    swap_mb = mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)
    usage = shutil.disk_usage(MEMORY_DIR if os.path.isdir(MEMORY_DIR) else ".")
    return {
        "load1": load1,
        "mem_percent": mem_percent,
        "mem_total_mb": mem_total,
        "swap_mb": swap_mb,
        "disk_percent": round(usage.used / usage.total * 100),
    }


def uptime_days() -> float:
    with open("/proc/uptime") as f:
        return round(float(f.read().split()[0]) / 86400, 1)


def start_sampler() -> None:
    """Фоновый поток: сэмпл метрик раз в 5 минут в SQLite (retention 7 дней)."""
    from tools import db

    def _loop() -> None:
        while True:
            try:
                s = sample_metrics()
                db.save_server_metric(s["load1"], s["mem_percent"], s["swap_mb"], s["disk_percent"])
            except Exception as e:
                logger.warning(f"server_metrics sampler: {e}")
            try:
                from tools.vpn_tools import sample_vpn
                sample_vpn()
            except Exception as e:
                logger.warning(f"vpn sampler: {e}")
            time.sleep(SAMPLE_INTERVAL_SEC)

    threading.Thread(target=_loop, daemon=True).start()
    logger.info("server_metrics sampler запущен (5 мин)")


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
