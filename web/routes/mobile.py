"""web/routes/mobile.py — раздача APK мобильного приложения.

Вынесено из web/app.py (Фаза 6). Полностью изолировано: проксирует релизы
приватного репо Mira_Mobile с GitHub (токен GITHUB_APK_TOKEN), не зависит от
auth/agent. /mobile/download → 302 на GitHub CDN (APK на сервере не хранится).
"""

import os
import time
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from web.deps import BOT_USERNAME, verify_session as _verify_session, web_user_id as _web_user_id

logger = logging.getLogger("MiraWeb")

router = APIRouter()

_MOBILE_VERSION_CACHE: dict = {"ts": 0.0, "info": None}
_MOBILE_VERSION_TTL = 600
_GITHUB_APK_TOKEN = os.getenv("GITHUB_APK_TOKEN", "")
_MOBILE_DL_RATE: dict[str, list[float]] = {}
_MOBILE_DL_RATE_MAX = 30


def _public_base_url() -> str:
    return os.getenv("MIRA_PUBLIC_URL", "https://mira-bot.duckdns.org")


def _fetch_latest_release() -> dict | None:
    """{tag, body, asset_id, asset_name} последнего релиза Mira_Mobile. Кэш 10 мин."""
    now = time.time()
    if now - _MOBILE_VERSION_CACHE["ts"] < _MOBILE_VERSION_TTL:
        return _MOBILE_VERSION_CACHE["info"]

    token = _GITHUB_APK_TOKEN
    if not token:
        logger.warning("/mobile: GITHUB_APK_TOKEN не задан")
        return None

    import urllib.request as _req, urllib.error as _err, json as _js
    try:
        rq = _req.Request(
            "https://api.github.com/repos/Glombert/Mira_Mobile/releases/latest",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "mira-web",
            },
        )
        with _req.urlopen(rq, timeout=5) as resp:
            data = _js.loads(resp.read())
        asset_id = None
        asset_name = ""
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".apk"):
                asset_id = asset.get("id")
                asset_name = asset.get("name", "")
                break
        info: dict | None = {
            "tag": data.get("tag_name", ""),
            "body": (data.get("body") or "")[:2000],
            "asset_id": asset_id,
            "asset_name": asset_name,
        }
    except Exception as e:
        logger.warning(f"/mobile: github api error: {e}")
        info = None

    _MOBILE_VERSION_CACHE["ts"] = now
    _MOBILE_VERSION_CACHE["info"] = info
    return info


@router.get("/mobile/version")
async def mobile_version():
    info = _fetch_latest_release()
    if not info:
        return {"version": "", "apk_url": "", "release_notes": ""}
    return {
        "version": info["tag"].lstrip("v"),
        "apk_url": f"{_public_base_url()}/mobile/download",
        "release_notes": info["body"],
    }


@router.get("/mobile/download")
async def mobile_download(request: Request):
    """Прокси: запрос к GitHub asset API → 302 на CDN → редиректим клиента."""
    client_ip = request.client.host if request.client else "?"
    _now = time.time()
    bucket = _MOBILE_DL_RATE.setdefault(client_ip, [])
    bucket[:] = [t for t in bucket if _now - t < 60]
    if len(bucket) >= _MOBILE_DL_RATE_MAX:
        raise HTTPException(429, detail="Too many download requests",
                            headers={"Retry-After": "60"})
    bucket.append(_now)

    info = _fetch_latest_release()
    if not info or not info.get("asset_id"):
        raise HTTPException(404, detail="APK не найден")

    token = _GITHUB_APK_TOKEN
    if not token:
        raise HTTPException(503, detail="GITHUB_APK_TOKEN not configured")

    import urllib.request as _req, urllib.error as _err

    asset_api = (
        f"https://api.github.com/repos/Glombert/Mira_Mobile/releases/"
        f"assets/{info['asset_id']}"
    )
    rq = _req.Request(asset_api, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/octet-stream",
        "User-Agent": "mira-web",
    })

    class _NoRedirect(_req.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    opener = _req.build_opener(_NoRedirect)
    try:
        opener.open(rq, timeout=8)
        raise HTTPException(502, detail="ожидался редирект от GitHub")
    except _err.HTTPError as e:
        if e.code in (301, 302, 307):
            signed = e.headers.get("Location")
            if not signed:
                raise HTTPException(502, detail="GitHub не дал Location")
            logger.info("/mobile/download: redirecting to GitHub CDN")
            return RedirectResponse(signed, status_code=302)
        raise HTTPException(502, detail=f"GitHub asset error: {e.code}")


# --- Mobile auth-страницы (Telegram Login Widget + deep-link) ---
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


@router.get("/auth/mobile")
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


@router.post("/m/register_push_token")
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


@router.get("/m/auth")
async def mobile_auth_redirect(code: str = ""):
    """Бот шлёт юзеру inline-кнопку с URL сюда → Telegram открывает страницу →
    мы обмениваем одноразовый code на session token → редиректим в
    miramobile://auth?token=... → Android отдаёт MiraMobile.

    Зачем не сразу deeplink в кнопке: Telegram BotAPI разрешает в inline_button.url
    только http/https/tg-схемы; кастомные (miramobile://) запрещены.
    """
    from web.security import redeem_mobile_auth_code
    token = redeem_mobile_auth_code(code) if code else None
    if not token:
        return HTMLResponse("Ссылка устарела или недействительна. Запроси новую через /login в боте.", status_code=400)
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


