"""web/routes/mobile.py — раздача APK мобильного приложения.

Вынесено из web/app.py (Фаза 6). Полностью изолировано: проксирует релизы
приватного репо Mira_Mobile с GitHub (токен GITHUB_APK_TOKEN), не зависит от
auth/agent. /mobile/download → 302 на GitHub CDN (APK на сервере не хранится).
"""

import os
import time
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

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
