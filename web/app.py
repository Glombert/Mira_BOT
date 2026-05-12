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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, HTTPException
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
from tools import semantic_memory

from router   import classify
from conclave import Conclave
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

    saveable = [
        _strip(m) for m in trimmed
        if isinstance(m.get("content"), (str, list))
        and m.get("role") != "tool"
        and not m.get("tool_calls")
    ]

    try:
        memory_crypto.save_json(_session_path(user_id), saveable)
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


def _is_approved(user_id: str) -> bool:
    """Только owner и regular имеют полный доступ."""
    data = load_user_profile(user_id)
    if not data:
        return False
    return data.get("status") in ("owner", "regular")


def _ensure_profile(user_id: str, tg_name: str = "") -> bool:
    """Создаёт профиль если не существует. Возвращает True если профиль новый."""
    if load_user_profile(user_id):
        return False
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    save_user_profile(user_id, {
        "id":           user_id,
        "name":         tg_name,
        "status":       "guest",   # новые пользователи ждут одобрения
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "last_seen":    datetime.now().strftime("%Y-%m-%d"),
        "sessions_count": 1,
        "about":        {},
        "preferences":  {"language": "ru"},
        "domain":       {},
    })
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    # Проверяем heartbeat Telegram-бота (обновляется каждые 30 секунд)
    heartbeat_path = os.path.join(MEMORY_DIR, ".heartbeat")
    bot_alive = False
    try:
        if os.path.exists(heartbeat_path):
            with open(heartbeat_path) as f:
                ts = float(f.read().strip())
            bot_alive = (time.time() - ts) < 120  # свежее 2 минут
    except Exception:
        pass
    return {"status": "ok", "bot_alive": bot_alive}


@app.get("/oauth/google/callback")
async def oauth_google_callback(code: str = "", state: str = "", error: str = ""):
    """
    Принимает редирект от Google OAuth, автоматически обменивает код,
    показывает результат. Пользователю не нужно копировать код вручную.
    """
    from tools.gdrive_tools import parse_oauth_state, exchange_code

    if error:
        logger.warning(f"OAuth callback: Google вернул ошибку: {error}")
        return HTMLResponse(_OAUTH_HTML.format(
            status="❌ Ошибка",
            message=f"Google отказал в доступе: {error}",
            detail="Попробуй ещё раз: /google_login в боте.",
        ))

    user_id = parse_oauth_state(state)
    if not user_id:
        logger.warning(f"OAuth callback: невалидный state={state}")
        return HTMLResponse(_OAUTH_HTML.format(
            status="❌ Ошибка",
            message="Невалидный state-параметр.",
            detail="Попробуй заново: /google_login в боте.",
        ))

    if not code:
        return HTMLResponse(_OAUTH_HTML.format(
            status="❌ Ошибка",
            message="Нет кода авторизации.",
            detail="Попробуй заново: /google_login в боте.",
        ))

    result = exchange_code(user_id, code)

    if result.get("ok"):
        logger.info(f"OAuth callback: успешная авторизация user_id={user_id}")
        return HTMLResponse(_OAUTH_HTML.format(
            status="✅ Готово!",
            message=f"Google Drive привязан: {result.get('email', 'ok')}",
            detail="Можешь закрыть эту страницу и вернуться в Telegram.",
        ))

    logger.warning(f"OAuth callback: ошибка обмена для {user_id}: {result.get('error')}")
    return HTMLResponse(_OAUTH_HTML.format(
        status="❌ Ошибка",
        message=result.get('error', 'Неизвестная ошибка при обмене кода.'),
        detail="Попробуй ещё раз: /google_login в боте.",
    ))


