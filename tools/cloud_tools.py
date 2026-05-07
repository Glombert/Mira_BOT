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
import logging

logger = logging.getLogger("Ouroborus")

SYNC_DIRS   = ["memory", "versions"]


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
