"""
web/app.py — веб-интерфейс Миры.

FastAPI + WebSocket. Запускается отдельным сервисом на порту 8000.
Nginx проксирует запросы снаружи.

Аутентификация: Telegram Login Widget.
  1. Пользователь нажимает "Войти через Telegram"
  2. Telegram верифицирует личность и вызывает /auth/telegram
  3. Сервер проверяет подпись и выдаёт подписанный session token
  4. Token хранится в localStorage, передаётся в WebSocket

Сессии: tg_id → user_id "tg_{tg_id}". История общая с Telegram и Mobile.
Старые web-сессии под "web_tg_{tg_id}" мигрируют при первой загрузке.
"""

import os
import sys
import hmac
import time
import hashlib
import asyncio
import json
import logging
import threading
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
from tools.scheduler import schedule_reminder, list_reminders, cancel_reminder, list_tasks
from tools import rate_limit
from tools.time_parse import parse_time
from tools.rituals import load_rituals, parse_importance, should_notify

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
# Next.js статический бандл клиента (см. clients/apps/web).
# Собирается командой: cd clients && npm install && npm run build:web
CLIENT_DIST  = Path(__file__).parent.parent / "clients" / "apps" / "web" / "dist"
# Legacy vanilla-JS клиент — fallback пока новый бандл не собран.
LEGACY_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mira Web")

# Next.js client static assets — отдаются по /_next/...
# (используется при output: 'export' из clients/apps/web/next.config.js).
if (CLIENT_DIST / "_next").is_dir():
    app.mount(
        "/_next",
        StaticFiles(directory=str(CLIENT_DIST / "_next")),
        name="next-static",
    )

