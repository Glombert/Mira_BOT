"""
tools/self_tools.py — инструменты самосознания Миры.

Позволяют Мире читать собственный код, конфиги и структуру проекта.
Доступ строго ограничен whitelist — .env, memory/, workspace/ недоступны.
"""

import os

# Файлы в корне проекта, которые Мира может читать
_READABLE_ROOT = {
    "agent.py", "conclave.py", "router.py", "providers.py",
    "telegram_bot.py", "persona.json", "PRINCIPLES.md",
    "requirements.txt", "README.md", "PLAN.md",
}

# Папки, содержимое которых Мира может читать
_READABLE_DIRS = {"agents", "tools", "profiles", "web", "scripts"}


def list_self() -> dict:
    """
    Показывает структуру проекта: файлы корня и содержимое разрешённых папок.
    Используется для самоизучения — Мира узнаёт из чего она состоит.
    """
    result = {}

    root_files = []
    for name in sorted(_READABLE_ROOT):
        if os.path.isfile(name):
            size = os.path.getsize(name)
            root_files.append(f"{name} ({size} байт)")
    result["root"] = root_files

    for d in sorted(_READABLE_DIRS):
        if os.path.isdir(d):
            files = []
            for fname in sorted(os.listdir(d)):
                fpath = os.path.join(d, fname)
                if os.path.isfile(fpath) and not fname.startswith("."):
                    size = os.path.getsize(fpath)
                    files.append(f"{fname} ({size} байт)")
            result[d] = files

    return {"ok": True, "structure": result}


def read_self(path: str) -> dict:
    """
    Читает файл проекта по whitelist.

    Разрешены:
      - корневые файлы из _READABLE_ROOT
      - файлы в agents/, tools/, profiles/

    Запрещены: .env, memory/, workspace/, logs/, versions/, .git/
    """
    path = path.strip().lstrip("/").lstrip("./")
    parts = path.replace("\\", "/").split("/")

    if len(parts) == 1:
        if parts[0] not in _READABLE_ROOT:
            return {
                "ok": False,
                "error": f"Файл не разрешён для чтения: {path}. "
                         f"Разрешены: {', '.join(sorted(_READABLE_ROOT))}",
            }
        full_path = parts[0]

    elif len(parts) == 2 and parts[0] in _READABLE_DIRS:
        full_path = os.path.join(parts[0], parts[1])
        if not os.path.exists(full_path):
            return {"ok": False, "error": f"Файл не найден: {path}"}

    else:
        return {
            "ok": False,
            "error": f"Путь не разрешён: {path}. "
                     f"Доступные папки: {', '.join(sorted(_READABLE_DIRS))}",
        }

    if not os.path.isfile(full_path):
        return {"ok": False, "error": f"Не является файлом: {path}"}

    try:
        with open(full_path, encoding="utf-8") as f:
            content = f.read()
        return {"ok": True, "path": path, "content": content, "size": len(content)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
