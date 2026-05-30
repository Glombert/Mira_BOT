"""Парити-тесты WS-контракта: Python (web/ws_protocol.py) ⟷ TS
(clients/packages/shared/src/types/index.ts).

Цель — убить тихий дрейф: если на сервере добавили/убрали тип сообщения, а в TS
забыли (или наоборот) — этот тест падает и заставляет синхронизировать.
"""

import re
from pathlib import Path

import pytest

from web import ws_protocol as P

ROOT = Path(__file__).resolve().parent.parent
TS_TYPES = ROOT / "clients" / "packages" / "shared" / "src" / "types" / "index.ts"


def _ts_union_literals(name: str) -> set[str]:
    """Достаёт литералы `type: '...'` из TS-объединения `export type <name> = ...`.

    Блок берём до следующего `export` (или конца файла), потому что внутри
    вариантов union есть свои `;` (например `{ type: 'command'; cmd: string }`).
    """
    src = TS_TYPES.read_text(encoding="utf-8")
    m = re.search(rf"export type {name}\s*=(.*?)(?:\nexport |\Z)", src, re.S)
    assert m, f"в TS не найден union {name}"
    return set(re.findall(r"type:\s*'([a-z_]+)'", m.group(1)))


def test_server_message_types_match_ts():
    ts = _ts_union_literals("ServerMessage")
    py = set(P.SERVER_MESSAGE_TYPES)
    assert py == ts, (
        f"ServerMessage рассинхронизирован.\n"
        f"только в Python: {py - ts}\n"
        f"только в TS:     {ts - py}"
    )


def test_client_message_typed_match_ts():
    # В TS ClientMessage есть ещё бестиповое чат-сообщение (без `type`) —
    # оно не имеет литерала и в сравнение по type не попадает.
    ts = _ts_union_literals("ClientMessage")
    py = set(P.CLIENT_MESSAGE_TYPES)
    assert py == ts, (
        f"ClientMessage (типизированные) рассинхронизированы.\n"
        f"только в Python: {py - ts}\n"
        f"только в TS:     {ts - py}"
    )


def test_every_server_model_has_unique_type_default():
    types = [P._type_literal(m) for m in P.SERVER_MESSAGES]
    assert len(types) == len(set(types)), "дублирующиеся type среди серверных моделей"
    assert all(isinstance(t, str) and t for t in types)


def test_ws_payload_excludes_none_and_keeps_type():
    payload = P.ws_payload(P.Thought(content="привет"))
    assert payload == {"type": "thought", "content": "привет"}
    # необязательные None-поля не уходят на провод
    payload2 = P.ws_payload(P.Message(content="x"))
    assert payload2 == {"type": "message", "content": "x"}
    assert "attachments" not in payload2 and "cards" not in payload2


def test_ws_payload_nested_models_serialized():
    msg = P.Files(files=[P.FileEntry(name="a.txt", dir="inbox", size=10)])
    payload = P.ws_payload(msg)
    assert payload == {"type": "files", "files": [{"name": "a.txt", "dir": "inbox", "size": 10}]}


def test_chat_message_is_typeless():
    assert "type" not in P.ChatMessage.model_fields
    payload = P.ws_payload(P.ChatMessage(content="hi", mode="tech"))
    assert payload == {"content": "hi", "mode": "tech"}


@pytest.mark.parametrize("model_cls,expected_type", [
    (P.Ready, "ready"),
    (P.AuthRequired, "auth_required"),
    (P.Pong, "pong"),
    (P.ProfileSaved, "profile_saved"),
])
def test_type_defaults(model_cls, expected_type):
    assert P._type_literal(model_cls) == expected_type