# CORS для локальной dev-разработки клиента (apps/web на :3000).
# В проде клиент отдаётся nginx с того же домена что и API — CORS не нужен.
if os.getenv("MIRA_ALLOW_LOCAL_CORS") == "1":
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# Cache-Control для статики:
#   /_next/static/* — хешированные имена файлов (chunks/webpack-<hash>.js),
#                     immutable + 1 год — браузер не дёрнет сервер повторно.
#   /              — index.html без кеша, иначе пользователи будут видеть
#                     старый бандл после деплоя.
@app.middleware("http")
async def _cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/_next/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.endswith("/index.html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

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

app.mount("/static", StaticFiles(directory=str(LEGACY_STATIC_DIR)), name="static")


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


from web.security import (
    SESSION_SIG_LEN, SESSION_MAX_AGE,
    make_session as _ws_make, verify_session as _ws_verify,
    safe_filename as _safe_filename, resolve_under as _resolve_under,
)


def _make_session(tg_id: int, name: str) -> str:
    return _ws_make(BOT_TOKEN, tg_id, name)


def _verify_session(token: str) -> int | None:
    return _ws_verify(BOT_TOKEN, token)


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _web_user_id(tg_id: int) -> str:
    """Web и Telegram делят профиль — user_id одинаковый."""
    return f"tg_{tg_id}"


# Одноразовая миграция: пользователи, у которых до унификации копилась
# отдельная web-сессия (ключ web_<user_id>) — склеиваем её с tg-сессией
# по updated_at и удаляем legacy-запись. Флаг «уже мигрировали» не нужен:
# после успешной миграции web_<user_id> просто отсутствует в БД.
_migrated_users: set[str] = set()


def _migrate_legacy_web_session(user_id: str) -> None:
    """Сливает web_<user_id> в <user_id> и удаляет legacy-запись.

    Стратегия: чья updated_at старше → в начало, моложе → в конец.
    Дедуп смежных дублей по (role, content). После — legacy удаляется.
    Идемпотентно: повторный вызов ничего не делает (legacy уже нет).
    """
    if user_id in _migrated_users:
        return
    _migrated_users.add(user_id)
    from tools import db
    legacy_key = f"web_{user_id}"
    legacy = db.load_session(legacy_key)
    if not legacy:
        return
    current = db.load_session(user_id) or []
    legacy_ts  = db.get_session_updated_at(legacy_key)  or ""
    current_ts = db.get_session_updated_at(user_id)     or ""
    if legacy_ts <= current_ts:
        merged = legacy + current
    else:
        merged = current + legacy
    # System-prompt пересчитывается при каждом _load_session, в БД ему делать
    # нечего. Дедупим смежные дубли (могут возникнуть на стыке двух сессий).
    out: list = []
    prev: tuple | None = None
    for m in merged:
        if m.get("role") == "system":
            continue
        key = (m.get("role"), m.get("content"))
        if key != prev:
            out.append(m)
            prev = key
    db.save_session(user_id, out)
    db.delete_session(legacy_key)
    logger.info(f"migrate: web_{user_id} ({len(legacy)}) + {user_id} ({len(current)}) → {len(out)}")


def _load_session(user_id: str) -> list:
    _migrate_legacy_web_session(user_id)
    sys_prompt = _system_prompt_for(user_id)
    from tools import db
    msgs = db.load_session(user_id)
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
        from tools import db
        db.save_session(user_id, saveable)
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
# Фоновые обработчики: scheduled tasks и rituals
# ---------------------------------------------------------------------------

def _run_scheduled_task(user_id: str, prompt: str) -> str:
    """Выполняет отложенную задачу (kind='task') как симуляцию user message."""
    import providers as _prov
    from agent import Agent, Profile

    msgs = _load_session(user_id)
    is_appr = _is_approved(user_id)
    if is_appr:
        pdata = load_user_profile(user_id) or {}
        if pdata.get("status") == "owner":
            profile = Profile("dev")
        else:
            profile = Profile("default")
        agent_name = "alpha"
    else:
        profile = Profile("guest")
        agent_name = "alpha_guest"

    try:
        alpha = Agent.from_config_file(agent_name, profile, user_id, _system_prompt_for(user_id))
    except FileNotFoundError:
        return "Конфиг агента не найден."

    msgs.append({"role": "user", "content": prompt, "ts": time.time()})
    system = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    msgs = system + the_rest[-MAX_HISTORY:]
    llm_msgs = [{k: v for k, v in m.items() if k != "ts"} for m in msgs]

    try:
        answer = alpha.run(llm_msgs)
        assistant_msg = {"role": "assistant", "content": answer, "ts": time.time()}
        msgs.append(assistant_msg)
        _save_session(user_id, msgs)
        logger.info(f"_run_scheduled_task: {user_id} — ok ({len(answer)} символов)")
        return answer
    except Exception as e:
        logger.error(f"_run_scheduled_task: {user_id} — ошибка: {e}")
        return f"Ошибка: {e}"


def _run_ritual_background(ritual: dict, user_id: str) -> None:
    """Выполняет один ритуал в фоне и шлёт notify_owner если IMPORTANCE ≥ порога."""
    from agent import Agent, Profile
    from tools import db as _db
    from tools.access_tools import notify_owner as _notify

    logger.info(f"rituals: запуск '{ritual['name']}' для {user_id}")

    profile = Profile("dev")  # ритуалы всегда от владельца
    try:
        alpha = Agent.from_config_file("alpha", profile, user_id, _system_prompt_for(user_id))
    except FileNotFoundError:
        logger.error(f"rituals: alpha config не найден")
        return

    # Эфемерная сессия: ритуал не должен загрязнять основную историю.
    # Собираем system + промпт ритуала = стартовый контекст для alpha.run.
    msgs = [
        {"role": "system", "content": _system_prompt_for(user_id)},
        {"role": "user",   "content": ritual["prompt"]},
    ]

    try:
        # alpha.run() — встроенный agent-loop с TOOL_SCHEMAS.
        # Мира может вызывать read_self, list_self, web_search и др.
        answer = alpha.run(msgs)
    except Exception as e:
        logger.error(f"rituals: '{ritual['name']}' agent error: {e}")
        _db.save_ritual_run(ritual["name"], datetime.now().isoformat(), f"ERROR: {e}")
        return

    now_iso = datetime.now().isoformat()
    _db.save_ritual_run(ritual["name"], now_iso, answer[:300])

    importance = parse_importance(answer)
    threshold = ritual.get("notify_threshold", "MAJOR")
    if should_notify(importance, threshold):
        title = f"🔔 Ритуал: {ritual['name']} [{importance}]"
        body = answer[:500]
        _notify(title + "\n" + body)
        logger.info(f"rituals: '{ritual['name']}' → notified ({importance})")
    else:
        logger.info(f"rituals: '{ritual['name']}' → ok ({importance}, below {threshold})")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    # Отдаём новый Next.js клиент если собран, иначе legacy vanilla-JS.
    new_index = CLIENT_DIST / "index.html"
    if new_index.is_file():
        return FileResponse(str(new_index))
    legacy_index = LEGACY_STATIC_DIR / "index.html"
    if legacy_index.is_file():
        return FileResponse(str(legacy_index))
    raise HTTPException(status_code=404, detail="Web client not built")


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


@app.get("/history")
async def history(session: str = "", limit: int = 50):
    """Подгрузить переписку для клиента (user/assistant, без system).

    Клиент вызывает один раз после `ready` чтобы показать прошлый контекст.
    """
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    msgs = _load_session(user_id)
    limit = max(1, min(limit, 200))
    # Включаем user/assistant + системные пометки про загруженные файлы.
    # Прочие system-сообщения (главный prompt) клиенту не нужны.
    def _is_file_note(m: dict) -> bool:
        c = m.get("content", "")
        return isinstance(c, str) and c.startswith("[Пользователь загрузил файл:")
    visible = []
    for m in msgs:
        role = m.get("role")
        content = m.get("content")
        if not isinstance(content, str):
            continue
        if role in ("user", "assistant"):
            visible.append({"role": role, "content": content, "ts": m.get("ts")})
        elif role == "system" and _is_file_note(m):
            visible.append({"role": "system", "content": content, "ts": m.get("ts")})
    return {"messages": visible[-limit:]}


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

UPLOAD_MAX_BYTES = 20 * 1024 * 1024


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), session: str = ""):
    """Загружает файл в workspace/inbox пользователя."""
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)

    # Rate limit: 20 файлов / минуту (owner без лимитов)
    allowed, retry_after = rate_limit.check_and_record(user_id, "upload")
    if not allowed:
        msg = rate_limit.friendly_message("upload", retry_after)
        logger.info(f"upload rate limit: {user_id} → retry in {retry_after}s")
        raise HTTPException(status_code=429, detail=msg, headers={"Retry-After": str(retry_after)})

    user_root = os.path.join(WORKSPACE_DIR, user_id)
    inbox = os.path.join(user_root, "inbox")
    os.makedirs(inbox, exist_ok=True)

    filename = _safe_filename(file.filename or "upload")
    dest = _resolve_under(user_root, "inbox", filename)
    if dest is None:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")

    content = await file.read()
    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=rate_limit.friendly_message("size", 0),
        )
    with open(dest, "wb") as f:
        f.write(content)
    logger.info(f"upload: {user_id} → {filename} ({len(content)} bytes)")
    # Системную пометку в сессию НЕ добавляем — иначе Мира начнёт
    # анализировать файл, ещё не получив задание от пользователя.
    # Привязка к ходу делается в WS-обработчике: клиент шлёт
    # {content: "...", attachment: "filename"} — там и подкладываем
    # маркер «[Прикреплён: ...]» к тексту пользователя.
    return {"ok": True, "filename": filename, "size": len(content)}


