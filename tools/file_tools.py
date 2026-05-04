"""
tools/file_tools.py — инструменты для работы с файлами пользователя.

Главное правило: Мира работает ТОЛЬКО внутри workspace/{user_id}/.
Выйти за пределы этой папки невозможно — resolve_path() это проверяет.

Структура workspace:
    workspace/
    └── {user_id}/
        ├── inbox/    ← пользователь кидает файлы сюда
        ├── output/   ← Мира кладёт результаты сюда
        └── temp/     ← временные файлы (чистятся через 7 дней)
"""

import os

# Корень workspace — все пути будут внутри этой папки
WORKSPACE_ROOT = "workspace"


# ---------------------------------------------------------------------------
# Внутренняя функция: проверка пути
# Пользователь не вызывает её напрямую — только другие функции модуля.
# ---------------------------------------------------------------------------

def _resolve_path(user_id: str, relative_path: str) -> str:
    """
    Принимает user_id и относительный путь (например "inbox/data.xlsx").
    Возвращает абсолютный путь внутри workspace/{user_id}/.

    Если путь пытается выйти за пределы папки (например "../../../etc/passwd") —
    бросает исключение. Это защита от случайных или намеренных ошибок.

    Пример:
        _resolve_path("cli_andrey", "inbox/data.xlsx")
        → "/home/mira/workspace/cli_andrey/inbox/data.xlsx"
    """
    # Собираем "идеальный" корень папки пользователя
    user_root = os.path.realpath(os.path.join(WORKSPACE_ROOT, user_id))

    # Собираем целевой путь
    target = os.path.realpath(os.path.join(user_root, relative_path))

    # Проверяем что target начинается с user_root + разделитель пути.
    # Важно добавлять os.sep: без него "workspace/cli_andrey_evil" прошло бы
    # проверку startswith("workspace/cli_andrey"), что является уязвимостью.
    if not (target == user_root or target.startswith(user_root + os.sep)):
        raise PermissionError(
            f"Доступ запрещён: путь '{relative_path}' выходит за пределы workspace."
        )

    return target


# ---------------------------------------------------------------------------
# Публичные функции — их будет вызывать агент
# ---------------------------------------------------------------------------

def list_files(user_id: str, subdir: str = "") -> dict:
    """
    Возвращает список файлов и папок внутри workspace/{user_id}/{subdir}.

    Аргументы:
        user_id  — идентификатор пользователя (например "cli_andrey")
        subdir   — подпапка (например "inbox"). Если пусто — корень workspace.

    Возвращает словарь:
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
            full = os.path.join(target, name)
            # Папки помечаем слешем для наглядности
            entries.append(name + "/" if os.path.isdir(full) else name)

        return {"ok": True, "files": entries}

    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Неожиданная ошибка: {e}"}


def read_file(user_id: str, relative_path: str) -> dict:
    """
    Читает текстовый файл из workspace/{user_id}/{relative_path}.

    Аргументы:
        user_id       — идентификатор пользователя
        relative_path — путь относительно workspace пользователя

    Возвращает:
        {"ok": True,  "content": "содержимое файла"}
        {"ok": False, "error": "описание ошибки"}

    Ограничение: только текстовые файлы (UTF-8).
    Бинарные файлы (картинки, Excel) — через специализированные инструменты.
    """
    try:
        target = _resolve_path(user_id, relative_path)

        if not os.path.exists(target):
            return {"ok": False, "error": f"Файл '{relative_path}' не найден."}

        if not os.path.isfile(target):
            return {"ok": False, "error": f"'{relative_path}' — это папка, а не файл."}

        # Ограничение на размер: не читаем файлы больше 1 MB
        # (чтобы не засорять контекст огромными файлами)
        size = os.path.getsize(target)
        if size > 1 * 1024 * 1024:
            return {
                "ok": False,
                "error": f"Файл слишком большой ({size // 1024} KB). Максимум — 1 MB."
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

    Аргументы:
        user_id       — идентификатор пользователя
        relative_path — путь относительно workspace пользователя
        content       — текст для записи
        overwrite     — разрешить перезапись если файл уже существует?
                        По умолчанию False — безопаснее.

    Возвращает:
        {"ok": True,  "path": "относительный путь к файлу"}
        {"ok": False, "error": "описание ошибки"}

    Папки создаются автоматически если их нет.
    """
    try:
        target = _resolve_path(user_id, relative_path)

        # Проверяем overwrite до записи
        if os.path.exists(target) and not overwrite:
            return {
                "ok": False,
                "error": (
                    f"Файл '{relative_path}' уже существует. "
                    f"Передай overwrite=True чтобы перезаписать."
                )
            }

        # Создаём промежуточные папки если их нет
        os.makedirs(os.path.dirname(target), exist_ok=True)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        return {"ok": True, "path": relative_path, "size_bytes": len(content.encode("utf-8"))}

    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Неожиданная ошибка: {e}"}
