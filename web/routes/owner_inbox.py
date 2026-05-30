"""web/routes/owner_inbox.py — тех-канал владельца (owner-only).

Вынесено из web/app.py (Фаза 6 рефакторинга монолитов). Эти эндпоинты
изолированы: зависят только от web.deps (owner-сессия) и tools/*, не от
agent/WS-петли — поэтому вынесены первыми.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from web.deps import verify_owner_session

logger = logging.getLogger("MiraWeb")

router = APIRouter()


@router.get("/m/owner_inbox")
async def owner_inbox_list(session: str = "", since_id: int = 0, limit: int = 200, unread: int = 0):
    """История тех-чата владельца. ?since_id=N&limit=200&unread=1"""
    if not verify_owner_session(session):
        raise HTTPException(status_code=401, detail="owner only")
    from tools import db as _db
    items = _db.list_inbox(since_id=since_id, limit=min(max(limit, 1), 500), unread_only=bool(unread))
    return {"items": items}


@router.post("/m/owner_inbox/{item_id}/read")
async def owner_inbox_mark_read(item_id: int, request: Request):
    """Отметить запись прочитанной. Body: {session}"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not verify_owner_session((body.get("session") or "").strip()):
        raise HTTPException(status_code=401, detail="owner only")
    from tools import db as _db
    ok = _db.mark_inbox_read(item_id)
    return {"ok": ok}


@router.post("/m/owner_inbox/{item_id}/action")
async def owner_inbox_action(item_id: int, request: Request):
    """Применить действие к записи (approve/reject и пр.).
    Body: {session, action: 'approve'|'reject'|...}"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    if not verify_owner_session((body.get("session") or "").strip()):
        raise HTTPException(status_code=401, detail="owner only")
    action = (body.get("action") or "").strip().lower()
    if not action:
        raise HTTPException(status_code=400, detail="action required")
    from tools import db as _db
    items = _db.list_inbox(since_id=item_id - 1, limit=1)
    if not items or items[0]["id"] != item_id:
        raise HTTPException(status_code=404, detail="not found")
    item = items[0]
    # Применяем действие в зависимости от типа
    result: dict = {"ok": True}
    if item["type"] == "approval_request" and action in ("approve", "reject"):
        from tools import access_tools as _at
        target = (item.get("payload") or {}).get("user_id") or ""
        if not target:
            raise HTTPException(status_code=400, detail="no target user")
        if action == "approve":
            ok = _at.approve(target)
        else:
            ok = _at.reject(target)
        result["target"] = target
        result["applied"] = ok
    _db.set_inbox_action(item_id, action)
    # WS notify прочим клиентам владельца
    try:
        from tools.owner_channel import push_to_owner
        push_to_owner({
            "channel": "tech",
            "type": "inbox_update",
            "id": item_id,
            "action": action,
        })
    except Exception:
        pass
    return result