@app.get("/files/{file_path:path}")
async def download_file(file_path: str, session: str = ""):
    """Скачивает файл из workspace пользователя (только inbox/ и output/)."""
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    user_root = os.path.join(WORKSPACE_DIR, user_id)

    parts = file_path.replace("\\", "/").split("/", 1)
    if len(parts) != 2 or parts[0] not in ("output", "inbox"):
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    full_path = _resolve_under(user_root, parts[0], parts[1])
    if full_path is None:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(full_path, filename=os.path.basename(full_path))


# Rate limit на /auth/telegram: 10 попыток в минуту с одного IP.
# In-memory, без зависимостей. На один процесс — Mira крутится в одном uvicorn,
# репликаций нет, этого достаточно. При перезапуске счётчики сбрасываются — ок.
from collections import deque
_AUTH_RATE_WINDOW   = 60.0
_AUTH_RATE_MAX_HITS = 10
_auth_rate_buckets: dict[str, deque[float]] = {}
_auth_rate_lock     = threading.Lock()


def _auth_rate_check(ip: str) -> bool:
    """True если разрешено, False — превышение."""
    now = time.time()
    with _auth_rate_lock:
        bucket = _auth_rate_buckets.setdefault(ip, deque())
        while bucket and now - bucket[0] > _AUTH_RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= _AUTH_RATE_MAX_HITS:
            return False
        bucket.append(now)
        return True


