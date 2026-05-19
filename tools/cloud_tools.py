"""
tools/cloud_tools.py — синхронизация с облаком через rclone.

Требует:
    rclone установлен (https://rclone.org)
    RCLONE_REMOTE=gdrive:mira_memory в .env

Что синхронизируется:
    memory/    — профили пользователей, история, журнал решений
    versions/  — резервные копии agent.py

Развёртывание на новой машине (три команды):
    rclone copy gdrive:mira_memory/memory ./memory
    rclone copy gdrive:mira_memory/versions ./versions
    python agent.py
"""

import os
import subprocess
import threading
import time
import logging

logger = logging.getLogger("Ouroboros")

SYNC_DIRS   = ["memory", "versions"]
# Папка на Google Drive. Переопределяется через .env (MIRA_GDRIVE_BASE),
# чтобы её можно было менять без правки кода.
GDRIVE_BASE = os.getenv("MIRA_GDRIVE_BASE", "gdrive:Mira")

# Throttle для sync_output/sync_inbox: leading-edge запуск + trailing повтор
# через COOLDOWN_S, чтобы серия из write_file не плодила параллельные rclone.
_THROTTLE_COOLDOWN_S = 10.0
_throttle_lock = threading.Lock()
_throttle_state: dict[tuple[str, str], dict] = {}


def _throttled_run(key: tuple[str, str], run_fn) -> None:
    """Запускает run_fn (rclone в потоке) с дросселированием.

    Первый вызов уходит сразу. Повторные в течение COOLDOWN — собираются
    в один отложенный trailing-запуск через Timer. Серия из N быстрых
    вызовов даёт максимум 2 rclone-процесса на ключ.
    """
    with _throttle_lock:
        st = _throttle_state.setdefault(key, {"running": False, "pending": False, "last": 0.0})
        now = time.time()
        if st["running"] or now - st["last"] < _THROTTLE_COOLDOWN_S:
            if not st["pending"]:
                st["pending"] = True
                delay = max(0.5, _THROTTLE_COOLDOWN_S - (now - st["last"]))
                threading.Timer(delay, lambda: _throttled_run(key, run_fn)).start()
            return
        st["running"] = True
        st["pending"] = False

    def _worker():
        try:
            run_fn()
        finally:
            with _throttle_lock:
                st["running"] = False
                st["last"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()


def _rclone_available() -> bool:
    """Проверяет что rclone установлен."""
    try:
        result = subprocess.run(
            ["rclone", "version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_remote() -> str | None:
    """Читает RCLONE_REMOTE из окружения."""
    remote = os.getenv("RCLONE_REMOTE", "").strip()
    return remote if remote else None


def cloud_sync() -> bool:
    """
    Синхронизирует memory/ и versions/ в облако.

    Использует rclone copy (не sync) — не удаляет файлы в облаке.
    Возвращает True при успехе, False при любой ошибке.
    """
    if not _rclone_available():
        print("[-] rclone не найден. Установи: https://rclone.org/install/")
        return False

    remote = _get_remote()
    if not remote:
        print("[-] RCLONE_REMOTE не задан в .env. Пример: RCLONE_REMOTE=gdrive:mira_memory")
        return False

    success = True
    for d in SYNC_DIRS:
        if not os.path.isdir(d):
            continue
        dest = f"{remote}/{d}"
        print(f"[Cloud] {d}/ → {dest} ...")
        result = subprocess.run(
            ["rclone", "copy", d, dest, "--progress"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"[-] Ошибка при синхронизации {d}: {result.stderr.strip()}")
            logger.error(f"cloud_sync {d}: {result.stderr.strip()}")
            success = False
        else:
            logger.info(f"cloud_sync: {d}/ → {dest} OK")

    if success:
        print("[*] Синхронизация с облаком завершена.")
    return success


def sync_output_to_drive(user_id: str) -> None:
    """
    Копирует workspace/{user_id}/output/ → gdrive:Mira/workspace/{user_id}/output/
    Запускается после write_file / excel_write. Через throttle — серия
    записей даёт максимум 2 rclone-процесса (см. _throttled_run).
    """
    if not _rclone_available():
        return
    src  = os.path.join("workspace", user_id, "output")
    dest = f"{GDRIVE_BASE}/workspace/{user_id}/output"
    if not os.path.isdir(src):
        return

    def _run():
        try:
            result = subprocess.run(
                ["rclone", "copy", src, dest, "--update"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                logger.info(f"cloud: output/{user_id} → Drive OK")
            else:
                logger.warning(f"cloud: sync output failed: {result.stderr[:200]}")
        except Exception as e:
            logger.warning(f"cloud: sync output error: {e}")

    _throttled_run(("output", user_id), _run)


def sync_inbox_from_drive(user_id: str) -> None:
    """
    Копирует gdrive:Mira/workspace/{user_id}/inbox/ → workspace/{user_id}/inbox/
    Запускается перед list_files / read_file. Дросселируется так же,
    как sync_output_to_drive.
    """
    if not _rclone_available():
        return
    src  = f"{GDRIVE_BASE}/workspace/{user_id}/inbox"
    dest = os.path.join("workspace", user_id, "inbox")
    os.makedirs(dest, exist_ok=True)

    def _run():
        try:
            result = subprocess.run(
                ["rclone", "copy", src, dest, "--update"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                logger.info(f"cloud: Drive/inbox/{user_id} → local OK")
            else:
                logger.debug(f"cloud: sync inbox: {result.stderr[:100]}")
        except Exception as e:
            logger.warning(f"cloud: sync inbox error: {e}")

    _throttled_run(("inbox", user_id), _run)


def cloud_restore() -> bool:
    """
    Восстанавливает memory/ и versions/ из облака.

    Скачивает файлы которых нет локально (не перезаписывает существующие).
    Возвращает True при успехе, False при ошибке.
    """
    if not _rclone_available():
        print("[-] rclone не найден. Установи: https://rclone.org/install/")
        return False

    remote = _get_remote()
    if not remote:
        print("[-] RCLONE_REMOTE не задан в .env.")
        return False

    success = True
    for d in SYNC_DIRS:
        src = f"{remote}/{d}"
        os.makedirs(d, exist_ok=True)
        print(f"[Cloud] {src} → {d}/ ...")
        result = subprocess.run(
            ["rclone", "copy", src, d, "--progress"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"[-] Ошибка при восстановлении {d}: {result.stderr.strip()}")
            logger.error(f"cloud_restore {d}: {result.stderr.strip()}")
            success = False
        else:
            logger.info(f"cloud_restore: {src} → {d}/ OK")

    if success:
        print("[*] Восстановление из облака завершено.")
    return success
