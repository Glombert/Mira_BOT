"""Тесты для tools/file_tools.py — attach_file tool."""

import os
import pytest
from tools.file_tools import attach_file, pop_pending_attachments


pytestmark = pytest.mark.usefixtures("isolated_cwd")


class TestAttachFile:
    def test_attach_valid_inbox_file(self):
        user_id = "tg_test_attach"
        inbox = os.path.join("workspace", user_id, "inbox")
        os.makedirs(inbox, exist_ok=True)
        path = os.path.join(inbox, "report.pdf")
        with open(path, "w") as f:
            f.write("data")
        result = attach_file(user_id, "inbox/report.pdf")
        assert result["ok"] is True
        assert result["attached"] == "report.pdf"
        pending = pop_pending_attachments(user_id)
        assert len(pending) == 1
        assert pending[0]["name"] == "report.pdf"
        assert pending[0]["dir"] == "inbox"

    def test_attach_nonexistent_file(self):
        result = attach_file("tg_test", "inbox/ghost.pdf")
        assert result["ok"] is False
        assert "не найден" in result["error"]

    def test_bad_path_no_dir(self):
        result = attach_file("tg_test", "secret_file.txt")
        assert result["ok"] is False
        assert "inbox/" in result["error"] or "output/" in result["error"]

    def test_path_traversal_blocked(self):
        result = attach_file("tg_test", "output/../../../etc/passwd")
        assert result["ok"] is False
        assert "недопустимое" in result["error"] or "не найден" in result["error"]

    def test_pop_clears(self):
        user_id = "tg_test_pop"
        inbox = os.path.join("workspace", user_id, "inbox")
        os.makedirs(inbox, exist_ok=True)
        path = os.path.join(inbox, "f.txt")
        with open(path, "w") as f:
            f.write("x")
        attach_file(user_id, "inbox/f.txt")
        first = pop_pending_attachments(user_id)
        assert len(first) == 1
        second = pop_pending_attachments(user_id)
        assert second == []
