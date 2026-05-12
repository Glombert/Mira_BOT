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
    notify_new_user, time_context,
)
from tools.gdrive_tools import (
    is_configured as gdrive_configured,
    is_authorized as gdrive_authorized,
    get_auth_url,
    gdrive_list, gdrive_read,
    gdrive_status,
    gcal_list, gcal_quick_add,
    gsheet_read, gsheet_create,
)
from tools.scheduler import schedule_reminder, list_reminders, cancel_reminder

logger = logging.getLogger("MiraWeb")
logger.setLevel(logging.INFO)

# Файловый лог с ротацией (как в telegram_bot.py)
from logging.handlers import TimedRotatingFileHandler
os.makedirs("logs", exist_ok=True)
_web_log_handler = TimedRotatingFileHandler(
    "logs/web.log",
    when="midnight",
    interval=1,
    backupCount=3,
    encoding="utf-8",
)
_web_log_handler.suffix = "%Y-%m-%d"
_web_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(_web_log_handler)
# Дублируем в stdout для systemd/journalctl
_stdout_handler = logging.StreamHandler()
_stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(_stdout_handler)

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")   # например: MyMiraBot (без @)
OWNER_TG_ID  = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
MAX_HISTORY  = 20
STATIC_DIR   = Path(__file__).parent / "static"

app = FastAPI(title="Mira Web")

# Web heartbeat: фоновый поток пишет метку каждые 30 секунд
_web_heartbeat_path = os.path.join(MEMORY_DIR, ".heartbeat_web")

def _start_web_heartbeat() -> None:
    import threading as _th
    import time as _time

    def _loop() -> None:
        while True:
            try:
                os.makedirs(MEMORY_DIR, exist_ok=True)
                with open(_web_heartbeat_path, "w") as f:
                    f.write(str(_time.time()))
            except Exception:
                pass
            _time.sleep(30)

    _th.Thread(target=_loop, daemon=True).start()
    logger.info("Web heartbeat запущен")

@app.on_event("startup")
async def startup():
    _start_web_heartbeat()
    logger.info("=== Mira Web запущена ===")
    # Стартовое уведомление владельцу
    try:
        from tools.access_tools import notify_owner
        notify_owner("Web-интерфейс Миры запущен")
    except Exception as e:
        logger.warning(f"Не удалось отправить стартовое уведомление: {e}")

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
    """Web и Telegram делят профиль — user_id одинаковый."""
    return f"tg_{tg_id}"


def _web_web_session_path(user_id: str) -> str:
    """Web-сессия отдельная от Telegram: префикс web_."""
    return os.path.join(MEMORY_SESSIONS_DIR, f"web_{user_id}.json")


def _load_session(user_id: str) -> list:
    sys_prompt = _system_prompt_for(user_id)
    msgs = memory_crypto.load_json(_web_session_path(user_id))
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
        memory_crypto.save_json(_web_session_path(user_id), saveable)
    except Exception as e:
        logger.warning(f"save_session {user_id}: {e}")


def _system_prompt_for(user_id: str) -> str:
    base      = SYSTEM_PROMPT + f"\n\n{time_context()}"
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
    # Определяем статус: владелец → owner, остальные → guest
    raw_uid = user_id.replace("tg_", "")
    is_owner = OWNER_TG_ID and raw_uid.isdigit() and int(raw_uid) == OWNER_TG_ID
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for sub in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, user_id, sub), exist_ok=True)
    save_user_profile(user_id, {
        "id":           user_id,
        "name":         tg_name,
        "status":       "owner" if is_owner else "guest",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "last_seen":    datetime.now().strftime("%Y-%m-%d"),
        "sessions_count": 1,
        "guest_message_count": 0,
        "about":        {},
        "preferences":  {"language": "ru"},
        "domain":       {},
    })
    if not is_owner:
        notify_new_user(user_id, tg_name, "web")
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


def _check_heartbeat(filename: str) -> bool:
    """Проверяет свежесть heartbeat-файла (до 120 сек)."""
    path = os.path.join(MEMORY_DIR, filename)
    try:
        if os.path.exists(path):
            with open(path) as f:
                ts = float(f.read().strip())
            return (time.time() - ts) < 120
    except Exception:
        pass
    return False


