"""Тесты для _evolve_extract_diff и _unescape_diff.

Реальные кейсы /evolve где модель загрязняла diff JSON-escaped
кавычками. Без unescape strict-match не находит совпадений
потому что `\\"` это другой символ нежели `"`.
"""

import pytest

from agent import _evolve_extract_diff, _unescape_diff


def test_extract_diff_from_code_block():
    response = '''Вот патч:

```diff
--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-old
+new
```

Готово.'''
    diff = _evolve_extract_diff(response)
    assert diff is not None
    assert "--- a/foo.py" in diff
    assert "@@" in diff


def test_extract_no_block_but_raw_diff():
    response = """--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-old
+new"""
    diff = _evolve_extract_diff(response)
    assert diff is not None
    assert "--- a/foo.py" in diff


def test_extract_returns_none_for_chat_text():
    diff = _evolve_extract_diff("Я подумала и решила что лучше не менять код.")
    assert diff is None


def test_extract_returns_none_for_empty():
    assert _evolve_extract_diff("") is None
    assert _evolve_extract_diff(None) is None


# ----- unescape ------

def test_unescape_real_world_case():
    """Воспроизводит то что Мира реально вернула в /evolve."""
    dirty = """--- a/tools/tool_schemas.py
+++ b/tools/tool_schemas.py
@@ -384,4 +384,5 @@
                 \\"required\\": []
             }
+    {
+        \\"type\\": \\"function\\",
"""
    clean = _unescape_diff(dirty)
    assert '"required":' in clean
    assert '"type":' in clean
    assert '\\"' not in clean


def test_unescape_passthrough_when_clean():
    """Чистый diff не трогаем."""
    clean = """--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
 "x"
"""
    assert _unescape_diff(clean) == clean


def test_unescape_preserves_real_backslashes():
    """Литералы \\\\ (двойной слеш) должны остаться двойным слешем."""
    text = "path = \\\"C:\\\\\\\\Users\\\""
    out = _unescape_diff(text)
    # \" → ", \\\\ → \\ (двойной бэкслеш в исходе)
    assert '"' in out
    assert "\\\\" in out or "\\" in out  # backslash сохранён


def test_unescape_handles_literal_newlines():
    """Если \\n идёт literal-ом (модель вернула в одну строку)."""
    dirty = "line1\\nline2\\nline3"
    out = _unescape_diff(dirty)
    assert out.count("\n") >= 2
    assert "line2" in out
