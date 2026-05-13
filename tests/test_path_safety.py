"""Тесты path-санитизации против path traversal."""

import os

from web.security import safe_filename, resolve_under


def test_safe_filename_strips_path():
    assert safe_filename("/etc/passwd") == "passwd"
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("a/b/c.txt") == "c.txt"
    assert safe_filename("..\\..\\windows\\system32") == "system32"


def test_safe_filename_strips_nul():
    assert "\x00" not in safe_filename("file\x00.txt")


def test_safe_filename_empty():
    assert safe_filename("") == "upload"
    assert safe_filename(None) == "upload"
    assert safe_filename("..") == "upload"
    assert safe_filename(".") == "upload"


def test_safe_filename_length():
    long = "a" * 500 + ".txt"
    assert len(safe_filename(long)) <= 255


def test_resolve_under_inside(tmp_path):
    root = str(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "doc.pdf").write_text("ok")
    resolved = resolve_under(root, "inbox", "doc.pdf")
    assert resolved is not None
    assert resolved.startswith(os.path.realpath(root))


def test_resolve_under_escape_via_dotdot(tmp_path):
    (tmp_path / "user").mkdir()
    (tmp_path / "secret").write_text("x")
    resolved = resolve_under(str(tmp_path / "user"), "..", "secret")
    assert resolved is None


def test_resolve_under_escape_via_symlink(tmp_path):
    root = tmp_path / "user"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "trap").symlink_to(outside)
    resolved = resolve_under(str(root), "trap")
    assert resolved is None


def test_resolve_under_root_itself(tmp_path):
    """Сам корень не считается 'внутри' — нельзя расценивать как файл."""
    resolved = resolve_under(str(tmp_path))
    assert resolved is None
