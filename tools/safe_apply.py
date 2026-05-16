"""tools/safe_apply.py — атомарное применение мульти-файл diff с откатом.

Слой который связывает три предыдущих этапа:
    diff_tools  — парсинг и расчёт нового контента
    self_edit   — whitelist и валидация синтаксиса
    safe_apply  — фактическая запись на диск с гарантией: либо ВСЁ применилось
                  и smoke-test прошёл, либо НИЧЕГО не изменилось.

Алгоритм:
    1. parse_multi_diff(diff_text)
    2. check_all_paths — все пути в whitelist?
    3. Создать versions/{timestamp}/ для бэкапов
    4. Для каждого FileChange:
        a. бэкапим оригинал (если есть)
        b. считаем новый контент через apply_change
        c. validate_content (ast/json)
        d. пишем на диск
        e. при любой ошибке — откат всех применённых
    5. Smoke-test (опциональный) — импорт ключевых модулей подпроцессом
    6. Если всё ок — возвращаем (True, summary, [затронутые_файлы])
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from tools.diff_tools import parse_multi_diff, apply_change, extract_paths, FileChange
from tools.self_edit  import check_all_paths, validate_content

logger = logging.getLogger("Ouroborus")


@dataclass
class ApplyResult:
    ok:             bool
    message:        str
    touched_paths:  list[str]
    backup_dir:     str | None = None
    smoke_stderr:   str | None = None


def _default_smoke_test(project_root: str) -> tuple[bool, str]:
    """По умолчанию: импорт ключевых модулей в подпроцессе.

    Если хоть один не импортится — значит код сломан, откатываемся.
    Не импортим всё подряд — берём верх пирамиды зависимостей.
    """
    code = (
        "import agent; "
        "import providers; "
        "import router; "
        "import conclave; "
        "from tools import db, diff_tools, self_edit; "
        "print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=30, cwd=project_root,
        )
    except subprocess.TimeoutExpired:
        return False, "smoke-test превысил 30s timeout"
    except Exception as e:
        return False, f"не удалось запустить smoke-test: {e}"

    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or "exit nonzero").strip()


def _backup_path(backup_dir: str, rel_path: str) -> str:
    """Где лежит бэкап файла rel_path внутри backup_dir."""
    return os.path.join(backup_dir, rel_path)


def _make_backup_dir(project_root: str) -> str:
    """Создаёт уникальную папку versions/{ts}/ для этого применения."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = os.path.join(project_root, "versions", f"evolve_{ts}")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _backup_file(full_path: str, rel_path: str, backup_dir: str) -> None:
    """Копирует full_path в backup_dir/rel_path."""
    dest = _backup_path(backup_dir, rel_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(full_path, dest)


def _rollback(applied: list[tuple[str, bool]], project_root: str, backup_dir: str) -> None:
    """Восстанавливает все применённые изменения из бэкапа.

    applied — [(rel_path, existed_before_apply)]. Идём в ОБРАТНОМ порядке.
    """
    for rel_path, existed in reversed(applied):
        full = os.path.join(project_root, rel_path)
        if existed:
            backup = _backup_path(backup_dir, rel_path)
            if os.path.exists(backup):
                os.makedirs(os.path.dirname(full), exist_ok=True)
                shutil.copy2(backup, full)
                logger.info(f"rollback: восстановлен {rel_path}")
        else:
            # Файл был создан этим применением — удаляем
            if os.path.exists(full):
                os.remove(full)
                logger.info(f"rollback: удалён созданный {rel_path}")


def safe_apply(
    diff_text:     str,
    project_root:  str = ".",
    smoke_test_fn: Optional[Callable[[str], tuple[bool, str]]] = _default_smoke_test,
) -> ApplyResult:
    """Применяет мульти-файл diff атомарно. См. docstring модуля."""
    # 1. Парсинг
    try:
        changes = parse_multi_diff(diff_text)
    except ValueError as e:
        return ApplyResult(False, f"Невалидный diff: {e}", [])

    if not changes:
        return ApplyResult(False, "Diff не содержит ни одной секции файла", [])

    # 2. Whitelist
    paths = list(extract_paths(changes))
    ok, problems = check_all_paths(paths)
    if not ok:
        msg = "Запрещённые пути:\n" + "\n".join(f"  • {p}" for p in problems)
        return ApplyResult(False, msg, [])

    # 3. Бэкап-директория
    backup_dir = _make_backup_dir(project_root)
    logger.info(f"safe_apply: бэкап в {backup_dir}")

    # 4. Применение по одному файлу
    applied: list[tuple[str, bool]] = []  # (rel_path, existed_before)
    try:
        for change in changes:
            full = os.path.join(project_root, change.path)
            existed = os.path.exists(full)

            if existed:
                _backup_file(full, change.path, backup_dir)

            if change.action == "delete":
                if existed:
                    os.remove(full)
                applied.append((change.path, existed))
                continue

            existing_content = None
            if existed:
                with open(full, encoding="utf-8") as f:
                    existing_content = f.read()

            ok_change, result = apply_change(existing_content, change)
            if not ok_change:
                raise RuntimeError(f"{change.path}: {result}")
            new_content = result

            ok_val, err = validate_content(change.path, new_content)
            if not ok_val:
                raise RuntimeError(err)

            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_content)
            applied.append((change.path, existed))
            logger.info(
                f"safe_apply: {change.action} {change.path} "
                f"({'new' if not existed else 'modified'})"
            )

        # 5. Smoke-test
        if smoke_test_fn is not None:
            ok_smoke, smoke_err = smoke_test_fn(project_root)
            if not ok_smoke:
                raise RuntimeError(f"smoke-test упал: {smoke_err}")

        return ApplyResult(
            ok            = True,
            message       = f"Применено {len(applied)} файлов",
            touched_paths = [p for p, _ in applied],
            backup_dir    = backup_dir,
        )

    except Exception as e:
        logger.warning(f"safe_apply: откат из-за {e}")
        _rollback(applied, project_root, backup_dir)
        return ApplyResult(
            ok            = False,
            message       = f"Не применено: {e}",
            touched_paths = [],
            backup_dir    = backup_dir,
        )
