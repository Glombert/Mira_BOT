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
import logging

logger = logging.getLogger("Ouroborus")

SYNC_DIRS   = ["memory", "versions"]
GDRIVE_BASE = "gdrive:Mira"   # папка на Google Drive (без RCLONE_REMOTE)


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
    Запускается в фоне после write_file / excel_write.
    Пользователь сразу видит файл на своём диске.
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

    threading.Thread(target=_run, daemon=True).start()


def sync_inbox_from_drive(user_id: str) -> None:
    """
    Копирует gdrive:Mira/workspace/{user_id}/inbox/ → workspace/{user_id}/inbox/
    Запускается в фоне перед list_files / read_file.
    Мира видит файлы которые пользователь положил на диск.
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

    threading.Thread(target=_run, daemon=True).start()


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
