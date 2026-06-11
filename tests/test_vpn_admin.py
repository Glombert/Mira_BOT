"""Тесты tools/vpn_admin — owner-гейт и заведение VPN-пользователей."""

import subprocess
import types

from tools import vpn_admin as va


class _Proc:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def _owner(monkeypatch, status):
    fake_db = types.SimpleNamespace(load_user_profile=lambda uid: {"status": status})
    monkeypatch.setattr(va, "db", fake_db, raising=False)
    # va импортирует db внутри _is_owner через `from tools import db`
    import tools.db as real_db
    monkeypatch.setattr(real_db, "load_user_profile", lambda uid: {"status": status})


def test_non_owner_blocked(monkeypatch):
    _owner(monkeypatch, "regular")
    r = va.vpn_add_user("Admin", "reality", caller_id="tg_999")
    assert not r["ok"] and "владелец" in r["error"]


def test_bad_name(monkeypatch):
    _owner(monkeypatch, "owner")
    r = va.vpn_add_user("rm -rf /; ", "wireguard", caller_id="tg_1")
    assert not r["ok"] and "Имя" in r["error"]


def test_unknown_protocol(monkeypatch):
    _owner(monkeypatch, "owner")
    r = va.vpn_add_user("Admin", "openvpn", caller_id="tg_1")
    assert not r["ok"] and "протокол" in r["error"].lower()


def test_reality_alias_hiddify(monkeypatch):
    _owner(monkeypatch, "owner")
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _Proc(stdout="✓ заведён\nvless://uuid@5.42.98.236:443?type=tcp#Admin\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = va.vpn_add_user("Admin", "Hiddify", caller_id="tg_1")
    assert r["ok"] and r["protocol"] == "reality"
    assert r["link"].startswith("vless://")
    assert captured["cmd"][1].endswith("reality_add_user.sh")
    assert captured["cmd"][2] == "Admin"  # имя отдельным argv — не shell


def test_wireguard_link(monkeypatch):
    _owner(monkeypatch, "owner")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _Proc(stdout="wireguard://KEY@5.42.98.236:51820?...#Phone\n"))
    r = va.vpn_add_user("Phone", "wg", caller_id="tg_1")
    assert r["ok"] and r["protocol"] == "wireguard" and r["link"].startswith("wireguard://")


def test_script_failure(monkeypatch):
    _owner(monkeypatch, "owner")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _Proc(rc=1, stderr="пользователь уже есть"))
    r = va.vpn_add_user("Admin", "reality", caller_id="tg_1")
    assert not r["ok"] and "уже есть" in r["error"]


def test_remove_non_owner_blocked(monkeypatch):
    _owner(monkeypatch, "regular")
    r = va.vpn_remove_user("Admin", "reality", caller_id="tg_999")
    assert not r["ok"] and "владелец" in r["error"]


def test_remove_calls_correct_script(monkeypatch):
    _owner(monkeypatch, "owner")
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _Proc(stdout="✓ удалён")
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = va.vpn_remove_user("Admin", "hiddify", caller_id="tg_1")
    assert r["ok"] and r["protocol"] == "reality"
    assert captured["cmd"][1].endswith("reality_remove_user.sh")
    assert captured["cmd"][2] == "Admin"
