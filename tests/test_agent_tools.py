"""Характеризующие тесты диспетчера инструментов (agent_tools.execute_tool)
и человекочитаемых описаний (_humanize_tool). Реестр подменяется, реальные
инструменты не вызываются.
"""

import json

import pytest

import agent_tools


def test_unknown_tool_returns_error_json():
    out = agent_tools.execute_tool("нет_такого", {}, "tg_1")
    data = json.loads(out)
    assert data["ok"] is False
    assert "Неизвестный инструмент" in data["error"]


def test_handler_exception_is_caught(monkeypatch):
    def _boom(user_id, args):
        raise RuntimeError("сломалось")
    monkeypatch.setitem(agent_tools._TOOL_REGISTRY, "boom", _boom)
    out = agent_tools.execute_tool("boom", {}, "tg_1")
    data = json.loads(out)
    assert data["ok"] is False
    assert "boom" in data["error"]


def test_success_returns_json_string(monkeypatch):
    monkeypatch.setitem(
        agent_tools._TOOL_REGISTRY, "ping",
        lambda user_id, args: {"ok": True, "echo": args.get("x")},
    )
    out = agent_tools.execute_tool("ping", {"x": 42}, "tg_1")
    assert isinstance(out, str)
    data = json.loads(out)
    assert data == {"ok": True, "echo": 42}


def test_handler_receives_user_id_and_args(monkeypatch):
    seen = {}
    def _capture(user_id, args):
        seen["user_id"] = user_id
        seen["args"] = args
        return {"ok": True}
    monkeypatch.setitem(agent_tools._TOOL_REGISTRY, "cap", _capture)
    agent_tools.execute_tool("cap", {"a": 1}, "tg_777")
    assert seen == {"user_id": "tg_777", "args": {"a": 1}}


@pytest.mark.parametrize("name,args,expected", [
    ("web_search", {"query": "котики"}, "ищет в интернете: «котики»"),
    ("read_file", {"relative_path": "inbox/x.txt"}, "читает файл inbox/x.txt"),
    ("run_python", {}, "запускает код"),
    ("совсем_новый", {}, "совсем новый"),
])
def test_humanize_tool(name, args, expected):
    assert agent_tools._humanize_tool(name, args) == expected