_OAUTH_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mira · Google Drive</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; margin: 0; background: #0f172a; color: #e2e8f0;
  }}
  .card {{
    background: #1e293b; border-radius: 12px; padding: 40px;
    max-width: 420px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.3);
  }}
  h1 {{ font-size: 48px; margin: 0 0 16px; }}
  h2 {{ font-size: 20px; font-weight: 600; margin: 0 0 8px; }}
  p {{ font-size: 14px; color: #94a3b8; margin: 0 0 24px; }}
  .hint {{ font-size: 12px; color: #64748b; }}
</style>
</head>
<body>
<div class="card">
  <h1>{status}</h1>
  <h2>{message}</h2>
  <p>{detail}</p>
  <span class="hint">Mira · Telegram Bot</span>
</div>
</body>
</html>"""

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), session: str = ""):
    """Загружает файл в workspace/inbox пользователя."""
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    inbox = os.path.join(WORKSPACE_DIR, user_id, "inbox")
    os.makedirs(inbox, exist_ok=True)
    dest = os.path.join(inbox, file.filename or "upload")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл больше 20 МБ")
    with open(dest, "wb") as f:
        f.write(content)
    logger.info(f"upload: {user_id} → {file.filename} ({len(content)} bytes)")
    return {"ok": True, "filename": file.filename, "size": len(content)}


@app.get("/files/{file_path:path}")
async def download_file(file_path: str, session: str = ""):
    """Скачивает файл из workspace пользователя (только inbox/ и output/)."""
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    parts = file_path.replace("\\", "/").split("/", 1)
    if len(parts) != 2 or parts[0] not in ("output", "inbox"):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    full_path = os.path.join(WORKSPACE_DIR, user_id, parts[0], parts[1])
    full_path = os.path.normpath(full_path)
    if not full_path.startswith(os.path.join(WORKSPACE_DIR, user_id)):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(full_path, filename=os.path.basename(full_path))


@app.get("/auth/telegram")
async def auth_telegram(request: Request):
    """Верифицирует данные Telegram Login Widget и возвращает session token."""
    data = dict(request.query_params)
    if not data or not BOT_TOKEN or not _verify_telegram(data):
        return {"ok": False, "error": "Ошибка авторизации"}

    tg_id   = int(data["id"])
    name    = (data.get("first_name", "") + " " + data.get("last_name", "")).strip()
    token   = _make_session(tg_id, name)
    user_id = _web_user_id(tg_id)
    is_new  = _ensure_profile(user_id, name)

    if is_new:
        import threading, json as _j
        owner_tg = os.getenv("OWNER_TELEGRAM_ID", "")
        if owner_tg and BOT_TOKEN:
            msg = f"Новый пользователь через веб!\nИмя: {name}\nID: {user_id}"
            payload = {
                "chat_id": owner_tg, "text": msg,
                "reply_markup": _j.dumps({"inline_keyboard": [[
                    {"text": "Одобрить ✅", "callback_data": f"u_ap_{user_id}"},
                    {"text": "Отклонить ❌", "callback_data": f"u_rj_{user_id}"},
                ]]})
            }
            def _sn():
                try:
                    import urllib.request, urllib.parse
                    urllib.request.urlopen(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        data=urllib.parse.urlencode(payload).encode(), timeout=8)
                except Exception: pass
            threading.Thread(target=_sn, daemon=True).start()

    logger.info(f"Telegram auth: {tg_id} ({name}) new={is_new}")
    return {"ok": True, "session": token, "name": name}


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

            # Команды
            if data.get("type") == "command":
                cmd = data.get("cmd", "")
                if cmd == "clear":
                    _save_session(user_id, [{"role": "system", "content": _system_prompt_for(user_id)}])
                    await websocket.send_json({"type": "system", "content": "История очищена."})

                elif cmd == "whoami":
                    p = load_user_profile(user_id) or {}
                    about = p.get("about", {})
                    lines = [f"Имя: {p.get('name', '—')}",
                             f"Статус: {p.get('status', 'regular')}"]
                    if about.get("role"):    lines.append(f"Роль: {about['role']}")
                    if about.get("project"): lines.append(f"Проект: {about['project']}")
                    summary = p.get("conversation_summary", "")
                    if summary: lines.append(f"\nЧто Мира знает о тебе:\n{summary[:400]}")
                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})

                elif cmd == "files":
                    files = []
                    for subdir in ("inbox", "output"):
                        d = os.path.join(WORKSPACE_DIR, user_id, subdir)
                        if os.path.isdir(d):
                            for fname in sorted(os.listdir(d)):
                                fpath = os.path.join(d, fname)
                                if os.path.isfile(fpath) and not fname.startswith("."):
                                    files.append({
                                        "name": fname,
                                        "dir":  subdir,
                                        "size": os.path.getsize(fpath),
                                    })
                    await websocket.send_json({"type": "files", "files": files})

                elif cmd == "forget":
                    from agent import get_user_profile_path
                    path = get_user_profile_path(user_id)
                    if os.path.exists(path):
                        os.remove(path)
                    _save_session(user_id, [{"role": "system", "content": _system_prompt_for(user_id)}])
                    try:
                        semantic_memory.delete_user(user_id)
                    except Exception as e:
                        logger.warning(f"semantic_memory delete: {e}")
                    await websocket.send_json({"type": "system", "content": "Профиль и история сброшены."})

                continue

            text = data.get("content", "").strip()
            if not text:
                continue

            msgs    = _load_session(user_id)
            profile = Profile("guest" if not _is_approved(user_id) else "default")
            agent   = "alpha_guest" if not _is_approved(user_id) else "alpha"
            alpha   = Agent.from_config_file(agent, profile, user_id, _system_prompt_for(user_id))

            msgs.append({"role": "user", "content": text})
            system   = [m for m in msgs if m["role"] == "system"]
            the_rest = [m for m in msgs if m["role"] != "system"]
            msgs     = system + the_rest[-MAX_HISTORY:]

            # Семантический поиск — augment только для LLM, не сохраняем
            augment = ""
            try:
                matches = semantic_memory.search(user_id, text, top_k=5)
                augment = semantic_memory.format_for_prompt(matches)
            except Exception as e:
                logger.warning(f"semantic_memory search: {e}")
            llm_msgs = list(msgs)
            if augment and llm_msgs and llm_msgs[0].get("role") == "system":
                llm_msgs[0] = {**llm_msgs[0], "content": llm_msgs[0]["content"] + "\n\n" + augment}

            await websocket.send_json({"type": "thinking"})

            # Классификация + роутинг как в CLI и Telegram
            _EXECUTOR_FOR = {"search": "scout", "code": "coder", "complex": "coder"}
            task_type = classify(text, alpha.model_chain if alpha else [])

            try:
                if task_type in _EXECUTOR_FOR and alpha:
                    conclave = Conclave(
                        system_prompt=SYSTEM_PROMPT, user_id=user_id,
                        profile=profile, tool_schemas=TOOL_SCHEMAS,
                        execute_tool_fn=execute_tool,
                    )
                    executor = _EXECUTOR_FOR[task_type]
                    logger.info(f"Web Conclave: task_type={task_type}, executor={executor}")
                    raw = await asyncio.to_thread(conclave.run_with_qa, text, executor)

                    sys_with_aug = SYSTEM_PROMPT + ("\n\n" + augment if augment else "")
                    presentation = f"Специалисты выполнили задачу. Представь результат пользователю:\n\n{raw}"
                    recent = [m for m in msgs if m.get("role") != "system"][-12:]
                    alpha_msgs = [
                        {"role": "system", "content": sys_with_aug},
                        *recent,
                        {"role": "assistant", "content": "[передала специалистам]"},
                        {"role": "user", "content": presentation},
                    ]
                    answer = _providers.call(
                        alpha.model_chain, alpha_msgs, temperature=0.7
                    ).choices[0].message.content
                else:
                    answer = await asyncio.to_thread(alpha.run, llm_msgs)
            except Exception as e:
                logger.error(f"alpha.run: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "content": "Что-то пошло не так. Попробуй ещё раз."})
                continue

            await websocket.send_json({"type": "message", "content": answer})
            _save_session(user_id, msgs)

            snap = list(msgs)
            user_text  = text
            bot_answer = answer
            def _bg():
                try:
                    semantic_memory.index_message(user_id, "user", user_text)
                    if bot_answer:
                        semantic_memory.index_message(user_id, "assistant", bot_answer)
                except Exception as e:
                    logger.warning(f"semantic_memory index: {e}")
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
