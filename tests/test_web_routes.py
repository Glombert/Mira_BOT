"""Характеризующие тесты HTTP/WS-поверхности web/app.py — авторизация и роутинг.

Фиксируют поведение ДО извлечения web/routes/* (Фаза 6 плана): неавторизованный
доступ отбивается, owner-эндпоинты закрыты, WS требует сессию. Тяжёлый agent-путь
здесь не дёргаем — проверяем только контракт доступа и маршрутизации.

TestClient создаём без `with` — чтобы не запускать lifespan/фоновые ритуалы.
"""

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_bot_token_123")
os.environ.setdefault("MIRA_ALLOW_UNSANDBOXED", "1")

import pytest
from fastapi.testclient import TestClient

import web.app as webapp


@pytest.fixture(scope="module")
def client():
    return TestClient(webapp.app)


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert {"status", "bot_alive", "web_alive"} <= set(body)


def test_upload_requires_session(client):
    r = client.post("/upload", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 401


def test_files_requires_session(client):
    assert client.get("/files/output/x.txt").status_code == 401


def test_history_requires_session(client):
    assert client.get("/history").status_code == 401


def test_owner_inbox_requires_owner(client):
    assert client.get("/m/owner_inbox").status_code == 401


def test_owner_inbox_mark_read_requires_owner(client):
    r = client.post("/m/owner_inbox/1/read", json={})
    assert r.status_code == 401


def test_auth_telegram_bad_data_returns_not_ok(client):
    r = client.get("/auth/telegram", params={"id": "1", "hash": "bad", "auth_date": "1"})
    assert r.status_code == 200
    assert r.json().get("ok") is False


def test_register_push_requires_fields(client):
    r = client.post("/m/register_push_token", json={})
    assert r.status_code in (400, 401)


def test_ws_requires_auth(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "auth_required"


def test_mobile_version_without_token(client):
    # Без GITHUB_APK_TOKEN релиз не тянется → пустой ответ (без сети)
    r = client.get("/mobile/version")
    assert r.status_code == 200
    assert set(r.json()) == {"version", "apk_url", "release_notes"}


def test_mobile_download_without_apk(client):
    # Без токена/релиза — 404, не падение
    r = client.get("/mobile/download", follow_redirects=False)
    assert r.status_code in (404, 503)


def test_auth_mobile_page_renders(client):
    r = client.get("/auth/mobile")
    assert r.status_code == 200
    assert "telegram" in r.text.lower()


def test_mobile_auth_redirect_bad_code(client):
    # Невалидный одноразовый code → 400 (страница «ссылка устарела»)
    r = client.get("/m/auth", params={"code": "nope"})
    assert r.status_code == 400

def test_auth_webapp_bad_data_returns_not_ok(client):
    r = client.post("/auth/webapp", json={"init_data": "user=x&hash=bad&auth_date=1"})
    assert r.status_code == 200
    assert r.json().get("ok") is False


def test_verify_webapp_init_data_roundtrip():
    import hashlib
    import hmac as hmac_mod
    import json as json_mod
    import time as time_mod
    from urllib.parse import urlencode

    user = {"id": 42, "first_name": "Тест"}
    pairs = {
        "auth_date": str(int(time_mod.time())),
        "query_id": "AAF",
        "user": json_mod.dumps(user, separators=(",", ":")),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac_mod.new(b"WebAppData", webapp.BOT_TOKEN.encode(), hashlib.sha256).digest()
    good_hash = hmac_mod.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    init_data = urlencode({**pairs, "hash": good_hash})
    parsed = webapp._verify_webapp_init_data(init_data)
    assert parsed and parsed["id"] == 42

    # Подделка подписи и протухший auth_date — отбиваются
    assert webapp._verify_webapp_init_data(urlencode({**pairs, "hash": "0" * 64})) is None
    stale = {**pairs, "auth_date": "1"}
    stale_cs = "\n".join(f"{k}={v}" for k, v in sorted(stale.items()))
    stale_hash = hmac_mod.new(secret, stale_cs.encode(), hashlib.sha256).hexdigest()
    assert webapp._verify_webapp_init_data(urlencode({**stale, "hash": stale_hash})) is None
