"""Тесты для tools/diff_tools.py — мульти-файл unified diff.

Покрывают парсер и applier. Цель — не дать /evolve в будущем тихо
испортить файлы из-за бага в diff-логике.
"""

import pytest

from tools.diff_tools import (
    Action, FileChange, Hunk,
    parse_multi_diff, apply_change, apply_hunks, extract_paths, summary,
)


# ---------------------------------------------------------------------------
# parse_multi_diff
# ---------------------------------------------------------------------------

def test_parse_single_file_modify():
    diff = """--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
 line1
-line2
+line2-modified
 line3
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 1
    c = changes[0]
    assert c.path == "foo.py"
    assert c.action == "modify"
    assert len(c.hunks) == 1
    assert c.hunks[0].old_start == 1
    assert c.hunks[0].old_count == 3


def test_parse_multiple_files():
    diff = """--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-old
+new
--- a/bar.py
+++ b/bar.py
@@ -5 +5 @@
-x
+y
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 2
    assert changes[0].path == "foo.py"
    assert changes[1].path == "bar.py"


def test_parse_create_new_file():
    diff = """--- /dev/null
+++ b/tools/new_tool.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 1
    assert changes[0].action == "create"
    assert changes[0].path == "tools/new_tool.py"


def test_parse_delete_file():
    diff = """--- a/obsolete.py
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 1
    assert changes[0].action == "delete"
    assert changes[0].path == "obsolete.py"


def test_parse_mixed_create_modify():
    diff = """--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+hello
--- a/old.py
+++ b/old.py
@@ -1 +1 @@
-x
+y
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 2
    actions = [c.action for c in changes]
    assert "create" in actions and "modify" in actions


def test_parse_strips_a_b_prefix():
    diff = """--- a/path/to/file.py
+++ b/path/to/file.py
@@ -1 +1 @@
-x
+y
"""
    changes = parse_multi_diff(diff)
    assert changes[0].path == "path/to/file.py"


def test_parse_ignores_git_metadata_prefix():
    diff = """diff --git a/foo.py b/foo.py
index abc..def 100644
--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-old
+new
"""
    changes = parse_multi_diff(diff)
    assert len(changes) == 1
    assert changes[0].path == "foo.py"


def test_parse_handles_short_hunk_header():
    """@@ -10 +10 @@ без count → одна строка"""
    diff = """--- a/x.py
+++ b/x.py
@@ -10 +10 @@
-old
+new
"""
    changes = parse_multi_diff(diff)
    h = changes[0].hunks[0]
    assert h.old_start == 10
    assert h.old_count == 1
    assert h.new_count == 1


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="пустой"):
        parse_multi_diff("")
    with pytest.raises(ValueError, match="пустой"):
        parse_multi_diff("   \n  \n")


def test_parse_no_headers_raises():
    with pytest.raises(ValueError, match="заголовка"):
        parse_multi_diff("просто текст без diff\n@@ -1 +1 @@\n-x\n+y\n")


def test_parse_orphan_old_header_raises():
    diff = """--- a/foo.py
@@ -1 +1 @@
-x
+y
"""
    with pytest.raises(ValueError, match=r"\+\+\+"):
        parse_multi_diff(diff)


def test_parse_modify_without_hunks_raises():
    diff = """--- a/foo.py
+++ b/foo.py
"""
    with pytest.raises(ValueError, match="MODIFY без хунков"):
        parse_multi_diff(diff)


# ---------------------------------------------------------------------------
# apply_hunks / apply_change
# ---------------------------------------------------------------------------

def test_apply_single_replace():
    original = "line1\nline2\nline3\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,3 +1,3 @@
 line1
-line2
+line2-new
 line3
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert result == "line1\nline2-new\nline3\n"


def test_apply_insert_line():
    original = "a\nb\nc\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -2,1 +2,2 @@
 b
+inserted
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert "inserted" in result
    assert result == "a\nb\ninserted\nc\n"


def test_apply_delete_line():
    original = "a\nb\nc\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -2,1 +1,0 @@
-b
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert result == "a\nc\n"


def test_apply_create_returns_full_content():
    diff = """--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+def hello():
