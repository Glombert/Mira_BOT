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
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from tools.diff_tools import parse_multi_diff, apply_change, extract_paths, FileChange

# Секреты НЕ должны утекать в дочерние процессы (smoke-test /evolve гоняет
# непроверенный код; git'у ключи тоже не нужны). Вырезаем по шаблону имени.
_SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSPHRASE|PASSWORD|DSN)", re.IGNORECASE)


def secret_free_env(**extra: str) -> dict:
    """os.environ без секретов (API_*/…TOKEN/…KEY/…) + extra-переопределения."""
    env = {k: v for k, v in os.environ.items()
           if not (_SECRET_ENV_RE.search(k) or k.startswith("API_"))}
    env.update(extra)
    return env
from tools.self_edit  import check_all_paths, validate_content

logger = logging.getLogger("Ouroboros")


# PRINCIPLES.md — защитные символы, которые /evolve-diff НЕ должен удалять.
# Раньше PRINCIPLES.md инжектился только в промпт LLM («честное слово»). Теперь
# safe_apply проверяет AST'ом, что эти функции остались определены — иначе откат.
_REQUIRED_SYMBOLS: dict[str, set[str]] = {
    "agent.py":            {"validate_code", "can_use", "smoke_test"},
    "tools/self_edit.py":  {"check_all_paths", "validate_content", "ALLOWED_PATTERNS"},
    "tools/shell_tools.py": {"run_python"},
    "web/security.py":     {"resolve_under", "safe_filename"},
    "tools/safe_apply.py": {"safe_apply", "_rollback", "check_principles"},
}


def _defined_symbols(source: str) -> set[str]:
    """Имена функций/классов/модульных присваиваний в Python-исходнике (AST)."""
    import ast
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return out


def check_principles(project_root: str, touched_paths: list[str],
                     backup_dir: str) -> tuple[bool, str]:
    """Проверяет, что diff не УДАЛИЛ защитный символ, который был ДО изменения.

    Сравниваем с бэкапом (pre-diff): защищаем только то, что реально
    присутствовало — иначе синтетические/новые файлы ложно отвергались бы.
    Возвращает (ok, reason)."""
    for rel in touched_paths:
        required = _REQUIRED_SYMBOLS.get(rel)
        if not required:
            continue
        backup_file = _backup_path(backup_dir, rel)
        if not os.path.exists(backup_file):
            continue  # файл создан этим diff'ом — нечего защищать
        try:
            with open(backup_file, encoding="utf-8") as f:
                before = _defined_symbols(f.read())
        except Exception:
            continue  # бэкап не-Python или нечитаем — не наш случай
        protected = required & before
        if not protected:
            continue
        full = os.path.join(project_root, rel)
        try:
            after = _defined_symbols(open(full, encoding="utf-8").read()) if os.path.exists(full) else set()
        except Exception as e:
            return False, f"{rel}: не парсится после diff ({e})"
        removed = protected - after
        if removed:
            return False, f"{rel}: diff удаляет защитные символы {sorted(removed)}"
    return True, ""


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


def _git_commit_changes(
    paths:        list[str],
    task_summary: str,
    project_root: str,
) -> tuple[bool, str]:
    """После успешного safe_apply делает git add + commit для затронутых файлов.

    Не пушит — push'ит отдельный cron. Если git не настроен или commit не
    прошёл — логируем но не откатываем файлы (они уже валидны, smoke прошёл).
    """
    if not paths:
        return False, "нет файлов для коммита"

    subject = (task_summary or "evolve").split("\n")[0].strip()[:70]
    if not subject:
        subject = "evolve"
    body = (
        f"Затронуто: {', '.join(paths)}\n\n"
        f"Применено через safe_apply (мульти-файл /evolve)."
    )
    if task_summary and len(task_summary) > 70:
        body = f"Задача:\n{task_summary}\n\n" + body

    full_message = f"evolve: {subject}\n\n{body}"

    # LANG=C — заставляем git отвечать на английском, чтобы парсить ошибки
    # независимо от локали системы (на VPS может быть ru_RU)
    env = secret_free_env(LANG="C", LC_ALL="C")

    try:
        # add
        r = subprocess.run(
            ["git", "add", "--"] + paths,
            capture_output=True, text=True, cwd=project_root, timeout=15, env=env,
        )
        if r.returncode != 0:
            return False, f"git add: {r.stderr.strip()}"

        # commit — Mira как author, host как committer
        r = subprocess.run(
            ["git", "-c", "commit.gpgsign=false",
             "commit",
             "--author", "Mira via /evolve <mira@bot.evolve>",
             "-m", full_message],
            capture_output=True, text=True, cwd=project_root, timeout=15, env=env,
        )
        if r.returncode != 0:
            err = r.stderr.strip() or r.stdout.strip()
            # Если коммит пустой (файлы не изменились реально) — это не ошибка
            if "nothing to commit" in err or "no changes added" in err:
                return False, "no changes to commit"
            return False, f"git commit: {err}"

        # Берём короткий хеш для лога
        r2 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=project_root, timeout=5, env=env,
        )
        sha = r2.stdout.strip() if r2.returncode == 0 else "?"
        return True, sha

    except subprocess.TimeoutExpired:
        return False, "git timeout"
    except Exception as e:
        return False, f"git error: {e}"


def safe_apply(
    diff_text:     str,
    project_root:  str = ".",
    smoke_test_fn: Optional[Callable[[str], tuple[bool, str]]] = _default_smoke_test,
    task_summary:  str = "",
    auto_commit:   bool = True,
) -> ApplyResult:
    """Применяет мульти-файл diff атомарно. См. docstring модуля.

    auto_commit=True (по умолчанию): после успешного smoke-test делает
    git add + commit изменённых файлов. Push выполняется отдельным
    cron-скриптом — мы не делаем сетевые операции внутри.
    """
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

    # 3. Бэкап-директория + сохраняем сам diff чтобы можно было разобрать
    # провалы apply (видеть что именно Мира пыталась записать).
    backup_dir = _make_backup_dir(project_root)
    logger.info(f"safe_apply: бэкап в {backup_dir}")
    try:
        with open(os.path.join(backup_dir, "_input.diff"), "w", encoding="utf-8") as f:
            f.write(diff_text)
    except Exception as e:
        logger.warning(f"safe_apply: не удалось сохранить _input.diff: {e}")

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

        # 4.5 PRINCIPLES: diff не должен удалять защитные функции (path-safety,
        # sandbox, whitelist, smoke_test, rollback). Раньше PRINCIPLES.md был
        # «честным словом» LLM — теперь проверяется кодом, иначе откат.
        ok_pr, pr_err = check_principles(project_root, [p for p, _ in applied], backup_dir)
        if not ok_pr:
            raise RuntimeError(f"PRINCIPLES нарушен: {pr_err}")

        # 5. Smoke-test
        if smoke_test_fn is not None:
            ok_smoke, smoke_err = smoke_test_fn(project_root)
            if not ok_smoke:
                raise RuntimeError(f"smoke-test упал: {smoke_err}")

        touched = [p for p, _ in applied]
        msg = f"Применено {len(applied)} файлов"

        if auto_commit and touched:
            ok_commit, commit_info = _git_commit_changes(touched, task_summary, project_root)
            if ok_commit:
                msg += f" + git commit {commit_info}"
                logger.info(f"safe_apply: коммит {commit_info}")
            else:
                logger.warning(f"safe_apply: коммит не создан ({commit_info})")
                msg += f" (без git-коммита: {commit_info})"

        return ApplyResult(
            ok            = True,
            message       = msg,
            touched_paths = touched,
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
