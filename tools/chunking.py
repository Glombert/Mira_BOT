"""tools/chunking.py — дробление длинного ответа на 2-3 сообщения.

Зачем: живой человек в мессенджере редко пишет километровой простыней — он
бросает короткую реакцию, потом основную мысль, иногда вопрос. Этот модуль
разбивает ответ Миры по логическим границам (пустая строка), сохраняя
неделимые блоки (код-фенсы, таблицы, списки).

API: split_for_chat(text, max_parts=3) -> list[str]
"""

import re

_FENCE_RE = re.compile(r"```")
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def _has_code_fence(text: str) -> bool:
    """True если в тексте есть незакрытый/полноценный fence ```...```."""
    return text.count("```") >= 2 or _FENCE_RE.search(text) is not None


def _has_table(text: str) -> bool:
    return _TABLE_RE.search(text) is not None


def split_for_chat(text: str, max_parts: int = 3, min_chars_to_split: int = 280) -> list[str]:
    """Дробит ответ на 1-3 сообщения по \\n\\n.

    Возвращает список из 1, 2 или 3 строк. Логика:
    - Короткий ответ (< min_chars_to_split) → одно сообщение.
    - Содержит ```код-блок``` или markdown-таблицу → одно сообщение
      (дробить такое — рвать структуру).
    - 2 параграфа → 2 сообщения.
    - 3+ параграфов → 3 сообщения: первый, средние склеены, последний.

    Каждый кусок стрипнут от пробелов по краям. Пустые куски не возвращаем.
    """
    if max_parts < 1:
        max_parts = 1
    text = (text or "").strip()
    if not text:
        return []
    if max_parts == 1 or len(text) < min_chars_to_split:
        return [text]
    if _has_code_fence(text) or _has_table(text):
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        return [text]
    if len(paragraphs) == 2 or max_parts == 2:
        if max_parts == 2 and len(paragraphs) > 2:
            head = paragraphs[0]
            tail = "\n\n".join(paragraphs[1:])
            return [head, tail]
        return paragraphs

    # 3+ параграфов → берём первый, середину склеиваем, последний — отдельно
    head = paragraphs[0]
    tail = paragraphs[-1]
    middle = "\n\n".join(paragraphs[1:-1])
    out = [head]
    if middle:
        out.append(middle)
    out.append(tail)
    return out
