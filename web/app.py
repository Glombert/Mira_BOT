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
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from tools.env_guard import check_env_permissions
check_env_permissions()

from core import providers as _providers
_providers.init()
from core import memory_crypto
memory_crypto.init()
from core import memory_manager
from tools import semantic_memory

from agent import (
    Agent, Profile, load_user_profile, save_user_profile,
    MEMORY_DIR, WORKSPACE_DIR,
)
from tools.gdrive_tools import (
    is_authorized as gdrive_authorized,
    gdrive_status,
)
from tools import rate_limit

logger = logging.getLogger("MiraWeb")
logger.setLevel(logging.INFO)

# Файловый лог с ротацией (как в telegram_bot.py)
from logging.handlers import TimedRotatingFileHandler
from tools.paths import at_root

os.makedirs(at_root("logs"), exist_ok=True)
_web_log_handler = TimedRotatingFileHandler(
    at_root("logs", "web.log"),
    when="midnight",
    interval=1,
    backupCount=14,  # 2 недели — чтобы биweekly-ритуал log_audit видел весь период
    encoding="utf-8",
)
_web_log_handler.suffix = "%Y-%m-%d"
_web_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(_web_log_handler)
# Дублируем в stdout для systemd/journalctl
_stdout_handler = logging.StreamHandler()
_stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(_stdout_handler)
# Redaction filter — маскировка секретов в логах (ASVS V7.1)
from tools.redaction_filter import install as _install_redact
_install_redact()
from tools import observability as _observability
_observability.init("web")

from web.deps import (
    BOT_TOKEN, BOT_USERNAME, OWNER_TG_ID,
    make_session as _make_session,
    verify_session as _verify_session,
    web_user_id as _web_user_id,
)
from web.sessions import (
    MAX_HISTORY, _load_session, _save_session, _system_prompt_for,
    _is_approved, _ensure_profile,
    _changelog_augment, _incoming_augment,
    _mark_changelog_seen, _mark_incoming_seen,
)
from web.panels import MEMORY_CARD_MAX_DISTANCE, _compute_sidebar_counts, _build_cards
from web.ws_commands import _ws_profile_save, _ws_command
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


# Global security headers middleware (ASVS V13, OWASP)
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    return response


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
    safe_filename as _safe_filename, resolve_under as _resolve_under,
)
# Контракт WS — единый источник истины (web/ws_protocol.py). Импортируем
# ws_payload под алиасом _wsp: в chat() есть локальная переменная, а имя
# ws_payload там заняли бы под dict (UnboundLocalError на уровне функции).
from web.ws_protocol import (
    Ready, AuthRequired,
    Pong, SidebarCounts,
    ws_payload as _wsp,
)


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

# Одноразовая миграция: пользователи, у которых до унификации копилась
# отдельная web-сессия (ключ web_<user_id>) — склеиваем её с tg-сессией
# по updated_at и удаляем legacy-запись. Флаг «уже мигрировали» не нужен:
# после успешной миграции web_<user_id> просто отсутствует в БД.








# Манеры Миры (анкета). Это модуляция тона, НЕ подмена характера из SYSTEM_PROMPT.


















# ---------------------------------------------------------------------------
# Общий helper: запускает alpha.run() для любого источника
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Фоновые обработчики: scheduled tasks и rituals
# ---------------------------------------------------------------------------
# Счётчики для сайдбара (Aurora UI design)
# ---------------------------------------------------------------------------



# Карточка «Из памяти» — показываем РЕДКО, только на «особенные» совпадения.
# В обычной беседе любое сообщение тянет похожее (distance<0.5), поэтому порог
# жёсткий + кулдаун на стороне сессии (см. _msgs_since_card). Оба настраиваются.
MEMORY_CARD_COOLDOWN = int(os.getenv("MEMORY_CARD_COOLDOWN", "6"))




# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    # Отдаём новый Next.js клиент если собран, иначе legacy vanilla-JS.
    new_index = CLIENT_DIST / "index.html"
    if new_index.is_file():
        return FileResponse(str(new_index), headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' wss:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'",
        })
    legacy_index = LEGACY_STATIC_DIR / "index.html"
    if legacy_index.is_file():
        return FileResponse(str(legacy_index), headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' wss:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'",
        })
    raise HTTPException(status_code=404, detail="Web client not built")


# Раздача APK мобайла (/mobile/version, /mobile/download) — web/routes/mobile.py
from web.routes.mobile import router as _mobile_router
app.include_router(_mobile_router)


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
async def history(session: str = "", limit: int = 50, scope: str = "chat"):
    """Подгрузить переписку для клиента (user/assistant, без system).

    scope='chat' — основная история; scope='tech' — техническая, только владельцу.
    Клиент вызывает один раз после `ready` чтобы показать прошлый контекст.
    """
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Rate limit
    from tools import rate_limit as _rl
    allowed, retry = _rl.check_and_record(_web_user_id(tg_id), "history")
    if not allowed:
        raise HTTPException(429, detail=f"Too many history requests, retry in {retry}s",
                            headers={"Retry-After": str(retry)})
    user_id = _web_user_id(tg_id)
    if scope == "tech":
        if not OWNER_TG_ID or tg_id != OWNER_TG_ID:
            raise HTTPException(status_code=403, detail="tech scope: owner only")
        msgs = _load_session("tech_" + user_id) or []
    else:
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
async def oauth_google_callback(code: str = "", state: str = "", error: str = "",
                                 request: Request = None):
    """
    Принимает редирект от Google OAuth, автоматически обменивает код,
    показывает результат. Пользователю не нужно копировать код вручную.
    """
    from tools.gdrive_tools import parse_oauth_state, exchange_code
    # Rate limit per IP (без сессии — редирект от Google)
    client_ip = request.client.host if request and request.client else "anon"
    from tools import rate_limit as _rl
    allowed, retry = _rl.check_and_record(f"ip:{client_ip}", "oauth")
    if not allowed:
        raise HTTPException(429, detail=f"Too many OAuth requests, retry in {retry}s",
                            headers={"Retry-After": str(retry)})

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

# Загрузка/скачивание файлов workspace — web/routes/files.py
from web.routes.files import router as _files_router
app.include_router(_files_router)


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


# Тех-канал владельца (owner_inbox) — вынесен в web/routes/owner_inbox.py
from web.routes.owner_inbox import router as _owner_inbox_router
app.include_router(_owner_inbox_router)









