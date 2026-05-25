"""tools/owner_channel.py — канал push-уведомлений владельцу через WS.

Отдельный модуль чтобы избежать circular import между web/app.py
и tools/access_tools.py. Используется:
- access_tools.notify_new_user() → push_to_owner({type:'approval_request', ...})
- access_tools.notify_owner() для WS-доставки (дублирует Telegram)
- web/app.py — add/remove при WS connect/disconnect, читает для commands

Потокобезопасность: asyncio.Queue на каждое соединение +
блокировка на список _owner_ws — FastAPI WebSocket живёт в том же event loop,
но register/unregister и send могут быть из разных потоков (notify_new_user
вызывается из Telegram webhook). Поэтому используем call_soon_threadsafe.
"""

import asyncio
import logging
import json

logger = logging.getLogger("MiraWeb")

_owner_queues: dict[str, asyncio.Queue] = {}  # key = str(id(ws))
_loop: asyncio.AbstractEventLoop | None = None


def init(loop: asyncio.AbstractEventLoop) -> None:
    """Сохраняет event loop для call_soon_threadsafe."""
    global _loop
    _loop = loop


def register(ws_key: str, queue: asyncio.Queue, owner_id: str = "") -> None:
    """Регистрирует очередь. owner_id проверяется на принадлежность владельцу (defense in depth)."""
    if owner_id:
        import os as _os
        _owner_tg = _os.getenv("OWNER_TELEGRAM_ID", "0")
        if _owner_tg and _owner_tg != "0" and owner_id not in (f"tg_{_owner_tg}", f"cli_{_owner_tg}"):
            logger.warning(f"owner_channel: попытка регистрации не-owner ({owner_id})")
            return
    _owner_queues[ws_key] = queue
    logger.info(f"owner_channel: registered {ws_key}, total={len(_owner_queues)}")


def unregister(ws_key: str) -> None:
    """Убирает очередь при disconnect."""
    _owner_queues.pop(ws_key, None)
    logger.info(f"owner_channel: unregistered {ws_key}, total={len(_owner_queues)}")


def push_to_owner(payload: dict) -> None:
    """Шлёт payload во все активные WS-сессии владельца. Thread-safe."""
    if not _loop:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    for key, q in list(_owner_queues.items()):
        try:
            # put_nowait безопасен в asyncio.Queue для одного producer из
            # другого потока — очередь не имеет внутреннего threading.Lock.
            # call_soon_threadsafe гарантирует что put выполнится в event loop.
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass
