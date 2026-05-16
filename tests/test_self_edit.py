"""Тесты для tools/self_edit.py — права на самописание и валидация контента.

Самое чувствительное место /evolve: если whitelist дырявый, Мира сможет
переписать .env или удалить пользовательские данные. Все эти тесты
страхуют именно от этого.
"""

import pytest

from tools.self_edit import (
    ALLOWED_PATTERNS, HARD_DENY_PREFIXES,
    is_path_safe, is_path_allowed, validate_content, check_all_paths,
)


# ---------------------------------------------------------------------------
# is_path_safe — формальные проверки
# ---------------------------------------------------------------------------

def test_safe_relative_path():
    ok, _ = is_path_safe("agent.py")
    assert ok


def test_unsafe_absolute_path():
    ok, why = is_path_safe("/etc/passwd")
    assert not ok
    assert "абсолют" in why


def test_unsafe_parent_traversal():
    ok, why = is_path_safe("../../etc/shadow")
    assert not ok
    assert ".." in why


def test_unsafe_embedded_parent_traversal():
    ok, why = is_path_safe("tools/../../../etc/passwd")
    assert not ok


def test_unsafe_empty_path():
    ok, why = is_path_safe("")
    assert not ok
    assert "пустой" in why


def test_unsafe_whitespace_only():
    ok, _ = is_path_safe("   ")
    assert not ok


# ---------------------------------------------------------------------------
# is_path_allowed — whitelist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "agent.py",
    "providers.py",
    "router.py",
    "telegram_bot.py",
    "web/app.py",
    "web/security.py",
    "tools/db.py",
    "tools/diff_tools.py",
    "agents/alpha.json",
    "agents/artist.json",
    "profiles/dev.json",
    "persona.json",
    "tests/test_db.py",
    "PRINCIPLES.md",
    "README.md",
])
def test_allowed_paths_pass(path):
    ok, why = is_path_allowed(path)
    assert ok, f"{path} должен быть разрешён, но: {why}"


@pytest.mark.parametrize("path", [
    ".env",
    ".env.backup",
    "memory/tg_123.json",
    "memory/sessions/foo.json",
    "memory/mira.db",
    "workspace/tg_123/inbox/file.txt",
    "logs/agent.log",
    "versions/agent_2026-05-14.py",
    ".git/HEAD",
    "credentials.json",
    "chat_history.json",
])
def test_forbidden_paths_rejected(path):
    ok, why = is_path_allowed(path)
    assert not ok, f"{path} должен быть отклонён, но прошёл"


def test_random_unlisted_path_rejected():
    """Что не в whitelist — то нельзя, default-deny."""
    ok, why = is_path_allowed("some_random_new_file.py")
    assert not ok
    assert "ALLOWED" in why or "whitelist" in why


def test_absolute_path_rejected_even_if_basename_allowed():
    ok, _ = is_path_allowed("/root/mira_agent/agent.py")
    assert not ok


def test_traversal_rejected_even_to_allowed_target():
    ok, _ = is_path_allowed("agents/../agent.py")
    assert not ok


# ---------------------------------------------------------------------------
# validate_content
# ---------------------------------------------------------------------------

def test_validate_python_ok():
    ok, _ = validate_content("foo.py", "def hello():\n    return 1\n")
    assert ok


def test_validate_python_syntax_error():
    ok, err = validate_content("foo.py", "def broken(:\n")
    assert not ok
    assert "SyntaxError" in err


def test_validate_python_imports_only():
    ok, _ = validate_content("foo.py", "import os\nimport json\n")
    assert ok


def test_validate_json_ok():
    ok, _ = validate_content("config.json", '{"a": 1, "b": [2, 3]}')
    assert ok


def test_validate_json_broken_braces():
    ok, err = validate_content("config.json", '{"a": 1, "b"')
    assert not ok
    assert "JSON" in err


def test_validate_json_extra_comma():
    ok, _ = validate_content("config.json", '{"a": 1,}')
    assert not ok


def test_validate_markdown_passes_through():
    """README.md и др. — без проверки синтаксиса."""
    ok, _ = validate_content("README.md", "# Заголовок\n\n[нерабочая(ссылка")
    assert ok


def test_validate_unknown_extension_passes():
    ok, _ = validate_content("data.csv", "a,b,c\n1,2,3")
    assert ok


# ---------------------------------------------------------------------------
# check_all_paths — пакетная проверка
# ---------------------------------------------------------------------------

def test_check_all_paths_all_allowed():
    ok, problems = check_all_paths(["agent.py", "tools/db.py", "agents/foo.json"])
    assert ok
    assert problems == []


def test_check_all_paths_some_rejected():
    ok, problems = check_all_paths([
        "agent.py",          # ok
        ".env",              # запрет
        "tools/foo.py",      # ok
        "../etc/passwd",     # запрет
    ])
    assert not ok
    assert len(problems) == 2
    assert any(".env" in p for p in problems)
    assert any("etc" in p for p in problems)


# ---------------------------------------------------------------------------
# Защита от регрессии — критичные инварианты
# ---------------------------------------------------------------------------

def test_invariant_no_pattern_allows_env():
    """Никакой паттерн в ALLOWED_PATTERNS не должен случайно разрешать .env."""
    import fnmatch
    for pattern in ALLOWED_PATTERNS:
        assert not fnmatch.fnmatch(".env", pattern), f"{pattern} разрешает .env"


def test_invariant_no_pattern_allows_memory():
    import fnmatch
    for pattern in ALLOWED_PATTERNS:
        for bad in ("memory/tg_1.json", "memory/sessions/foo.json", "memory/mira.db"):
            assert not fnmatch.fnmatch(bad, pattern), f"{pattern} разрешает {bad}"


def test_invariant_credentials_in_hard_deny():
    assert "credentials.json" in HARD_DENY_PREFIXES
