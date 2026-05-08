"""
web/app.py — веб-интерфейс Миры.

FastAPI + WebSocket. Запускается отдельным сервисом на порту 8000.
Nginx проксирует запросы снаружи.

Аутентификация: WEB_ACCESS_TOKEN в .env.
Сессии: per-browser session_id → user_id "web_{id}", та же memory/ что у Telegram.
"""

import os
import sys
import asyncio
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Добавляем корень проекта в path чтобы импортировать Миру
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

logger  = logging.getLogger("MiraWeb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

WEB_TOKEN   = os.getenv("WEB_ACCESS_TOKEN", "")
MAX_HISTORY = 40

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mira Web")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _web_user_id(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum())[:32]
    return f"web_{safe}"


def _session_path(user_id: str) -> str:
    return os.path.join(MEMORY_SESSIONS_DIR, f"{user_id}.json")


def _load_session(user_id: str) -> list:
    sys_prompt = _system_prompt_for(user_id)
    path = _session_path(user_id)
    msgs = memory_crypto.load_json(path)
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

    def _strip_images(m: dict) -> dict:
        c = m.get("content")
        if isinstance(c, list):
            texts = [p.get("text", "") for p in c if p.get("type") == "text"]
            return {**m, "content": " ".join(t for t in texts if t).strip() or "[медиа]"}
        return m

    saveable = [_strip_images(m) for m in trimmed if m.get("content") is not None]
    try:
        memory_crypto.save_json(_session_path(user_id), saveable)
    except Exception as e:
        logger.warning(f"Не удалось сохранить сессию {user_id}: {e}")


def _system_prompt_for(user_id: str) -> str:
    base = SYSTEM_PROMPT
    summary = memory_manager.get_summary(user_id, load_user_profile)
    if summary:
        base += f"\n\nЧто ты знаешь об этом пользователе из прошлых разговоров:\n{summary}"
    templates = memory_manager.get_templates_prompt(user_id)
    if templates:
        base += f"\n\n{templates}"
    return base


def _ensure_profile(user_id: str) -> None:
    if load_user_profile(user_id):
        return
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    save_user_profile(user_id, {
        "id":           user_id,
        "name":         "",
        "status":       "regular",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "last_seen":    datetime.now().strftime("%Y-%m-%d"),
        "sessions_count": 1,
        "about":        {},
        "preferences":  {"language": "ru"},
        "domain":       {},
    })


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def chat(websocket: WebSocket, token: str = "", session_id: str = ""):
    # Проверка токена
    if WEB_TOKEN and token != WEB_TOKEN:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    # Проверка токена после accept (иначе браузер получает HTTP 403, не WS close)
    if WEB_TOKEN and token != WEB_TOKEN:
        await websocket.send_json({"type": "auth_required"})
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Генерируем session_id если не передан
    if not session_id:
        session_id = uuid.uuid4().hex

    user_id = _web_user_id(session_id)
    _ensure_profile(user_id)

    logger.info(f"WS connect: {user_id}")

    # Отправляем session_id клиенту чтобы он сохранил
    await websocket.send_json({"type": "session", "session_id": session_id})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            text = data.get("content", "").strip()
            if not text:
                continue

            # Загружаем сессию
            msgs = _load_session(user_id)
            profile = Profile("default")
            alpha = Agent.from_config_file(
                "alpha", profile, user_id, _system_prompt_for(user_id)
            )

            msgs.append({"role": "user", "content": text})
            system   = [m for m in msgs if m["role"] == "system"]
            the_rest = [m for m in msgs if m["role"] != "system"]
            msgs     = system + the_rest[-MAX_HISTORY:]

            await websocket.send_json({"type": "thinking"})

            try:
                answer = await asyncio.to_thread(alpha.run, msgs)
            except Exception as e:
                logger.error(f"Ошибка alpha.run: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "content": "Что-то пошло не так. Попробуй ещё раз."
                })
                continue

            await websocket.send_json({"type": "message", "content": answer})
            _save_session(user_id, msgs)

            # Фоновые задачи памяти
            model_chain = alpha.model_chain
            msgs_snap   = list(msgs)

            def _memory():
                updated = memory_manager.maybe_summarize(
                    user_id, msgs_snap, model_chain,
                    load_user_profile, save_user_profile,
                )
                if updated is not msgs_snap:
                    _save_session(user_id, updated)
                memory_manager.update_user_profile(
                    user_id, msgs_snap, model_chain,
                    load_user_profile, save_user_profile,
                )

            memory_manager.run_background(_memory)

    except WebSocketDisconnect:
        logger.info(f"WS disconnect: {user_id}")
    except Exception as e:
        logger.error(f"WS error: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
