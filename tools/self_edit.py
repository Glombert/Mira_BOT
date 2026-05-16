"""tools/self_edit.py — что Мире разрешено редактировать и как это валидировать.

Сердцевина безопасности /evolve. Два слоя защиты:

1. ALLOWED_PATTERNS — белый список путей. Всё что не подпадает — отказ.
   Никаких .env, memory/, workspace/, logs/, .git/, credentials.json.

2. validate_content — для .py через ast.parse, для .json через json.loads.
   Если новый контент не парсится — отказ. Это страхует от того что Мира
   нашлёпает синтаксических ошибок в diff.

Smoke-test (импорт модулей) делается уровнем выше, в safe-apply.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import os
from typing import Iterable

# Файлы которые /evolve имеет право трогать. Глобы matchаются на нормализованный
# относительный путь от корня проекта.
ALLOWED_PATTERNS: tuple[str, ...] = (
    # Главные модули
    "agent.py",
    "providers.py",
    "router.py",
    "conclave.py",
    "telegram_bot.py",
    "memory_manager.py",
    "memory_crypto.py",
    # Web
    "web/app.py",
    "web/security.py",
    # Конфиги (агенты, профили, персона)
    "agents/*.json",
    "profiles/*.json",
    "persona.json",
    # Инструменты — целиком
    "tools/*.py",
    # Тесты — Мира может расширять собственное покрытие
    "tests/*.py",
    "tests/conftest.py",
    "pytest.ini",
    # Документы
    "PRINCIPLES.md",
    "README.md",
    "requirements.txt",
)

# Эти подстроки/префиксы — твёрдый запрет даже если попадают под allowed
# (страхуем от ошибок в паттернах выше).
HARD_DENY_PREFIXES: tuple[str, ...] = (
    ".env",
    "memory/",
    "workspace/",
    "logs/",
    "versions/",
    ".git/",
    "credentials.json",
    "chat_history.json",
)


def is_path_safe(path: str) -> tuple[bool, str]:
    """Проверяет: relative, без '..', без leading '/', не пустой.

    Возвращает (True, "") или (False, причина).
    """
    if not path or not path.strip():
        return False, "пустой путь"

    p = path.strip().replace("\\", "/")

    if os.path.isabs(p) or p.startswith("/"):
        return False, "абсолютный путь запрещён"

    # `..` в любом сегменте отказ — даже если normpath сворачивает обратно
    # к разрешённому пути (agents/../agent.py → agent.py). Любое .. подозрительно.
    if ".." in p.split("/"):
        return False, "сегмент `..` в пути запрещён"

    return True, ""


def is_path_allowed(path: str) -> tuple[bool, str]:
    """Может ли /evolve этот путь редактировать. (ok, reason_if_not).

    Проверяем (в порядке): safe → не в hard-deny → подпадает под allowed-паттерн.
    """
    safe, why = is_path_safe(path)
    if not safe:
        return False, why

    normalized = os.path.normpath(path).replace("\\", "/")

    for deny in HARD_DENY_PREFIXES:
        if normalized == deny or normalized.startswith(deny):
            return False, f"путь в HARD_DENY ({deny})"

    for pattern in ALLOWED_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return True, ""

    return False, "путь не в ALLOWED_PATTERNS — расширение whitelist требует ручного решения"


def validate_content(path: str, content: str) -> tuple[bool, str]:
    """Синтаксическая проверка нового контента. (ok, error_or_empty).

    .py   → ast.parse
    .json → json.loads
    остальное → пропускаем (README.md и т.п.)
    """
    if path.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            return False, f"SyntaxError в {path}: {e.msg} (строка {e.lineno})"
        return True, ""

    if path.endswith(".json"):
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return False, f"Невалидный JSON в {path}: {e.msg} (строка {e.lineno})"
        return True, ""

    # .md, .txt, .ini — без синтаксической проверки
    return True, ""


def check_all_paths(paths: Iterable[str]) -> tuple[bool, list[str]]:
    """Прогон is_path_allowed по списку. Возвращает (все_ок, список_проблем)."""
    problems: list[str] = []
    for p in paths:
        ok, why = is_path_allowed(p)
        if not ok:
            problems.append(f"{p}: {why}")
    return len(problems) == 0, problems
