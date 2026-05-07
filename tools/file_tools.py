"""
tools/file_tools.py — инструменты для работы с файлами пользователя.

Главное правило: Мира работает ТОЛЬКО внутри workspace/{user_id}/.
Выйти за пределы этой папки невозможно — _resolve_path() это проверяет.

Структура workspace:
    workspace/
    └── {user_id}/
        ├── inbox/    ← пользователь кидает файлы сюда
        ├── output/   ← Мира кладёт результаты сюда
        ├── temp/     ← временные файлы (чистятся через 7 дней)
        └── .undo/    ← бэкапы до overwrite (последние 10)
"""

import os
from datetime import datetime

WORKSPACE_ROOT  = "workspace"
MAX_FILE_SIZE   = 5 * 1024 * 1024   # 5 MB — лимит на чтение и запись
MAX_WS_SIZE     = 100 * 1024 * 1024  # 100 MB — лимит workspace пользователя
MAX_UNDO_SLOTS  = 10                 # сколько отмен хранить


# ---------------------------------------------------------------------------
# Внутренние функции
# ---------------------------------------------------------------------------

def _resolve_path(user_id: str, relative_path: str) -> str:
    """
    Принимает user_id и относительный путь (например "inbox/data.xlsx").
    Возвращает абсолютный путь внутри workspace/{user_id}/.

    Если путь пытается выйти за пределы папки (например "../../../etc/passwd") —
    бросает исключение.

    Добавляем os.sep при проверке: без него "cli_andrey_evil" прошло бы
    проверку startswith("cli_andrey"), что является уязвимостью.
    """
    user_root = os.path.realpath(os.path.join(WORKSPACE_ROOT, user_id))
    target    = os.path.realpath(os.path.join(user_root, relative_path))

    if not (target == user_root or target.startswith(user_root + os.sep)):
        raise PermissionError(
            f"Доступ запрещён: путь '{relative_path}' выходит за пределы workspace."
        )
    return target