+    return "world"
+
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(None, changes[0])
    assert ok
    assert "def hello()" in result
    assert "return \"world\"" in result


def test_apply_modify_missing_file_fails():
    diff = """--- a/missing.py
+++ b/missing.py
@@ -1 +1 @@
-x
+y
"""
    changes = parse_multi_diff(diff)
    ok, err = apply_change(None, changes[0])
    assert not ok
    assert "MODIFY" in err


def test_apply_delete_returns_empty():
    diff = """--- a/x.py
+++ /dev/null
@@ -1,2 +0,0 @@
-a
-b
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change("a\nb\n", changes[0])
    assert ok
    assert result == ""


def test_apply_delete_out_of_bounds():
    """Удаление того чего нет в файле — отказ (был «пределами», теперь «не нашёл»)."""
    original = "only_line\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -5,1 +5,0 @@
-something
"""
    changes = parse_multi_diff(diff)
    ok, err = apply_change(original, changes[0])
    assert not ok
    assert "не нашёл" in err or "пределами" in err


def test_apply_multiple_hunks_one_file():
    original = "line1\nline2\nline3\nline4\nline5\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,1 +1,1 @@
-line1
+LINE1
@@ -5,1 +5,1 @@
-line5
+LINE5
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert result == "LINE1\nline2\nline3\nline4\nLINE5\n"


def test_strict_rejects_content_not_in_file():
    """Хунк описывает то чего в файле вообще нет — отказ."""
    original = "line1\nline2\nline3\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,3 +1,3 @@
 NOWHERE_LINE_A
-NOWHERE_LINE_B
+new_line
 NOWHERE_LINE_C
"""
    changes = parse_multi_diff(diff)
    ok, err = apply_change(original, changes[0])
    assert not ok
    assert "не нашёл" in err or "не нашел" in err


def test_ambiguous_match_disambiguated_by_hint():
    """Контекст встречается дважды, но hint указывает на 1-е вхождение — берём его.

    Это стандартное поведение GNU patch: line number — disambiguator при
    повторяющемся контенте. Если hint совпадает с одним из мест — этого достаточно.
    """
    original = "DUP\nA\nB\nDUP\nA\nB\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,2 +1,2 @@
 DUP
-A
+REPLACED
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    # Заменилось первое A (по hint), второе A осталось
    assert result.startswith("DUP\nREPLACED")
    assert result.endswith("DUP\nA\nB\n")


def test_ambiguous_match_no_hint_fails():
    """Если hint вообще не совпадает И в файле несколько мест — отказ."""
    # hint указывает на строку 100 (вне файла), а fingerprint встречается дважды
    original = "DUP\nA\nB\nDUP\nA\nB\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -100,2 +100,2 @@
 DUP
-A
+REPLACED
"""
    changes = parse_multi_diff(diff)
    ok, err = apply_change(original, changes[0])
    assert not ok
    assert "несколько раз" in err or "не нашёл" in err


def test_fuzzy_finds_shifted_hunk():
    """Заголовок @@ -1 @@ но контекст реально на строке 10 — applier найдёт."""
    original = (
        "padding1\npadding2\npadding3\npadding4\npadding5\n"
        "padding6\npadding7\npadding8\npadding9\n"
        "target_line\nafter_target\n"
    )
    diff = """--- a/x.py
+++ b/x.py
@@ -1,2 +1,3 @@
 target_line
+inserted
 after_target
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok, f"fuzzy match должен найти target_line: {result}"
    # Между target_line и after_target вставилась inserted
    lines = result.splitlines()
    target_idx = lines.index("target_line")
    assert lines[target_idx + 1] == "inserted"
    assert lines[target_idx + 2] == "after_target"


def test_fuzzy_realistic_scenario_off_by_5():
    """Воспроизводит реальный кейс из /evolve с conclave.py — старт на 5 строк раньше."""
    original = "\n".join([
        "# header line 0",
        "import os",
        "",
        "# some constants",
        "X = 1",
        "Y = 2",
        "",
        "_AGENT_NAMES = {",
        '    "coder":     "Кодер",',
        '    "critic":    "Критик",',
        '    "scout":     "Разведчик",',
        "}",
        "",
    ]) + "\n"

    # Мира думает что _AGENT_NAMES начинается с 4 строки, а реально с 8
    diff = """--- a/x.py
