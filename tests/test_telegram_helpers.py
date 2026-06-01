"""Характеризующие тесты чистых хелперов telegram_bot.py (Фаза 6.3).

Фиксируют поведение ДО извлечения хендлеров (6.4). Только pure-функции,
без Telegram Update/Context и без сети.
"""

import os

os.environ.setdefault("MIRA_ALLOW_UNSANDBOXED", "1")

import pytest

import telegram_bot as tb


def test_user_id():
    assert tb._user_id(123) == "tg_123"
    assert tb._user_id(0) == "tg_0"


class TestSplitMessage:
    def test_short_text_single_part(self):
        assert tb._split_message("привет") == ["привет"]

    def test_empty(self):
        # пустая строка ≤ лимита → одна часть (пустая)
        assert tb._split_message("") == [""]

    def test_exactly_limit(self):
        s = "a" * tb.MAX_MSG_LEN
        assert tb._split_message(s) == [s]

    def test_over_limit_two_parts(self):
        s = "a" * (tb.MAX_MSG_LEN + 1)
        parts = tb._split_message(s)
        assert len(parts) == 2
        assert "".join(parts) == s
        assert all(len(p) <= tb.MAX_MSG_LEN for p in parts)

    def test_multiple_parts_preserve_content(self):
        s = "x" * (tb.MAX_MSG_LEN * 2 + 17)
        parts = tb._split_message(s)
        assert len(parts) == 3
        assert "".join(parts) == s
        assert all(len(p) <= tb.MAX_MSG_LEN for p in parts)


class TestStripMdForTg:
    def test_empty_unchanged(self):
        assert tb._strip_md_for_tg("") == ""

    def test_bold_double_star(self):
        assert tb._strip_md_for_tg("это **важно** очень") == "это важно очень"

    def test_bold_underscore(self):
        assert tb._strip_md_for_tg("__жирно__") == "жирно"

    def test_inline_code(self):
        assert tb._strip_md_for_tg("вызови `func()` тут") == "вызови func() тут"

    def test_header_stripped(self):
        assert tb._strip_md_for_tg("## Заголовок") == "Заголовок"

    def test_code_fence_removed(self):
        out = tb._strip_md_for_tg("```python\ncode here\n```")
        assert "```" not in out
        assert "code here" in out

    def test_plain_text_unchanged(self):
        s = "обычный текст без разметки"
        assert tb._strip_md_for_tg(s) == s
