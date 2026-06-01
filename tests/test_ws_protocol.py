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


# ---------------------------------------------------------------------------
# Эквивалентность миграции (Фаза 2.4): структурные WS-payload'ы в web/app.py
# переведены с сырых dict-литералов на модели + ws_payload(). Эти тесты
# доказывают, что сериализация байт-в-байт совпадает со старым литералом —
# миграция не меняет провод, лишь добавляет контроль контракта.
# ---------------------------------------------------------------------------

def test_eq_auth_required():
    assert P.ws_payload(P.AuthRequired(bot="mira_bot")) == {
        "type": "auth_required", "bot": "mira_bot"}


def test_eq_pong():
    assert P.ws_payload(P.Pong()) == {"type": "pong"}


def test_eq_profile_saved():
    assert P.ws_payload(P.ProfileSaved()) == {"type": "profile_saved"}


def test_eq_gdrive_auth_url():
    assert P.ws_payload(P.GdriveAuthUrl(url="https://x/y")) == {
        "type": "gdrive_auth_url", "url": "https://x/y"}


def test_eq_permissions_update():
    assert P.ws_payload(P.PermissionsUpdate(gdrive_authorized=False, gdrive_email="")) == {
        "type": "permissions_update", "gdrive_authorized": False, "gdrive_email": ""}


def test_eq_files():
    files = [{"name": "a.txt", "dir": "inbox", "size": 10},
             {"name": "b.png", "dir": "output", "size": 99}]
    assert P.ws_payload(P.Files(files=[P.FileEntry(**f) for f in files])) == {
        "type": "files", "files": files}


def test_eq_users_list():
    users = [{"id": "tg_1", "name": "Аня", "status": "owner"},
             {"id": "tg_2", "name": "", "status": "guest"}]
    assert P.ws_payload(P.UsersList(users=[P.UserEntry(**u) for u in users])) == {
        "type": "users_list", "users": users}


def test_eq_ready_with_counts():
    counts = {"files": 3, "reminders_today": 1, "tasks": 0}
    got = P.ws_payload(P.Ready(
        name="Аня", is_owner=True, is_approved=True,
        gdrive_authorized=False, gdrive_email="", permissions=["chat", "files"],
        counts=P.SidebarCounts(**counts),
    ))
    assert got == {
        "type": "ready", "name": "Аня", "is_owner": True, "is_approved": True,
        "gdrive_authorized": False, "gdrive_email": "",
        "permissions": ["chat", "files"], "counts": counts,
    }


def test_eq_ready_counts_drops_none_subfields():
    # неодобренный юзер: только files. None-подполя SidebarCounts не уходят.
    got = P.ws_payload(P.Ready(
        name="", is_owner=False, is_approved=False,
        gdrive_authorized=False, gdrive_email="", permissions=["chat", "files"],
        counts=P.SidebarCounts(files=2),
    ))
    assert got["counts"] == {"files": 2}


def test_eq_profile_data_full():
    profile = {
        "id": "tg_1", "name": "Аня", "role": "owner", "status": "owner",
        "timezone": "Europe/Moscow", "telegram": "anya", "about_role": "",
        "about_project": "", "summary": "", "gdrive_linked": False,
        "gdrive_email": "", "memory_facts": 5, "conversations": 12,
        "days_together": 30, "onboarded": True, "addressing": "Аня",
        "address_form": "ты", "manner": ["тепло"], "origin": "Москва",
        "occupation": "инженер", "notes": "", "manner_options": ["тепло", "сухо"],
        "filled_by_mira": ["origin"],
    }
    got = P.ws_payload(P.ProfileDataMessage(profile=P.ProfileData(**profile)))
    assert got == {"type": "profile_data", "profile": profile}