def _get_workspace_size(user_id: str) -> int:
    """Считает общий размер workspace пользователя в байтах."""
    user_root = os.path.join(WORKSPACE_ROOT, user_id)
    if not os.path.isdir(user_root):
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(user_root):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _save_undo(user_id: str, relative_path: str, target: str) -> None:
    """
    Сохраняет копию файла в .undo/ перед перезаписью.
    Хранит до MAX_UNDO_SLOTS файлов, старые удаляются.
    """
    undo_dir = os.path.join(WORKSPACE_ROOT, user_id, ".undo")
    os.makedirs(undo_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = relative_path.replace("/", "_").replace("\\", "_")
    backup_name = f"{ts}_{safe_name}"
    backup_path = os.path.join(undo_dir, backup_name)

    try:
        import shutil
        shutil.copy2(target, backup_path)
    except Exception:
        pass

    # Чистим старые бэкапы если их больше MAX_UNDO_SLOTS
    try:
        entries = sorted(os.listdir(undo_dir))
        while len(entries) > MAX_UNDO_SLOTS:
            os.remove(os.path.join(undo_dir, entries.pop(0)))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Публичные инструменты — вызываются агентом через execute_tool()
# ---------------------------------------------------------------------------

def list_files(user_id: str, subdir: str = "") -> dict:
    """
    Возвращает список файлов и папок внутри workspace/{user_id}/{subdir}.

    Возвращает:
        {"ok": True,  "files": ["inbox/", "output/", "temp/", "data.xlsx"]}
        {"ok": False, "error": "описание ошибки"}
    """
    try:
        target = _resolve_path(user_id, subdir)

        if not os.path.exists(target):
            return {"ok": False, "error": f"Папка '{subdir or 'workspace'}' не найдена."}
        if not os.path.isdir(target):
            return {"ok": False, "error": f"'{subdir}' — это файл, а не папка."}

        entries = []
        for name in sorted(os.listdir(target)):
            if name == ".undo":
                continue  # скрываем служебную папку
            full = os.path.join(target, name)
            entries.append(name + "/" if os.path.isdir(full) else name)

        return {"ok": True, "files": entries}

    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Неожиданная ошибка: {e}"}


def read_file(user_id: str, relative_path: str) -> dict:
    """
    Читает текстовый файл из workspace/{user_id}/{relative_path}.

    Возвращает:
        {"ok": True, "content": "...", "size_bytes": N}
        {"ok": False, "error": "..."}

    Лимит: MAX_FILE_SIZE (5 MB). Только UTF-8.
    """
    try:
        target = _resolve_path(user_id, relative_path)

        if not os.path.exists(target):
            return {"ok": False, "error": f"Файл '{relative_path}' не найден."}
        if not os.path.isfile(target):
            return {"ok": False, "error": f"'{relative_path}' — это папка, а не файл."}

        size = os.path.getsize(target)
        if size > MAX_FILE_SIZE:
            return {
                "ok": False,
                "error": f"Файл слишком большой ({size // 1024} KB). Максимум — {MAX_FILE_SIZE // 1024 // 1024} MB."
            }

        with open(target, "r", encoding="utf-8") as f:
            content = f.read()

        return {"ok": True, "content": content, "size_bytes": size}

    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except UnicodeDecodeError:
        return {"ok": False, "error": "Файл не является текстовым (бинарный формат)."}
    except Exception as e:
        return {"ok": False, "error": f"Неожиданная ошибка: {e}"}


def write_file(user_id: str, relative_path: str, content: str,
               overwrite: bool = False) -> dict:
    """
    Записывает текст в файл workspace/{user_id}/{relative_path}.

    Перед перезаписью (overwrite=True) сохраняет бэкап в .undo/.
    Проверяет лимит workspace (100 MB) до записи.

    Возвращает:
        {"ok": True, "path": "...", "size_bytes": N}
        {"ok": False, "error": "..."}
    """
    try:
        target = _resolve_path(user_id, relative_path)

        if os.path.exists(target) and not overwrite:
            return {
                "ok": False,
                "error": (
                    f"Файл '{relative_path}' уже существует. "
                    "Передай overwrite=True чтобы перезаписать."
                )
            }

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_FILE_SIZE:
            return {
                "ok": False,
                "error": f"Содержимое слишком большое ({len(content_bytes) // 1024} KB). Максимум — {MAX_FILE_SIZE // 1024 // 1024} MB."
            }

        # Проверяем лимит workspace
        ws_size = _get_workspace_size(user_id)
        if ws_size + len(content_bytes) > MAX_WS_SIZE:
            return {
                "ok": False,
                "error": f"Превышен лимит workspace ({ws_size // 1024 // 1024} MB из {MAX_WS_SIZE // 1024 // 1024} MB)."
            }

        # Бэкап перед перезаписью
        if os.path.exists(target) and overwrite:
            _save_undo(user_id, relative_path, target)

        os.makedirs(os.path.dirname(target), exist_ok=True)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        return {"ok": True, "path": relative_path, "size_bytes": len(content_bytes)}

    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Неожиданная ошибка: {e}"}


# ---------------------------------------------------------------------------
# /undo — восстановление последней версии файла
# ---------------------------------------------------------------------------

def undo_last(user_id: str) -> dict:
    """
    Восстанавливает последний перезаписанный файл из .undo/.

    Возвращает:
        {"ok": True, "restored": "inbox/data.txt"}
        {"ok": False, "error": "..."}
    """
    undo_dir = os.path.join(WORKSPACE_ROOT, user_id, ".undo")
    if not os.path.isdir(undo_dir):
        return {"ok": False, "error": "Нет сохранённых версий для отмены."}

    entries = sorted(os.listdir(undo_dir))
    if not entries:
        return {"ok": False, "error": "Нет сохранённых версий для отмены."}

    latest = entries[-1]
    backup_path = os.path.join(undo_dir, latest)

    # Имя файла: YYYYMMDD_HHMMSS_path_with_underscores
    # Восстанавливаем в output/ чтобы не затереть текущий файл без спроса
    import shutil
    restore_name = latest[16:]  # убираем временную метку
    restore_path = os.path.join(WORKSPACE_ROOT, user_id, "output", f"undo_{restore_name}")
    os.makedirs(os.path.dirname(restore_path), exist_ok=True)

    try:
        shutil.copy2(backup_path, restore_path)
        os.remove(backup_path)
        return {"ok": True, "restored": f"output/undo_{restore_name}"}
    except Exception as e:
        return {"ok": False, "error": f"Ошибка восстановления: {e}"}


def list_undo(user_id: str) -> dict:
    """Показывает доступные бэкапы для /undo."""
    undo_dir = os.path.join(WORKSPACE_ROOT, user_id, ".undo")
    if not os.path.isdir(undo_dir):
        return {"ok": True, "backups": []}
    entries = sorted(os.listdir(undo_dir))
    return {"ok": True, "backups": entries}
