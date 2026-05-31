"""web/routes/files.py — загрузка и скачивание файлов workspace.

Вынесено из web/app.py (Фаза 6). Зависит от web.deps (сессия), web.security
(safe_filename/resolve_under), tools.rate_limit и WORKSPACE_DIR — не от WS/agent-петли.
"""

import os
import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from web.deps import verify_session as _verify_session, web_user_id as _web_user_id
from web.security import safe_filename as _safe_filename, resolve_under as _resolve_under
from agent import WORKSPACE_DIR
from tools import rate_limit

logger = logging.getLogger("MiraWeb")

router = APIRouter()

UPLOAD_MAX_BYTES = 20 * 1024 * 1024


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...), session: str = ""):
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

    # Предпроверка по Content-Length — отсекаем заведомо большие тела до чтения.
    clen = request.headers.get("content-length", "")
    if clen.isdigit() and int(clen) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail=rate_limit.friendly_message("size", 0))

    # Потоковое чтение с жёстким лимитом: не доверяем Content-Length и не
    # буферизуем в память больше лимита (защита от DoS большим аплоадом).
    total = 0
    overflow = False
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > UPLOAD_MAX_BYTES:
                overflow = True
                break
            f.write(chunk)
    if overflow:
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise HTTPException(status_code=413, detail=rate_limit.friendly_message("size", 0))
    logger.info(f"upload: {user_id} → {filename} ({total} bytes)")
    # Системную пометку в сессию НЕ добавляем — иначе Мира начнёт
    # анализировать файл, ещё не получив задание от пользователя.
    # Привязка к ходу делается в WS-обработчике: клиент шлёт
    # {content: "...", attachment: "filename"} — там и подкладываем
    # маркер «[Прикреплён: ...]» к тексту пользователя.
    return {"ok": True, "filename": filename, "size": total}


@router.get("/files/{file_path:path}")
async def download_file(file_path: str, session: str = ""):
    """Скачивает файл из workspace пользователя (только inbox/ и output/)."""
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    # Rate limit
    allowed, retry = rate_limit.check_and_record(user_id, "files")
    if not allowed:
        raise HTTPException(429, detail=f"Too many file requests, retry in {retry}s",
                            headers={"Retry-After": str(retry)})
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
