"""Тест sanitization имени файла в handle_document.

Telegram bot модуль слишком тяжёлый для импорта в тестах (тянет telegram, openai
и пр.). Проверяем эквивалентную логику, чтобы документировать ожидания: имя
без слешей, .., NUL, лимит 255 символов.
"""

import os


def _safe_doc_name(raw: str, file_id: str = "fallback") -> str:
    """Та же логика, что в telegram_bot._handle_document."""
    fname = os.path.basename((raw or f"file_{file_id}").replace("\\", "/"))
    fname = fname.replace("\x00", "")
    if not fname or fname in (".", ".."):
        fname = f"file_{file_id}"
    return fname[:255]


def test_path_components_stripped():
    assert _safe_doc_name("/etc/passwd") == "passwd"
    assert _safe_doc_name("../../secret") == "secret"
    assert _safe_doc_name("..\\..\\windows\\foo") == "foo"


def test_nul_stripped():
    assert "\x00" not in _safe_doc_name("evil\x00.txt")


def test_empty_fallback():
    assert _safe_doc_name("", "id123") == "file_id123"
    assert _safe_doc_name(None, "id123") == "file_id123"
    assert _safe_doc_name("..", "id123") == "file_id123"


def test_length_capped():
    assert len(_safe_doc_name("x" * 1000)) == 255


def test_realpath_check_blocks_escape(tmp_path):
    """Имитируем второй уровень защиты — realpath startswith."""
    user_root = tmp_path / "user"
    user_root.mkdir()
    (user_root / "inbox").mkdir()
    user_root_real = os.path.realpath(str(user_root))

    safe_name = _safe_doc_name("../evil")
    dest = os.path.realpath(os.path.join(user_root_real, "inbox", safe_name))
    # После sanitize всё должно остаться внутри user_root
    assert dest.startswith(user_root_real + os.sep)