@app.websocket("/ws")
async def chat(websocket: WebSocket, session: str = ""):
    await websocket.accept()

    tg_id = _verify_session(session) if session else None
    if not tg_id:
        await websocket.send_json(_wsp(AuthRequired(bot=BOT_USERNAME)))
        await websocket.close(code=4001)
        return

    user_id  = _web_user_id(tg_id)
    _ensure_profile(user_id)
    is_owner_ws = OWNER_TG_ID and tg_id == OWNER_TG_ID
    is_approved_ws = _is_approved(user_id)

    # Owner channel: регистрируем WS для push-уведомлений
    from tools.owner_channel import register as _och_register, unregister as _och_unregister, init as _och_init
    _och_init(asyncio.get_running_loop())
    _ws_key = str(id(websocket))
    _owner_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    if is_owner_ws:
        _och_register(_ws_key, _owner_queue, owner_id=user_id)

    # Формируем permissions для drawer-меню
    _perms = ["chat", "files"]
    if is_approved_ws:
        _perms.extend(["reminders", "tasks"])
        _perms.extend(["gcal", "gsheet", "gdrive"])
        if is_owner_ws:
            _perms.append("owner_admin")  # stats/users/versions/rituals/kidmode

    # Готовим ws_ready с флагами доступности
    _profile = load_user_profile(user_id) or {}
    _gd_auth = gdrive_authorized(user_id) if is_approved_ws else False

    # Счётчики для сайдбара (Aurora UI design)
    _counts = _compute_sidebar_counts(user_id, is_approved_ws, is_owner_ws)

    await websocket.send_json(_wsp(Ready(
        name=_profile.get("name", ""),
        is_owner=is_owner_ws,
        is_approved=is_approved_ws,
        gdrive_authorized=_gd_auth,
        gdrive_email=gdrive_status(user_id).get("email", "") if _gd_auth else "",
        permissions=_perms,
        counts=SidebarCounts(**_counts),
    )))
    logger.info(f"WS connect: {user_id} owner={is_owner_ws} approved={is_approved_ws}")

    # Фоновая задача: читаем _owner_queue и шлём в WS
    async def _forward_owner_messages():
        if not is_owner_ws:
            return
        while True:
            try:
                msg = await asyncio.wait_for(_owner_queue.get(), timeout=30)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    _owner_task = asyncio.create_task(_forward_owner_messages())

    # Карточка «Из памяти» — редкая и только на «особенные» совпадения:
    # счётчик сообщений с последней карточки (кулдаун) + уже показанные факты.
    _msgs_since_card = 0
    _shown_card_facts: set[str] = set()

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            if data.get("type") == "ping":
                # Session age check: каждые 5 минут проверяем не протухла ли сессия
                if int(time.time() / 300) % 1 == 0:  # каждый ping — дешёво
                    tg = _verify_session(session) if session else None
                    if not tg:
                        await websocket.send_json(_wsp(AuthRequired(bot=BOT_USERNAME)))
                        await websocket.close(code=4001)
                        break
                await websocket.send_json(_wsp(Pong()))
                continue

            # Анкета: пользователь сам заполняет профиль (необязательно, не проверяем)
            if data.get("type") == "profile_save":
                await _ws_profile_save(websocket, data, user_id)
                continue

            # Команды
            if data.get("type") == "command":
                await _ws_command(websocket, data, user_id=user_id, tg_id=tg_id,
                                  is_owner_ws=bool(is_owner_ws), is_approved_ws=is_approved_ws)
                continue

            text = data.get("content", "").strip()
            mode = (data.get("mode") or "chat").strip().lower()
            is_tech = (mode == "tech") and bool(is_owner_ws)
            # Прикреплённые файлы — поддержка массивов (attachments) и одиночного (attachment).
            # Клиент шлёт N POST'ов через /upload, потом одно WS-сообщение с массивом имён.
            attached_raw = data.get("attachments") or []
            if isinstance(attached_raw, str):
                attached_raw = [attached_raw]
            # Обратная совместимость: одиночное поле attachment
            single_attach = (data.get("attachment") or "").strip()
            if single_attach and not attached_raw:
                attached_raw = [single_attach]

            # Разделяем прикрепления на image и non-image.
            # Image-файлы должны лететь в LLM как vision-content-block (base64),
            # иначе Мира видит только путь и не может посмотреть содержимое.
            # Non-image (pdf/excel/txt и т.п.) остаются упоминанием в тексте —
            # Мира может позвать read_file / excel_read / read_pdf для них.
            import base64 as _b64, mimetypes as _mt
            _IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
            valid_files: list[str] = []
            image_blocks: list[dict] = []
            for name in attached_raw:
                if not isinstance(name, str) or not name.strip():
                    continue
                _att_safe = _safe_filename(name.strip())
                _att_path = _resolve_under(os.path.join(WORKSPACE_DIR, user_id), "inbox", _att_safe) if _att_safe else None
                if not (_att_path and os.path.isfile(_att_path)):
                    continue
                _mime = (_mt.guess_type(_att_safe)[0] or "").lower()
                if _mime in _IMAGE_MIMES:
                    try:
                        with open(_att_path, "rb") as _f:
                            _raw = _f.read()
                        _b64s = _b64.b64encode(_raw).decode("ascii")
                        image_blocks.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{_mime};base64,{_b64s}"},
                        })
                        valid_files.append(f"workspace/inbox/{_att_safe} (картинка)")
                    except Exception as e:
                        logger.warning(f"WS attachment image read failed: {_att_safe}: {e}")
                else:
                    valid_files.append(f"workspace/inbox/{_att_safe}")

            if valid_files:
                prefix = "[Прикреплены файлы:\n  " + "\n  ".join(valid_files) + "]\n\n"
                text = prefix + text
            if not text and not image_blocks:
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

            # === Tech-режим: отдельная сессия, расширенный system, ответ в channel=tech ===
            if is_tech:
                if image_blocks:
                    # картинки в тех-чате пока не поддерживаем (отдельный pipeline)
                    await websocket.send_json({"channel": "tech", "type": "error",
                                               "content": "Картинки в тех-чате пока не поддерживаются."})
                    continue
                tech_uid = "tech_" + user_id
                tmsgs = _load_session(tech_uid) or [
                    {"role": "system", "content": _system_prompt_for(user_id)}
                ]
                tmsgs.append({"role": "user", "content": text, "ts": time.time()})
                # Тримминг истории как в обычном пайплайне
                _sys = [m for m in tmsgs if m["role"] == "system"]
                _rest = [m for m in tmsgs if m["role"] != "system"]
                tmsgs = _sys + _rest[-MAX_HISTORY:]
                _tech_llm = [{k: v for k, v in m.items() if k != "ts"} for m in tmsgs]
                tech_extra = (
                    "(техно-режим: разговор с владельцем-разработчиком в отдельном "
                    "техническом канале. Можно выдавать сырые логи, стеки, дампы и "
                    "технические детали — меньше литературности, больше конкретики. "
                    "Если просит — посмотри в логи, прочти файл, опиши состояние. "
                    "Готова делать инспекцию и инженерное обсуждение.)"
                )
                try:
                    tech_agent = Agent.from_config_file(
                        "alpha", Profile("dev"), user_id, _system_prompt_for(user_id)
                    )
                except FileNotFoundError as e:
                    logger.error(f"tech: agent config alpha не найден: {e}")
                    await websocket.send_json({"channel": "tech", "type": "error",
                                               "content": "Конфиг агента не найден."})
                    continue
                await websocket.send_json({"channel": "tech", "type": "thinking"})
                _tech_ws_loop = asyncio.get_running_loop()
                def _tech_on_progress(text: str) -> None:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_json({"channel": "tech", "type": "thought", "content": text}),
                            _tech_ws_loop,
                        )
                    except Exception:
                        pass
                try:
                    answer = await asyncio.to_thread(
                        tech_agent.run, _tech_llm, None, tech_extra, _tech_on_progress
                    )
                except Exception as e:
                    logger.error(f"tech alpha.run: {e}", exc_info=True)
                    await websocket.send_json({"channel": "tech", "type": "error",
                                               "content": "Что-то пошло не так. Попробуй ещё раз."})
                    continue
                tmsgs.append({"role": "assistant", "content": answer, "ts": time.time()})
                _save_session(tech_uid, tmsgs)
                await websocket.send_json({
                    "channel": "tech",
                    "type": "message",
                    "content": answer,
                    "ts": time.time(),
                })
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

            # Если есть картинки — content становится list с text + image_url
            # блоками (формат OpenAI Vision / Anthropic Claude vision).
            # Иначе — обычная строка.
            if image_blocks:
                content_blocks: list = []
                if text:
                    content_blocks.append({"type": "text", "text": text})
                content_blocks.extend(image_blocks)
                msgs.append({"role": "user", "content": content_blocks, "ts": time.time()})
            else:
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
            matches: list[dict] = []
            try:
                matches = semantic_memory.search(user_id, text, top_k=5, max_distance=0.35)
                augment = semantic_memory.format_for_prompt(matches)
            except Exception as e:
                logger.warning(f"semantic_memory search: {e}")
            _msgs_since_card += 1  # кулдаун карточки «Из памяти»
            llm_msgs = [{k: v for k, v in m.items() if k != "ts"} for m in msgs]
            changelog_aug = _changelog_augment(user_id)
            incoming_aug = _incoming_augment(user_id)
            extra_aug = "\n\n".join(filter(None, [augment, changelog_aug, incoming_aug]))
            if extra_aug and llm_msgs and llm_msgs[0].get("role") == "system":
                llm_msgs[0] = {**llm_msgs[0], "content": llm_msgs[0]["content"] + "\n\n" + extra_aug}

            await websocket.send_json({"type": "thinking"})

            # 💭-облачко: Мира перед каждым tool_call шлёт «думаю про X».
            # alpha.run крутится в asyncio.to_thread, поэтому отправляем
            # через run_coroutine_threadsafe в основной event loop.
            _ws_loop = asyncio.get_running_loop()
            def _on_progress(text: str) -> None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json({"type": "thought", "content": text}),
                        _ws_loop,
                    )
                except Exception:
                    pass

            # Инверсия: Мира всегда отвечает сама. alpha.run умеет вызывать
            # инструменты (web_search, gcal, schedule_reminder, generate_image,
            # excel и т.д.) — специалисты Конклава ей доступны как инструменты,
            # а не как маршрут «мимо» её личности.
            try:
                answer = await asyncio.to_thread(alpha.run, llm_msgs, None, None, _on_progress)
            except Exception as e:
                logger.error(f"alpha.run: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "content": "Что-то пошло не так. Попробуй ещё раз."})
                continue

            # Если подсказка про новые фичи показывалась — фиксируем, что
            # пользователь её «увидел» (Мира получила её в контекст). Дальше
            # _changelog_augment вернёт "" пока WHATS_NEW.md снова не обновится.
            if changelog_aug:
                _mark_changelog_seen(user_id)
            # Аналогично — входящие сообщения Мира получила в контекст, помечаем
            # их seen. Не идеально (Мира могла не упомянуть), но достаточно:
            # если важно, она их зачитала; если не зачитала и человек спросит —
            # они есть в БД и она сможет их найти позже (другой инструмент).
            if incoming_aug:
                _mark_incoming_seen(user_id)

            # Снимок output/ ПОСЛЕ хода — diff с _output_before даёт список
            # файлов, созданных/обновлённых Мирой за этот ход. Плюс явные
            # прикрепления через attach_file tool (pop_pending_attachments).
            # Сливаем, дедуплицируем по (name, dir).
            from tools.file_tools import pop_pending_attachments
            manual = pop_pending_attachments(user_id)
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
            # Сливаем manual + auto, дедуплицируем
            merged = list({(a["name"], a["dir"]): a for a in (attachments + manual)}.values())

            # Сохраняем ответ в постоянную историю. И Конклав-путь (alpha_msgs —
            # отдельный список), и alpha.run (llm_msgs — копия c augment) не пишут
            # в основной msgs. Без этого следующий ход видит чат без её ответов
            # и Мира «забывает» что уже отвечала.
            assistant_msg = {"role": "assistant", "content": answer, "ts": time.time()}
            if merged:
                assistant_msg["attachments"] = merged
            msgs.append(assistant_msg)

            # Карточка «Из памяти»: только если совпадение очень близкое И прошёл
            # кулдаун (не на каждое сообщение) И этот факт ещё не показывали.
            # learned-ивент не шлём — это recall, а не новый инсайт.
            cards_payload: list | None = None
            if _msgs_since_card >= MEMORY_CARD_COOLDOWN:
                _cards = _build_cards(user_id, matches=matches,
                                      exclude_facts=_shown_card_facts)
                if _cards:
                    cards_payload = _cards
                    _msgs_since_card = 0
                    for _c in _cards:
                        if _c.get("fact"):
                            _shown_card_facts.add(_c["fact"])
                            logger.info(f"memory-card shown: {user_id} d<{MEMORY_CARD_MAX_DISTANCE}")

            # Дробление: длинный ответ на 2-3 сообщения для живого ритма.
            # Attachments крепим к ПЕРВОМУ куску (там и галерея на клиенте),
            # cards — к ПОСЛЕДНЕМУ (карточка «Из памяти» — это эпилог реплики).
            # Задержка перед следующим чанком пропорциональна длине предыдущего —
            # имитируем typewriter (~45 символов/сек). Без этого второй чанк
            # появляется ещё пока первый «печатается», и оба прыгают одновременно.
            from tools.chunking import split_for_chat
            parts = split_for_chat(answer) or [answer]
            prev_chars = 0
            for idx, chunk in enumerate(parts):
                if idx > 0:
                    wait = max(0.45, min(prev_chars / 45.0 + 0.35, 4.0))
                    await asyncio.sleep(wait)
                _msg: dict = {"type": "message", "content": chunk}
                if idx == 0 and merged:
                    _msg["attachments"] = merged
                if idx == len(parts) - 1 and cards_payload:
                    _msg["cards"] = cards_payload
                await websocket.send_json(_msg)
                prev_chars = len(chunk)

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

            # Mirror в Telegram-чат — НАМЕРЕННАЯ фича, не баг: владелец хочет
            # видеть одинаковую историю в телеге и в приложении при переключении
            # интерфейсов. Дублирование осознанное, опт-аут не нужен. Шлём
            # асинхронно через threading, чтобы не блокировать WS-обработчик.
            # tg_id уже из верифицированной сессии — никакого подделанного chat_id.
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
    finally:
        # Cleanup owner channel
        try:
            _owner_task.cancel()
        except Exception:
            pass
        if is_owner_ws:
            _och_unregister(_ws_key)


# --- Корневые статик-ассеты Next.js (mira-avatar-full.png, favicon и пр.) ---
# Next.js кладёт файлы из public/ в корень dist/. /_next смонтирован отдельно,
# а эти корневые файлы иначе отдавали 404 (аватар Миры не грузился).
# РЕГИСТРИРУЕТСЯ ПОСЛЕДНИМ среди GET-роутов — catch-all {path}, чтобы не
# затенять /health, /files/*, /mobile/* и т.д. (они определены выше).
@app.get("/{asset_path:path}")
async def _serve_client_asset(asset_path: str):
    candidate = (CLIENT_DIST / asset_path).resolve()
    dist_root = CLIENT_DIST.resolve()
    # Защита от path traversal: только файлы строго внутри dist.
    if candidate.is_file() and str(candidate).startswith(str(dist_root) + os.sep):
        return FileResponse(str(candidate))
    raise HTTPException(status_code=404, detail="Not found")


# --- Startup: retention cleanup + rate-limit cleanup ---

@app.on_event("startup")
async def _startup_cleanup():
    """Retention: чистим сессии, не обновлявшиеся дольше RETENTION_DAYS дней.
    RETENTION_DAYS=0 (или меньше) полностью отключает чистку."""
    import asyncio
    import threading

    def _run_once():
        try:
            from tools import db
            from datetime import datetime, timedelta
            days = int(os.getenv("RETENTION_DAYS", "90"))
            if days <= 0:
                return  # retention отключён
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            n = db.delete_sessions_older_than(cutoff)
            if n:
                logger.info(f"retention: удалено {n} сессий неактивных > {days} дн.")
        except Exception as e:
            logger.warning(f"retention cleanup error: {e}")

    # Первый прогон — в фоне, чтобы не блокировать старт.
    threading.Thread(target=_run_once, daemon=True).start()

    # Периодически — раз в сутки.
    async def _periodic_retention():
        while True:
            await asyncio.sleep(86400)
            await asyncio.to_thread(_run_once)
    asyncio.create_task(_periodic_retention())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
