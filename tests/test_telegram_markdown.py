"""Telegram не рендерит markdown в plain-режиме: **жирный** виден буквально.
Модель упорно использует звёздочки несмотря на инструкцию в персоне — поэтому
снимаем разметку на границе. Тесты фиксируют поведение чтобы случайно не сломать."""

from telegram_bot import _strip_md_for_tg


def test_bold_double_star_removed():
    assert _strip_md_for_tg("**жирный**") == "жирный"


def test_bold_double_underscore_removed():
    assert _strip_md_for_tg("__bold__") == "bold"


def test_inline_code_removed():
    assert _strip_md_for_tg("используй `recall` для поиска") == "используй recall для поиска"


def test_fenced_code_block_removed():
    src = "Вот код:\n```python\nprint('hi')\n```\nГотово."
    out = _strip_md_for_tg(src)
    assert "print('hi')" in out
    assert "```" not in out
    assert "python" not in out


def test_headings_removed():
    src = "# Заголовок\n## Подзаголовок\nтекст"
    out = _strip_md_for_tg(src)
    assert "Заголовок" in out
    assert "Подзаголовок" in out
    assert "#" not in out


def test_multiline_bold_kept_as_text():
    src = "**Новые инструменты:**\nспасибо за работу"
    out = _strip_md_for_tg(src)
    assert "Новые инструменты:" in out
    assert "**" not in out


def test_single_asterisk_preserved():
    # *италик* и арифметика — не трогаем чтобы не ломать формулы и идентификаторы
    assert _strip_md_for_tg("формула: 2 * 3 = 6") == "формула: 2 * 3 = 6"


def test_single_underscore_preserved():
    assert _strip_md_for_tg("snake_case_name") == "snake_case_name"


def test_empty_input():
    assert _strip_md_for_tg("") == ""
    assert _strip_md_for_tg(None) is None
