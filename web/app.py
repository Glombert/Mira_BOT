"""
web/app.py — веб-интерфейс Миры.

FastAPI + WebSocket. Запускается отдельным сервисом на порту 8000.
Nginx проксирует запросы снаружи.

Аутентификация: Telegram Login Widget.
  1. Пользователь нажимает "Войти через Telegram"
  2. Telegram верифицирует личность и вызывает /auth/telegram
  3. Сервер проверяет подпись и выдаёт подписанный session token
  4. Token хранится в localStorage, передаётся в WebSocket

Сессии: tg_id → user_id "web_tg_{tg_id}", та же memory/ что у Telegram.
"""

import os
import sys
import hmac
import time
import hashlib
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import providers as _providers
_providers.init()
import memory_crypto
memory_crypto.init()
import memory_manager

from agent import (
    Agent, Profile, SYSTEM_PROMPT, TOOL_SCHEMAS, execute_tool,
    load_user_profile, save_user_profile,
    MEMORY_DIR, WORKSPACE_DIR, MEMORY_SESSIONS_DIR,
)

logger = logging.getLogger("MiraWeb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")   # например: MyMiraBot (без @)
MAX_HISTORY  = 40
STATIC_DIR   = Path(__file__).parent / "static"

app = FastAPI(title="Mira Web")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Telegram Auth
# ---------------------------------------------------------------------------

def _verify_telegram(data: dict) -> bool:
    """Проверяет подпись Telegram Login Widget."""
    received_hash = data.get("hash", "")
    check_data    = {k: v for k, v in data.items() if k != "hash"}
    check_string  = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret        = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed      = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    # Данные не старше суток
    if time.time() - int(data.get("auth_date", 0)) > 86400:
        return False
    return hmac.compare_digest(computed, received_hash)


def _make_session(tg_id: int, name: str) -> str:
    """Создаёт подписанный session token."""
    payload = f"{tg_id}:{name}:{int(time.time())}"
    sig     = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{payload}:{sig}"


def _verify_session(token: str) -> int | None:
    """Возвращает tg_id если токен валиден, иначе None."""
    try:
        *parts, sig = token.split(":")
        payload  = ":".join(parts)
        expected = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(expected, sig):
            return None
        tg_id = int(parts[0])
        return tg_id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _web_user_id(tg_id: int) -> str:
    return f"web_tg_{tg_id}"


def _session_path(user_id: str) -> str:
    return os.path.join(MEMORY_SESSIONS_DIR, f"{user_id}.json")


def _load_session(user_id: str) -> list:
    sys_prompt = _system_prompt_for(user_id)
    msgs = memory_crypto.load_json(_session_path(user_id))
    if isinstance(msgs, list):
        for m in msgs:
            if m.get("role") == "system":
                m["content"] = sys_prompt
                break
        else:
            msgs.insert(0, {"role": "system", "content": sys_prompt})
        return msgs
    return [{"role": "system", "content": sys_prompt}]


def _save_session(user_id: str, msgs: list) -> None:
    os.makedirs(MEMORY_SESSIONS_DIR, exist_ok=True)
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    trimmed  = system + the_rest[-MAX_HISTORY:]

    def _strip(m):
        c = m.get("content")
        if isinstance(c, list):
            texts = [p.get("text", "") for p in c if p.get("type") == "text"]
            return {**m, "content": " ".join(t for t in texts if t) or "[медиа]"}
        return m

    try:
        memory_crypto.save_json(_session_path(user_id), [_strip(m) for m in trimmed])
    except Exception as e:
        logger.warning(f"save_session {user_id}: {e}")


def _system_prompt_for(user_id: str) -> str:
    base      = SYSTEM_PROMPT
    summary   = memory_manager.get_summary(user_id, load_user_profile)
    templates = memory_manager.get_templates_prompt(user_id)
    if summary:
        base += f"\n\nЧто ты знаешь об этом пользователе из прошлых разговоров:\n{summary}"
    if templates:
        base += f"\n\n{templates}"
    return base


def _ensure_profile(user_id: str, tg_name: str = "") -> None:
    if load_user_profile(user_id):
        return
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    save_user_profile(user_id, {
        "id":           user_id,
        "name":         tg_name,
        "status":       "regular",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "last_seen":    datetime.now().strftime("%Y-%m-%d"),
        "sessions_count": 1,
        "about":        {},
        "preferences":  {"language": "ru"},
        "domain":       {},
    })


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/auth/telegram")
async def auth_telegram(request: Request):
    """Callback от Telegram Login Widget."""
    data = dict(request.query_params)
    if not data or not BOT_TOKEN or not _verify_telegram(data):
        return HTMLResponse("<h2>Ошибка авторизации</h2><a href='/'>Назад</a>", status_code=400)

    tg_id   = int(data["id"])
    name    = data.get("first_name", "") + (" " + data.get("last_name", "")).rstrip()
    token   = _make_session(tg_id, name.strip())
    user_id = _web_user_id(tg_id)
    _ensure_profile(user_id, name.strip())

    logger.info(f"Telegram auth: {tg_id} ({name})")

    # Передаём токен через хэш URL — он не логируется сервером
    return HTMLResponse(f"""<!DOCTYPE html><html><body><script>
localStorage.setItem('mira_session', '{token}');
window.location.href = '/';
</script></body></html>""")


@app.websocket("/ws")
async def chat(websocket: WebSocket, session: str = ""):
    await websocket.accept()

    tg_id = _verify_session(session) if session else None
    if not tg_id:
        await websocket.send_json({"type": "auth_required", "bot": BOT_USERNAME})
        await websocket.close(code=4001)
        return

    user_id  = _web_user_id(tg_id)
    _ensure_profile(user_id)
    await websocket.send_json({"type": "ready", "name": load_user_profile(user_id).get("name", "")})
    logger.info(f"WS connect: {user_id}")

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            text = data.get("content", "").strip()
            if not text:
                continue

            msgs    = _load_session(user_id)
            profile = Profile("default")
            alpha   = Agent.from_config_file("alpha", profile, user_id, _system_prompt_for(user_id))

            msgs.append({"role": "user", "content": text})
            system   = [m for m in msgs if m["role"] == "system"]
            the_rest = [m for m in msgs if m["role"] != "system"]
            msgs     = system + the_rest[-MAX_HISTORY:]

            await websocket.send_json({"type": "thinking"})

            try:
                answer = await asyncio.to_thread(alpha.run, msgs)
            except Exception as e:
                logger.error(f"alpha.run: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "content": "Что-то пошло не так. Попробуй ещё раз."})
                continue

            await websocket.send_json({"type": "message", "content": answer})
            _save_session(user_id, msgs)

            snap = list(msgs)
            def _bg():
                updated = memory_manager.maybe_summarize(user_id, snap, alpha.model_chain, load_user_profile, save_user_profile)
                if updated is not snap:
                    _save_session(user_id, updated)
                memory_manager.update_user_profile(user_id, snap, alpha.model_chain, load_user_profile, save_user_profile)
            memory_manager.run_background(_bg)

    except WebSocketDisconnect:
        logger.info(f"WS disconnect: {user_id}")
    except Exception as e:
        logger.error(f"WS error: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