+++ b/x.py
@@ -4,3 +4,4 @@
     "coder":     "Кодер",
     "critic":    "Критик",
     "scout":     "Разведчик",
+    "artist":    "Художник",
 }
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok, f"fuzzy match должен исправить промах нумерации: {result}"
    assert '"artist":    "Художник"' in result


def test_loose_match_handles_extra_internal_whitespace():
    """Реальный кейс: модель сгенерировала diff с лишним пробелом внутри строки.
    В файле «X, True», в diff'е «X,  True» (два пробела). Loose match должен найти.
    """
    original = "header\n"
    original += '    "search":  ("scout", True,  False),\n'
    original += '    "code":    ("coder", False, False),\n'
    original += "footer\n"

    diff = """--- a/x.py
+++ b/x.py
@@ -2,2 +2,3 @@
     "search":  ("scout",  True,  False),
     "code":    ("coder", False, False),
+    "image":   ("artist", True,  False),
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok, f"loose должен найти место несмотря на лишний пробел: {result}"
    assert '"image":' in result


def test_loose_match_does_not_fire_when_strict_matches():
    """Если strict нашёл, loose не должен искажать поиск."""
    original = "A\nB\nC\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -2,1 +2,2 @@
 B
+INSERTED
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert result == "A\nB\nINSERTED\nC\n"


def test_loose_does_not_fire_when_truly_nothing():
    """Контента вообще нет в файле — loose тоже не найдёт, отказ."""
    original = "A\nB\nC\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,1 +1,1 @@
-COMPLETELY_DIFFERENT_LINE
+new
"""
    changes = parse_multi_diff(diff)
    ok, err = apply_change(original, changes[0])
    assert not ok


def test_non_strict_mode_skips_fingerprint():
    """С strict=False работает по hint и не ищет fingerprint."""
    original = "line1\nline2\nline3\n"
    diff = """--- a/x.py
+++ b/x.py
@@ -1,3 +1,3 @@
 line1
-line2
+new
 line3
"""
    changes = parse_multi_diff(diff)
    ok, _ = apply_change(original, changes[0], strict=False)
    assert ok


def test_apply_handles_no_newline_marker():
    original = "a\nb\nc"  # без \n в конце
    diff = """--- a/x.py
+++ b/x.py
@@ -3,1 +3,1 @@
-c
\\ No newline at end of file
+C
\\ No newline at end of file
"""
    changes = parse_multi_diff(diff)
    ok, result = apply_change(original, changes[0])
    assert ok
    assert result.endswith("C\n") or result.endswith("C")


# ---------------------------------------------------------------------------
# extract_paths + summary
# ---------------------------------------------------------------------------

def test_extract_paths():
    changes = [
        FileChange(path="a.py", action="modify"),
        FileChange(path="b.py", action="create"),
        FileChange(path="c.py", action="delete"),
    ]
    assert extract_paths(changes) == {"a.py", "b.py", "c.py"}


def test_summary_format():
    changes = [
        FileChange(path="foo.py", action="modify"),
        FileChange(path="bar.py", action="create"),
        FileChange(path="baz.py", action="delete"),
    ]
    s = summary(changes)
    assert "foo.py" in s and "MODIFY" in s
    assert "bar.py" in s and "CREATE" in s
    assert "baz.py" in s and "DELETE" in s
