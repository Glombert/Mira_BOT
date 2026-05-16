"""tools/diff_tools.py — парсер и applier мульти-файл unified diff.

Поддерживает три действия:
    modify  → '--- a/path' + '+++ b/path' + хунки '@@ -... +... @@'
    create  → '--- /dev/null' + '+++ b/path' + хунки (только +лines)
    delete  → '--- a/path' + '+++ /dev/null'

Стиль diff'а — стандартный `diff -u`. Опциональный 'diff --git ...' префикс
игнорируется (просто проскальзывает мимо до первого `---`).

Этот модуль НЕ пишет на диск — только разбирает и считает новый контент.
Запись и rollback — уровнем выше, в safe-apply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Action = Literal["create", "modify", "delete"]


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines:     list[str]  # с префиксом ' ', '-', '+' или '\\'


@dataclass
class FileChange:
    path:   str
    action: Action
    hunks:  list[Hunk] = field(default_factory=list)


_HEADER_OLD = re.compile(r"^---\s+(.+?)\s*$", re.MULTILINE)
_HEADER_NEW = re.compile(r"^\+\+\+\s+(.+?)\s*$", re.MULTILINE)
_HUNK       = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
    re.MULTILINE,
)


def _strip_diff_prefix(path: str) -> str:
    """'a/foo.py' → 'foo.py', '/dev/null' → '/dev/null'.

    Также срезает табы с метаданными времени модификации если git их добавил.
    """
    path = path.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return path
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_multi_diff(diff_text: str) -> list[FileChange]:
    """Разбирает мульти-файл diff. ValueError при кривом формате."""
    if not diff_text or not diff_text.strip():
        raise ValueError("Diff пустой")

    olds = list(_HEADER_OLD.finditer(diff_text))
    if not olds:
        raise ValueError("Нет ни одного заголовка `--- ` в diff")

    changes: list[FileChange] = []
    for i, old_m in enumerate(olds):
        section_start = old_m.start()
        section_end   = olds[i + 1].start() if i + 1 < len(olds) else len(diff_text)
        section       = diff_text[section_start:section_end]

        new_m = _HEADER_NEW.search(section, old_m.end() - section_start)
        if not new_m:
            raise ValueError(f"Секция {i + 1}: нет `+++` после `---`")

        old_path = _strip_diff_prefix(old_m.group(1))
        new_path = _strip_diff_prefix(new_m.group(1))

        if old_path == "/dev/null":
            action, path = "create", new_path
        elif new_path == "/dev/null":
            action, path = "delete", old_path
        else:
            action, path = "modify", new_path

        if not path or path == "/dev/null":
            raise ValueError(f"Секция {i + 1}: не удалось определить путь файла")

        hunks: list[Hunk] = []
        hunks_text = section[new_m.end():]
        hunk_matches = list(_HUNK.finditer(hunks_text))
        for j, hm in enumerate(hunk_matches):
            content_start = hunks_text.index("\n", hm.start()) + 1
            content_end   = (
                hunk_matches[j + 1].start()
                if j + 1 < len(hunk_matches)
                else len(hunks_text)
            )
            hunks.append(Hunk(
                old_start = int(hm.group(1)),
                old_count = int(hm.group(2) or 1),
                new_start = int(hm.group(3)),
                new_count = int(hm.group(4) or 1),
                lines     = hunks_text[content_start:content_end].splitlines(keepends=True),
            ))

        if action == "modify" and not hunks:
            raise ValueError(f"{path}: MODIFY без хунков")

        changes.append(FileChange(path=path, action=action, hunks=hunks))

    return changes


def apply_hunks(original: str, hunks: list[Hunk]) -> tuple[bool, str]:
    """Применяет список хунков к тексту. (ok, new_content_or_error).

    Простая реализация без strict context match — полагаемся на ast.parse /
    json.loads / smoke-test на следующем уровне чтобы поймать косяк и откатить.
    """
    result = list(original.splitlines(keepends=True))
    offset = 0

    for h_idx, h in enumerate(hunks):
        i = h.old_start - 1 + offset
        if i < 0:
            return False, f"Hunk #{h_idx + 1}: некорректный old_start={h.old_start}"

        for line in h.lines:
            if not line or line.startswith("\\"):
                # '\ No newline at end of file' — пропускаем
                continue
            ch   = line[0]
            body = line[1:]
            if body and not body.endswith("\n"):
                body += "\n"

            if ch == "+":
                result.insert(i, body)
                i += 1
                offset += 1
            elif ch == "-":
                if i >= len(result):
                    return False, (
                        f"Hunk #{h_idx + 1}: попытка удалить строку {i + 1} "
                        f"за пределами файла ({len(result)} строк)"
                    )
                result.pop(i)
                offset -= 1
            elif ch == " ":
                i += 1
            else:
                # Неизвестный префикс — игнорируем (бывают пустые строки в diff)
                pass

    return True, "".join(result)


def apply_change(existing_content: str | None, change: FileChange) -> tuple[bool, str]:
    """Применяет один FileChange. (ok, new_content_or_error).

    create — собирает контент из + строк (existing игнорируется)
    modify — применяет хунки к existing
    delete — возвращает пустую строку (физическое удаление на applier)
    """
    if change.action == "create":
        lines: list[str] = []
        for h in change.hunks:
            for line in h.lines:
                if not line or line.startswith("\\"):
                    continue
                if line.startswith("+"):
                    body = line[1:]
                    if body and not body.endswith("\n"):
                        body += "\n"
                    lines.append(body)
        return True, "".join(lines)

    if change.action == "delete":
        return True, ""

    if existing_content is None:
        return False, f"{change.path}: MODIFY для несуществующего файла"
    return apply_hunks(existing_content, change.hunks)


def extract_paths(changes: list[FileChange]) -> set[str]:
    """Какие файлы будут затронуты."""
    return {c.path for c in changes}


def summary(changes: list[FileChange]) -> str:
    """Краткая сводка для превью пользователю."""
    parts = []
    for c in changes:
        icon = {"create": "➕", "modify": "✏️", "delete": "❌"}.get(c.action, "?")
        parts.append(f"{icon} {c.action.upper():6} {c.path}")
    return "\n".join(parts)
