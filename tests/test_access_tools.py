"""Тесты для access_tools — CRUD профилей и переходы статусов.

access_tools пишет в SQLite (memory/mira.db). Fixture isolated_cwd создаёт
изолированную БД в tmp_path для каждого теста.
"""

import json
import os
import pytest

from tools import access_tools, db

pytestmark = pytest.mark.usefixtures("isolated_cwd")


def _make_profile(user_id: str, status: str = "regular", name: str = "Test") -> None:
    db.save_user_profile(user_id, {
        "id": user_id, "name": name, "status": status,
        "created_at": "2026-01-01", "last_seen": "2026-01-01",
    })


def test_get_status_existing():
    _make_profile("tg_1", "regular")
    assert access_tools.get_status("tg_1") == "regular"


def test_get_status_missing_defaults():
    assert access_tools.get_status("tg_missing") == "regular"


def test_set_status_valid():
    _make_profile("tg_1", "guest")
    assert access_tools.set_status("tg_1", "regular") is True
    assert access_tools.get_status("tg_1") == "regular"


def test_set_status_invalid_rejected():
    _make_profile("tg_1", "guest")
    assert access_tools.set_status("tg_1", "superuser") is False
    assert access_tools.get_status("tg_1") == "guest"


def test_set_status_missing_user():
    assert access_tools.set_status("tg_nobody", "regular") is False


def test_approve_clears_guest_counters():
    db.save_user_profile("tg_g", {
        "id": "tg_g", "status": "guest", "name": "G",
        "guest_message_count": 5, "rejected_at": "2026-01-01",
        "created_at": "2026-01-01", "last_seen": "2026-01-01",
    })
    assert access_tools.approve("tg_g") is True
    data = db.load_user_profile("tg_g")
    assert data["status"] == "regular"
    assert "guest_message_count" not in data
    assert "rejected_at" not in data


def test_blacklist_then_unblacklist():
    _make_profile("tg_1", "regular")
    assert access_tools.blacklist("tg_1") is True
    assert access_tools.get_status("tg_1") == "blacklisted"
    assert access_tools.unblacklist("tg_1") is True
    assert access_tools.get_status("tg_1") == "rejected"


def test_list_users_returns_only_real_users():
    _make_profile("tg_1", "regular", "Alice")
    _make_profile("tg_2", "guest", "Bob")
    # decisions.log и evolution_counter.json не хранятся в БД и не появятся
    users = access_tools.list_users()
    ids = {u["id"] for u in users}
    assert ids == {"tg_1", "tg_2"}


def test_delete_user_removes_profile_and_workspace():
    _make_profile("tg_doomed", "regular")
    os.makedirs("workspace/tg_doomed/inbox", exist_ok=True)
    with open("workspace/tg_doomed/inbox/file.txt", "w") as f:
        f.write("data")
    assert access_tools.delete_user("tg_doomed") is True
    assert db.load_user_profile("tg_doomed") is None
    assert not os.path.isdir("workspace/tg_doomed")


def test_increment_guest_counter():
    _make_profile("tg_g", "guest")
    profile = {"guest_message_count": 0}
    count, limit = access_tools.increment_guest_counter("tg_g", profile)
    assert count == 1
    assert limit == access_tools.GUEST_LIMIT
