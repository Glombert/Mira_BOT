"""Тесты для tools/chunking.py — дробление ответа на 2-3 части."""

from tools.chunking import split_for_chat


def test_short_text_not_split():
    text = "Ага, поняла. Сейчас гляну."
    assert split_for_chat(text) == [text]


def test_empty_text():
    assert split_for_chat("") == []
    assert split_for_chat("   \n  ") == []


def test_two_paragraphs_split_to_two():
    text = (
        "Слушай, разобралась в чём дело. " * 8 + "\n\n"
        + "Сейчас покажу что менять. " * 8
    )
    parts = split_for_chat(text)
    assert len(parts) == 2
    assert "Слушай" in parts[0]
    assert "покажу" in parts[1]


def test_three_paragraphs_three_chunks():
    text = "Первый параграф длинный. " * 4
    text += "\n\n" + "Второй параграф длинный. " * 4
    text += "\n\n" + "Третий параграф длинный. " * 4
    parts = split_for_chat(text)
    assert len(parts) == 3
    assert "Первый" in parts[0]
    assert "Второй" in parts[1]
    assert "Третий" in parts[2]


def test_four_paragraphs_collapse_middle():
    text = ("П1 " * 30) + "\n\n" + ("П2 " * 30) + "\n\n" + ("П3 " * 30) + "\n\n" + ("П4 " * 30)
    parts = split_for_chat(text)
    assert len(parts) == 3
    # средние склеены
    assert "П2" in parts[1] and "П3" in parts[1]
    assert "П1" in parts[0] and "П4" in parts[2]


def test_code_block_kept_whole():
    text = (
        "Вот фикс одной строкой:\n\n"
        "```python\n"
        "def foo():\n"
        "    return 42\n"
        "```\n\n"
        "Дальше просто запусти и проверь."
    )
    parts = split_for_chat(text)
    # код-блок дробить нельзя — должны вернуть одним куском
    assert len(parts) == 1
    assert "```python" in parts[0]


def test_markdown_table_kept_whole():
    text = (
        "Сравнение моделей:\n\n"
        "| Модель | Контекст | Скорость |\n"
        "|---|---|---|\n"
        "| Sonnet | 200k | быстрая |\n"
        "| Opus   | 200k | медленнее |\n\n"
        "Так что Sonnet годится."
    )
    parts = split_for_chat(text)
    assert len(parts) == 1


def test_max_parts_two():
    text = ("A " * 50) + "\n\n" + ("B " * 50) + "\n\n" + ("C " * 50)
    parts = split_for_chat(text, max_parts=2)
    assert len(parts) == 2
    assert "B" in parts[1] and "C" in parts[1]


def test_max_parts_one_returns_whole():
    text = ("A " * 50) + "\n\n" + ("B " * 50)
    parts = split_for_chat(text, max_parts=1)
    assert len(parts) == 1
    assert "A" in parts[0] and "B" in parts[0]


def test_threshold_not_split_at_two_short():
    text = "Коротко.\n\nДа."
    parts = split_for_chat(text)
    # слишком короткий — не дробим
    assert len(parts) == 1