@app.get("/health")
async def health():
    bot_alive = _check_heartbeat(".heartbeat")
    web_alive = _check_heartbeat(".heartbeat_web")
    return {
        "status": "ok",
        "bot_alive": bot_alive,
        "web_alive": web_alive,
    }


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

    logger.info(f"Telegram auth: {tg_id} ({name}) new={is_new}")
    return {"ok": True, "session": token, "name": name, "is_new": is_new}


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
                logger.info(f"WS command: {user_id} → {cmd}")
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
                    if _is_approved(user_id):
                        gd = gdrive_status(user_id)
                        if gd.get("authorized"):
                            lines.append(f"Google Drive: {gd.get('email', 'привязан')}")
                        elif gdrive_configured():
                            lines.append("Google Drive: не привязан")
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

                # --- Google Drive ---
                elif cmd == "gdrive_login":
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Google Drive доступен только одобренным пользователям."})
                    elif not gdrive_configured():
                        await websocket.send_json({"type": "system", "content": "Google Drive не настроен на сервере."})
                    elif gdrive_authorized(user_id):
                        gd = gdrive_status(user_id)
                        await websocket.send_json({"type": "system", "content": f"Google Drive уже привязан: {gd.get('email', 'ok')}\n/gdrive — список файлов."})
                    else:
                        url = get_auth_url(state=user_id)
                        if url:
                            await websocket.send_json({"type": "gdrive_auth_url", "url": url})
                        else:
                            await websocket.send_json({"type": "system", "content": "Не удалось создать ссылку для авторизации."})

                elif cmd == "gdrive_status":
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    elif not gdrive_authorized(user_id):
                        await websocket.send_json({"type": "system", "content": "Google Drive не привязан. Нажми «Привязать Drive» чтобы начать."})
                    else:
                        gd = gdrive_status(user_id)
                        await websocket.send_json({"type": "system", "content": f"Google Drive: {gd.get('email', 'привязан')}"})

                elif cmd.startswith("gdrive_list"):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    elif not gdrive_authorized(user_id):
                        await websocket.send_json({"type": "system", "content": "Сначала привяжи Google Drive."})
                    else:
                        folder = cmd[11:].strip() or "root"
                        result = gdrive_list(user_id, folder)
                        if result.get("ok"):
                            files = result.get("files", [])
                            if not files:
                                await websocket.send_json({"type": "system", "content": f"Папка пуста: {folder}"})
                            else:
                                lines = [f"Google Drive · {folder} ({len(files)})"]
                                for f in files[:20]:
                                    icon = "📁" if f["type"] == "folder" else "📄"
                                    size = f" · {f['size']}" if f.get("size") else ""
                                    lines.append(f"{icon} {f['name']}{size}")
                                    lines.append(f"  id: {f['id']}")
                                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        else:
                            await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                elif cmd.startswith("gdrive_get "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    elif not gdrive_authorized(user_id):
                        await websocket.send_json({"type": "system", "content": "Сначала привяжи Google Drive."})
                    else:
                        file_id = cmd[10:].strip()
                        if not file_id:
                            await websocket.send_json({"type": "system", "content": "Укажи ID файла: gdrive_get <id>"})
                        else:
                            result = gdrive_read(user_id, file_id)
                            if result.get("ok"):
                                fname = result.get("file", "file")
                                await websocket.send_json({"type": "system", "content": f"Файл скачан в output/: {fname} ({result.get('size', 0)} bytes)"})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                # --- Google Calendar ---
                elif cmd == "gcal" or cmd.startswith("gcal "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        parts = cmd.split()
                        n = 10
                        if len(parts) > 1:
                            try: n = max(1, min(int(parts[1]), 50))
                            except ValueError: pass
                        result = gcal_list(user_id, max_results=n)
                        if result.get("ok"):
                            events = result.get("events", [])
                            if not events:
                                await websocket.send_json({"type": "system", "content": "Календарь пуст."})
                            else:
                                lines = [f"Ближайшие события ({len(events)})"]
                                for e in events:
                                    start = e.get("start", "")[:16].replace("T", " ")
                                    lines.append(f"  {start} — {e.get('summary', '')}")
                                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        else:
                            await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                elif cmd.startswith("gcal_create "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        text = cmd[12:].strip()
                        if not text:
                            await websocket.send_json({"type": "system", "content": "Напиши: gcal_create Встреча с Колей завтра в 15:00"})
                        else:
                            result = gcal_quick_add(user_id, text)
                            if result.get("ok"):
                                await websocket.send_json({"type": "system", "content": f"Событие создано: {result.get('summary')}"})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                # --- Google Sheets ---
                elif cmd.startswith("gsheet "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        args = cmd[7:].strip().split()
                        if not args:
                            await websocket.send_json({"type": "system", "content": "Укажи ID таблицы: gsheet <id> [диапазон]"})
                        else:
                            sid, rng = args[0], args[1] if len(args) > 1 else "A1:Z100"
                            result = gsheet_read(user_id, sid, rng)
                            if result.get("ok"):
                                values = result.get("values", [])
                                if not values:
                                    await websocket.send_json({"type": "system", "content": "Таблица пуста."})
                                else:
                                    lines = [f"Таблица ({result.get('rows', 0)} строк)"]
                                    for row in values[:20]:
                                        lines.append(" | ".join(str(c)[:40] for c in row))
                                    await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                elif cmd.startswith("gsheet_create "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        title = cmd[14:].strip() or "Новая таблица"
                        result = gsheet_create(user_id, title)
                        if result.get("ok"):
                            await websocket.send_json({"type": "system", "content": f"Таблица создана: {result.get('title')}\n{result.get('url')}"})
                        else:
                            await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                # --- Reminders ---
                elif cmd.startswith("remind "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        args = cmd[7:].strip().split(maxsplit=1)
                        if len(args) < 2:
                            await websocket.send_json({"type": "system", "content": "Формат: remind <ISO-дата> <текст>\nПример: remind 2026-05-13T05:10 Пора на работу!"})
                        else:
                            trigger_at = args[0]
                            if "T" not in trigger_at and len(trigger_at) == 10:
                                trigger_at += "T09:00:00"
                            result = schedule_reminder(user_id, trigger_at, args[1])
                            if result.get("ok"):
                                t = result["task"]
                                await websocket.send_json({"type": "system", "content": f"Напоминание создано!\nID: {t['id']}\nКогда: {t['trigger_at']}\nТекст: {t['message']}"})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                elif cmd == "reminders":
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        result = list_reminders(user_id)
                        if result.get("ok"):
                            reminders = result.get("reminders", [])
                            if not reminders:
                                await websocket.send_json({"type": "system", "content": "Активных напоминаний нет."})
                            else:
                                lines = [f"Напоминания ({len(reminders)})"]
                                for r in reminders:
                                    lines.append(f"  {r['id']} — {r['trigger_at'][:16].replace('T', ' ')} — {r['message'][:60]}")
                                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        else:
                            await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                elif cmd.startswith("remind_cancel "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        task_id = cmd[14:].strip()
                        if not task_id:
                            await websocket.send_json({"type": "system", "content": "Укажи ID: remind_cancel <id>"})
                        else:
                            result = cancel_reminder(user_id, task_id)
                            if result.get("ok"):
                                await websocket.send_json({"type": "system", "content": result["message"]})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {result.get('error')}"})

                continue

            text = data.get("content", "").strip()
            if not text:
                continue

            logger.info(f"WS message: {user_id} len={len(text)}")

            # Гостевой лимит сообщений
            pdata = load_user_profile(user_id)
            if pdata and pdata.get("status") == "guest":
                count = pdata.get("guest_message_count", 0) + 1
                pdata["guest_message_count"] = count
                save_user_profile(user_id, pdata)
                if count > 10:
                    logger.info(f"Guest limit exceeded: {user_id}")
                    await websocket.send_json({"type": "system", "content": "Лимит сообщений исчерпан. Ожидай одобрения."})
                    continue
                elif count >= 8:
                    await websocket.send_json({"type": "system", "content": f"(осталось {10 - count} сообщений из 10)"})

            # Проверка статуса: blocked/rejected
            if pdata and pdata.get("status") == "blocked":
                logger.warning(f"Blocked user attempted message: {user_id}")
                await websocket.send_json({"type": "system", "content": "Доступ закрыт."})
                continue
            if pdata and pdata.get("status") == "rejected":
                logger.info(f"Rejected user attempted message: {user_id}")
                await websocket.send_json({"type": "system", "content": "Твой запрос на доступ был отклонён."})
                continue

            msgs    = _load_session(user_id)
            # Профиль: owner → dev, одобрен → default, гость → guest
            if _is_approved(user_id):
                pdata2 = load_user_profile(user_id) or {}
                if pdata2.get("status") == "owner":
                    profile = Profile("dev")
                else:
                    profile = Profile("default")
                agent = "alpha"
            else:
                profile = Profile("guest")
                agent = "alpha_guest"
            alpha = Agent.from_config_file(agent, profile, user_id, _system_prompt_for(user_id))

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
        logger.error(f"WS error {user_id}: {e}", exc_info=True)
        try:
            from tools.access_tools import notify_owner
            notify_owner(f"WebSocket error: {e}"[:300])
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