@app.get("/auth/telegram")
async def auth_telegram(request: Request):
    """Верифицирует данные Telegram Login Widget и возвращает session token."""
    client_ip = request.client.host if request.client else "?"
    if not _auth_rate_check(client_ip):
        logger.warning(f"/auth/telegram rate-limit: {client_ip}")
        raise HTTPException(status_code=429, detail="Too many auth attempts",
                            headers={"Retry-After": str(int(_AUTH_RATE_WINDOW))})

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


_AUTH_MOBILE_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Мира · Вход</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a1a; color: #e0e0f0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    min-height: 100vh; padding: 24px;
  }
  .logo {
    width: 120px; height: 120px; border-radius: 60px;
    object-fit: cover; border: 2px solid #FF8C4240;
    margin-bottom: 16px;
  }
  h1 { color: #FF8C42; font-size: 28px; font-weight: 700; margin-bottom: 4px; }
  p { color: #8888aa; font-size: 14px; margin-bottom: 32px; text-align: center; }
  #widget-container { margin-bottom: 24px; }
  .status {
    font-size: 14px; color: #aaaacc; text-align: center;
    opacity: 0; transition: opacity 0.3s;
  }
  .status.visible { opacity: 1; }
</style>
</head>
<body>
  <img src="/static/mira-avatar.png" class="logo" alt="Мира" onerror="this.style.display='none'">
  <h1>Мира</h1>
  <p>Войди через Telegram чтобы продолжить</p>
  <div id="widget-container"></div>
  <div id="status" class="status"></div>

<script>
  // Виджет рисует кнопку прямо на месте своего <script>-тега. Поэтому
  // создаём <script> динамически и вкладываем внутрь #widget-container —
  // иначе кнопка отрисуется в <head> или в конце <body>.
  (function() {
    const wrap = document.getElementById('widget-container');
    const s = document.createElement('script');
    s.src = 'https://telegram.org/js/telegram-widget.js?22';
    s.async = true;
    s.setAttribute('data-telegram-login', '{bot_username}');
    s.setAttribute('data-size', 'large');
    s.setAttribute('data-onauth', 'onTelegramAuth(user)');
    s.setAttribute('data-request-access', 'write');
    wrap.appendChild(s);
  })();

  // Telegram Login Widget callback
  function onTelegramAuth(user) {
    const status = document.getElementById('status');
    status.textContent = 'Авторизация...';
    status.classList.add('visible');

    fetch('/auth/telegram?' + new URLSearchParams(user).toString())
      .then(r => r.json())
      .then(data => {
        if (data.ok && data.session) {
          status.textContent = 'Успешно! Открываю приложение...';
          // Редирект в мобильное приложение через deep link
          setTimeout(() => {
            window.location.href = 'miramobile://auth?token=' + encodeURIComponent(data.session);
          }, 500);
        } else {
          status.textContent = 'Ошибка авторизации. Попробуй ещё раз.';
          status.style.color = '#ef4444';
        }
      })
      .catch(err => {
        status.textContent = 'Ошибка сети. Попробуй ещё раз.';
        status.style.color = '#ef4444';
      });
  }

  // Виджет вызовет onTelegramAuth(user) по data-onauth выше.
  // window-привязка нужна, потому что виджет ищет функцию в глобальной области.
  window.onTelegramAuth = onTelegramAuth;
</script>
</body>
</html>"""


@app.get("/auth/mobile")
async def auth_mobile():
    """Мобильная auth-страница с Telegram Login Widget → deep link в приложение."""
    # .replace вместо .format — в HTML много CSS-блоков {...}, которые
    # str.format() пытается интерпретировать как placeholder'ы.
    html = _AUTH_MOBILE_HTML.replace("{bot_username}", BOT_USERNAME.replace("@", ""))
    return HTMLResponse(html)


_MOBILE_REDIRECT_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Открываю Мира…</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0a0a1a; color: #e0e0f0; min-height: 100vh;
         display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; }
  h1 { color: #FF8C42; font-size: 28px; margin-bottom: 12px; }
  p { color: #8888aa; font-size: 14px; margin-bottom: 24px; text-align: center; }
  a.btn { display: inline-block; background: #FF8C42; color: #0a0a1a;
          padding: 14px 32px; border-radius: 12px; font-weight: 700;
          text-decoration: none; }
</style>
</head>
<body>
<h1>Мира</h1>
<p>Открываю приложение…<br>Если ничего не произошло — нажми кнопку.</p>
<a id="open" class="btn" href="__DEEPLINK__">Открыть Мира</a>
<script>
  setTimeout(function () { window.location.href = '__DEEPLINK__'; }, 250);
</script>
</body>
</html>"""


@app.post("/m/register_push_token")
async def register_push_token(request: Request):
    """Регистрирует FCM-токен мобильного устройства за текущим пользователем.

    Body (JSON): {"session": "<token>", "fcm_token": "<token>", "platform": "android"}
    Возвращает {"ok": true} или 401.

    Вызывается клиентом сразу после логина (когда есть и session,
    и FCM-токен от Firebase SDK). Если устройство уже регистрировалось —
    обновляется updated_at, дубликата не создаётся.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    session  = (body.get("session") or "").strip()
    fcm_tok  = (body.get("fcm_token") or "").strip()
    platform = (body.get("platform") or "android").strip().lower()
    if not session or not fcm_tok:
        raise HTTPException(status_code=400, detail="session и fcm_token обязательны")
    tg_id = _verify_session(session)
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    from tools import db
    db.save_push_token(user_id, fcm_tok, platform=platform)
    logger.info(f"push_token registered: {user_id} ({platform}, {fcm_tok[:16]}…)")
    return {"ok": True}


@app.get("/m/auth")
async def mobile_auth_redirect(token: str = ""):
    """Бот шлёт юзеру inline-кнопку с URL сюда → Telegram открывает страницу →
    мы редиректим в miramobile://auth?token=... → Android отдаёт MiraMobile.

    Зачем не сразу deeplink в кнопке: Telegram BotAPI разрешает в inline_button.url
    только http/https/tg-схемы; кастомные (miramobile://) запрещены.
    """
    if not token or len(token) > 512:
        return HTMLResponse("Неверный или пустой токен.", status_code=400)
    # КРИТИЧНО: токен идёт в URL (miramobile://auth?token=...), а формат токена —
    # "<tg_id>:<first_name>:<auth_date>:<hmac>". Если first_name содержит пробел
    # или кириллицу — Android intent-parser обрежет токен и сервер потом скажет
    # "сессия истекла". urllib.parse.quote безопасно кодирует всё, что не a-zA-Z0-9-_.
    import urllib.parse, html as _html
    encoded = urllib.parse.quote(token, safe="")
    # html-escape применяем поверх — encoded уже URL-safe, но мы вставляем его
    # одновременно в href-атрибут и в JS-литерал, для атрибута нужен escape.
    safe = _html.escape(encoded, quote=True)
    deeplink = f"miramobile://auth?token={safe}"
    body = _MOBILE_REDIRECT_HTML.replace("__DEEPLINK__", deeplink)
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


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
                    from agent import delete_user_profile
                    delete_user_profile(user_id)
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

                # --- Scheduled tasks (/task) ---
                elif cmd.startswith("task_cancel "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        t = cmd[12:].strip()
                        if not t:
                            await websocket.send_json({"type": "system", "content": "Укажи ID: task_cancel <id>"})
                        else:
                            r = cancel_reminder(user_id, t)
                            if r.get("ok"):
                                await websocket.send_json({"type": "system", "content": r["message"]})
                            else:
                                await websocket.send_json({"type": "system", "content": f"Ошибка: {r.get('error')}"})

                elif cmd == "tasks":
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        r = list_tasks(user_id)
                        tasks = r.get("tasks", [])
                        if not tasks:
                            await websocket.send_json({"type": "system", "content": "Запланированных задач нет."})
                        else:
                            lines = [f"Задачи ({len(tasks)}):"]
                            for t in tasks:
                                lines.append(f"  {t['id']} — {t['trigger_at'][:16].replace('T', ' ')} — {t['message'][:80]}")
                            await websocket.send_json({"type": "system", "content": "\n".join(lines)})

                elif cmd.startswith("task "):
                    if not _is_approved(user_id):
                        await websocket.send_json({"type": "system", "content": "Требуется одобрение."})
                    else:
                        rest = cmd[5:].strip()
                        if not rest:
                            await websocket.send_json({"type": "system", "content": "Формат: task <когда> <задача>\nПример: task завтра 8:00 проверь календарь"})
                        else:
                            from tools.time_parse import extract_time_and_rest
                            ok_parsed, trigger_or_err, prompt = extract_time_and_rest(rest)
                            if not ok_parsed:
                                await websocket.send_json({"type": "system", "content": trigger_or_err})
                            else:
                                r = schedule_reminder(user_id, trigger_or_err, prompt, kind="task")
                                if r.get("ok"):
                                    t = r["task"]
                                    await websocket.send_json({"type": "system", "content": f"Задача создана!\nID: {t['id']}\nКогда: {t['trigger_at']}\nЧто: {t['message'][:120]}"})
                                else:
                                    await websocket.send_json({"type": "system", "content": f"Ошибка: {r.get('error')}"})

                # --- Rituals ---
                elif cmd == "rituals":
                    is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
                    if not is_owner_ws:
                        await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
                    else:
                        from tools import db as _db
                        rituals = load_rituals()
                        runs = _db.load_ritual_runs()
                        if not rituals:
                            await websocket.send_json({"type": "system", "content": "Ритуалов не найдено."})
                        else:
                            lines = [f"Ритуалы ({len(rituals)}):"]
                            for r in rituals:
                                run = runs.get(r["name"], {})
                                last = run.get("last_run", "—")[:16].replace("T", " ") if run.get("last_run") else "—"
                                lines.append(f"  {r['name']} | расписание: {r['schedule']} | last: {last}")
                            await websocket.send_json({"type": "system", "content": "\n".join(lines)})

                elif cmd.startswith("ritual_run "):
                    is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
                    if not is_owner_ws:
                        await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
                    else:
                        rname = cmd[11:].strip()
                        rituals = {r["name"]: r for r in load_rituals()}
                        if rname not in rituals:
                            await websocket.send_json({"type": "system", "content": f"Ритуал '{rname}' не найден."})
                        else:
                            await websocket.send_json({"type": "system", "content": f"Запускаю ритуал '{rname}' в фоне..."})
                            threading.Thread(target=_run_ritual_background, args=(rituals[rname], user_id), daemon=True).start()

                # ---------- Owner-only команды (read-only) ----------
                # is_owner здесь = тот же критерий что в Telegram (OWNER_TELEGRAM_ID).
                # Деструктивные (/evolve, /rollback, /release, /git, /restart) НЕ
                # пробрасываются в WS — они требуют интерактивных подтверждений
                # и контекста, оставлены только в Telegram.
                elif cmd in ("stats", "users", "versions", "evolution_count", "blacklist"):
                    is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
                    if not is_owner_ws:
                        await websocket.send_json({"type": "system", "content": "Команда доступна только владельцу."})
                    elif cmd == "stats":
                        try:
                            from tools.metrics_tools import metrics_read
                            m = metrics_read(1)
                            if not m.get("ok"):
                                await websocket.send_json({"type": "system", "content": f"stats: {m.get('error', 'нет данных')}"})
                            else:
                                lines = [
                                    f"Метрики за {m.get('days')} д.",
                                    f"Вызовов: {m.get('total_calls')}",
                                    f"Токенов: {m.get('total_tokens')}",
                                    f"Оценка: ${m.get('cost_est', 0):.3f}",
                                ]
                                by_model = m.get("by_model") or {}
                                if by_model:
                                    lines.append("\nПо моделям:")
                                    for model, stat in list(by_model.items())[:10]:
                                        lines.append(f"  {model}: {stat.get('calls')} вызовов, {stat.get('tokens')} токенов")
                                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        except Exception as e:
                            await websocket.send_json({"type": "system", "content": f"stats: {e}"})
                    elif cmd == "users":
                        try:
                            from tools.access_tools import list_users
                            users = list_users()
                            icons = {"owner": "👑", "regular": "✅", "guest": "👤", "rejected": "❌", "blacklisted": "🚫", "blocked": "🚫"}
                            lines = [f"Пользователи ({len(users)}):"]
                            for u in users:
                                ico = icons.get(u.get("status"), "?")
                                lines.append(f"{ico} {u.get('name') or u.get('id')} [{u.get('status')}]")
                            await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        except Exception as e:
                            await websocket.send_json({"type": "system", "content": f"users: {e}"})
                    elif cmd == "versions":
                        try:
                            import io as _io, sys as _sys
                            from agent import list_backups
                            buf = _io.StringIO(); old = _sys.stdout
                            try:
                                _sys.stdout = buf
                                list_backups()
                            finally:
                                _sys.stdout = old
                            await websocket.send_json({"type": "system", "content": buf.getvalue() or "Резервных копий нет."})
                        except Exception as e:
                            await websocket.send_json({"type": "system", "content": f"versions: {e}"})
                    elif cmd == "evolution_count":
                        try:
                            from tools.access_tools import get_evolution_stats
                            evo = get_evolution_stats()
                            total = evo.get("total", 0)
                            success = evo.get("success", 0)
                            failed = evo.get("failed", 0)
                            rate = f"{round(success/total*100)}%" if total else "—"
                            await websocket.send_json({"type": "system", "content":
                                f"Счётчик эволюций:\nВсего: {total}\nУспешных: {success}\n"
                                f"Неуспешных: {failed}\nУспешность: {rate}"})
                        except Exception as e:
                            await websocket.send_json({"type": "system", "content": f"evolution_count: {e}"})
                    elif cmd == "blacklist":
                        try:
                            from tools.access_tools import list_users
                            users = [u for u in list_users() if u.get("status") in ("blacklisted", "blocked")]
                            if not users:
                                await websocket.send_json({"type": "system", "content": "Чёрный список пуст."})
                            else:
                                lines = [f"Чёрный список ({len(users)}):"]
                                for u in users:
                                    lines.append(f"🚫 {u.get('name') or u.get('id')} — {u.get('last_seen', '?')}")
                                await websocket.send_json({"type": "system", "content": "\n".join(lines)})
                        except Exception as e:
                            await websocket.send_json({"type": "system", "content": f"blacklist: {e}"})

                continue

            text = data.get("content", "").strip()
            # Прикреплённые файлы — поддержка массивов (attachments) и одиночного (attachment).
            # Клиент шлёт N POST'ов через /upload, потом одно WS-сообщение с массивом имён.
            attached_raw = data.get("attachments") or []
            if isinstance(attached_raw, str):
                attached_raw = [attached_raw]
            # Обратная совместимость: одиночное поле attachment
            single_attach = (data.get("attachment") or "").strip()
            if single_attach and not attached_raw:
                attached_raw = [single_attach]

            valid_files: list[str] = []
            for name in attached_raw:
                if not isinstance(name, str) or not name.strip():
                    continue
                _att_safe = _safe_filename(name.strip())
                _att_path = _resolve_under(os.path.join(WORKSPACE_DIR, user_id), "inbox", _att_safe) if _att_safe else None
                if _att_path and os.path.isfile(_att_path):
                    valid_files.append(f"workspace/inbox/{_att_safe}")

            if valid_files:
                prefix = "[Прикреплены файлы:\n  " + "\n  ".join(valid_files) + "]\n\n"
                text = prefix + text
            if not text:
                continue

            logger.info(f"WS message: {user_id} len={len(text)}")

            # Rate limit: 60 сообщ/мин. При превышении Мира отвечает
            # дружелюбным сообщением вместо обычной обработки LLM
            allowed, retry_after = rate_limit.check_and_record(user_id, "message")
            if not allowed:
                logger.info(f"message rate limit: {user_id} → retry in {retry_after}s")
                await websocket.send_json({
                    "type": "message",
                    "content": rate_limit.friendly_message("message", retry_after),
                })
                continue

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
            try:
                alpha = Agent.from_config_file(agent, profile, user_id, _system_prompt_for(user_id))
            except FileNotFoundError as e:
                logger.error(f"agent config '{agent}' не найден: {e}")
                await websocket.send_json({
                    "type": "system",
                    "content": f"Конфиг агента «{agent}» не найден на сервере. Сообщи владельцу.",
                })
                continue

            msgs.append({"role": "user", "content": text, "ts": time.time()})
            system   = [m for m in msgs if m["role"] == "system"]
            the_rest = [m for m in msgs if m["role"] != "system"]
            msgs     = system + the_rest[-MAX_HISTORY:]

            # Снимок output/ до хода — чтобы потом сравнить и автоматически
            # приложить к ответу Миры файлы, которые она создала за этот ход.
            # Это надёжнее регексов по тексту: ловим именно факт изменения
            # файлов на диске.
            _output_dir = os.path.join(WORKSPACE_DIR, user_id, "output")
            _output_before: dict[str, float] = {}
            if os.path.isdir(_output_dir):
                for _f in os.listdir(_output_dir):
                    _fp = os.path.join(_output_dir, _f)
                    if os.path.isfile(_fp) and not _f.startswith("."):
                        _output_before[_f] = os.path.getmtime(_fp)

            # Семантический поиск — augment только для LLM, не сохраняем.
            # Также: чистим лишние поля (ts) из llm_msgs — некоторые провайдеры
            # строги к схеме message.
            augment = ""
            try:
                matches = semantic_memory.search(user_id, text, top_k=5)
                augment = semantic_memory.format_for_prompt(matches)
            except Exception as e:
                logger.warning(f"semantic_memory search: {e}")
            llm_msgs = [{k: v for k, v in m.items() if k != "ts"} for m in msgs]
            if augment and llm_msgs and llm_msgs[0].get("role") == "system":
                llm_msgs[0] = {**llm_msgs[0], "content": llm_msgs[0]["content"] + "\n\n" + augment}

            await websocket.send_json({"type": "thinking"})

            # Классификация + роутинг как в CLI и Telegram
            _EXECUTOR_FOR = {"search": "scout", "code": "coder", "complex": "coder", "image": "artist"}
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

            # Снимок output/ ПОСЛЕ хода — diff с _output_before даёт список
            # файлов, созданных/обновлённых Мирой за этот ход. Прикладываем
            # к ответу как attachments — клиент рисует кнопки-чипы для скачивания.
            attachments: list[dict] = []
            if os.path.isdir(_output_dir):
                for _f in os.listdir(_output_dir):
                    _fp = os.path.join(_output_dir, _f)
                    if not os.path.isfile(_fp) or _f.startswith("."):
                        continue
                    _mtime = os.path.getmtime(_fp)
                    if _f not in _output_before or _mtime > _output_before[_f] + 0.5:
                        attachments.append({
                            "name": _f,
                            "dir":  "output",
                            "size": os.path.getsize(_fp),
                        })

            # Сохраняем ответ в постоянную историю. И Конклав-путь (alpha_msgs —
            # отдельный список), и alpha.run (llm_msgs — копия c augment) не пишут
            # в основной msgs. Без этого следующий ход видит чат без её ответов
            # и Мира «забывает» что уже отвечала.
            assistant_msg = {"role": "assistant", "content": answer, "ts": time.time()}
            if attachments:
                assistant_msg["attachments"] = attachments
            msgs.append(assistant_msg)

            ws_payload: dict = {"type": "message", "content": answer}
            if attachments:
                ws_payload["attachments"] = attachments
            await websocket.send_json(ws_payload)
            _save_session(user_id, msgs)

            # FCM push с текстом ответа. На foreground (приложение открыто, WS
            # доставил) Android не покажет дубля — onMessage сработает, но
            # notification из tray не выскочит. На background/killed —
            # пользователь увидит push, особенно ценно для долгих задач.
            try:
                from tools import fcm_tools
                fcm_tools.send_push(
                    user_id=user_id,
                    title="Mira",
                    body=answer[:240] if answer else "ответила",
                )
            except Exception as e:
                logger.warning(f"FCM push для ответа Миры: {e}")

            # Mirror в Telegram-чат: чтобы при переключении интерфейсов
            # пользователь увидел всё в одном месте. Шлём асинхронно через
            # threading, чтобы не блокировать WS-обработчик. tg_id уже из
            # верифицированной сессии — никакого подделанного chat_id.
            if BOT_TOKEN and tg_id:
                def _mirror_to_telegram(uid: int, q: str, a: str):
                    try:
                        import urllib.request, urllib.parse as _up
                        for _txt in (f"📲 {q}", a):
                            _data = _up.urlencode({"chat_id": uid, "text": _txt[:4000]}).encode()
                            urllib.request.urlopen(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                data=_data, timeout=8,
                            )
                    except Exception as e:
                        logger.warning(f"mirror_to_telegram: {e}")
                threading.Thread(target=_mirror_to_telegram, args=(tg_id, text, answer), daemon=True).start()

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
