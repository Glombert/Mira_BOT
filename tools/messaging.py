"""tools/messaging.py — передача сообщений между пользователями через Миру.

Поток:
  отправитель → "Передай Андрею: ..." → Мира зовёт send_to_user(target=..., body=...)
  → ВОЗВРАЩАЕТ pending preview ("Готовлю передать Андрею «...» — подтвердить?")
  → Мира спрашивает у пользователя
  → пользователь подтверждает
  → Мира зовёт confirm_send_to_user(pending_id=N)
  → сообщение в БД + TG-DM + WS-push получателю.

Защита:
- Гостям нельзя отправлять (`block_send_for_status`).
- Получатель в blocked_senders отправителя → отказ.
- Двухфактор (pending → confirm) — Мира никогда не отправит без явного «да».
- Тулу confirm доступна только pending'у, принадлежащему вызвавшему.
- TTL pending 10 минут — потом нужно начать заново.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("Ouroboros")

_MAX_BODY = 4000


def _list_approved_users() -> list[dict]:
    """Все одобренные (regular + owner) пользователи."""
    from tools import db
    out: list[dict] = []
    for user_id, profile in db.list_user_profiles():
        status = profile.get("status", "")
        if status not in ("owner", "regular"):
            continue
        out.append({
            "id":   user_id,
            "name": profile.get("name", "—"),
            "telegram_id": user_id.replace("tg_", "").replace("cli_", ""),
            "status": status,
        })
    return out


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def find_user(query: str, caller_id: str = "") -> dict:
    """Ищет пользователя по имени/username.

    Возвращает:
      {ok: True, user: {...}} — точное совпадение
      {ok: False, matches: [...]} — несколько совпадений (Мира попросит уточнить)
      {ok: False, error: "..."} — не найдено
    """
    q = _norm(query)
    if not q:
        return {"ok": False, "error": "Не указано имя получателя."}
    users = _list_approved_users()
    # Сами себе не пишем
    if caller_id:
        users = [u for u in users if u["id"] != caller_id]
    # 1) точное совпадение по name (case-insensitive)
    exact = [u for u in users if _norm(u["name"]) == q]
    if len(exact) == 1:
        return {"ok": True, "user": exact[0]}
    if len(exact) > 1:
        return {"ok": False, "matches": exact, "error": "Несколько людей с таким именем — уточни кто."}
    # 2) startswith / contains
    partial = [u for u in users if q in _norm(u["name"])]
    if len(partial) == 1:
        return {"ok": True, "user": partial[0]}
    if len(partial) > 1:
        return {"ok": False, "matches": partial, "error": "Несколько подходящих — уточни."}
    return {"ok": False, "error": f"Не нашла пользователя «{query}» в списке одобренных."}


def _caller_can_send(caller_id: str) -> tuple[bool, str]:
    from tools import db
    profile = db.load_user_profile(caller_id)
    if not profile:
        return False, "Профиль отправителя не найден."
    if profile.get("status") not in ("owner", "regular"):
        return False, "Только одобренные пользователи могут передавать сообщения."
    return True, ""


def _recipient_blocks_sender(recipient_id: str, sender_id: str) -> bool:
    from tools import db
    profile = db.load_user_profile(recipient_id) or {}
    blocked = profile.get("blocked_senders") or []
    return sender_id in blocked


def send_to_user(target: str, body: str, caller_id: str = "") -> dict:
    """Готовит к отправке. Возвращает pending_id и превью.

    Мира НЕ доставляет сразу — это первый шаг двухфактора. Затем спрашивает
    у пользователя «отправить?» и при «да» вызывает confirm_send_to_user.
    """
    ok, err = _caller_can_send(caller_id)
    if not ok:
        return {"ok": False, "error": err}

    body = (body or "").strip()
    if not body:
        return {"ok": False, "error": "Пустое тело сообщения."}
    if len(body) > _MAX_BODY:
        return {"ok": False, "error": f"Сообщение длиннее лимита ({_MAX_BODY} символов)."}

    f = find_user(target, caller_id=caller_id)
    if not f.get("ok"):
        return f

    user = f["user"]
    if _recipient_blocks_sender(user["id"], caller_id):
        # «Не доставляется» — но Мира не раскрывает факт блокировки.
        return {"ok": False, "error": "Не получится — этот человек сейчас не принимает сообщения от тебя."}

    from tools import db
    pending_id = db.add_pending_send(
        from_user_id=caller_id,
        to_user_id=user["id"],
        target_name=user["name"],
        body=body,
    )
    logger.info(f"messaging: pending #{pending_id} from {caller_id} → {user['id']} ({len(body)} chars)")
    return {
        "ok": True,
        "pending_id": pending_id,
        "target_user_id": user["id"],
        "target_name": user["name"],
        "preview": body[:200],
        "needs_confirmation": True,
        "hint": (
            "Покажи пользователю превью и спроси «Отправить?». "
            "Если согласен — позови confirm_send_to_user(pending_id). "
            "Если передумал — позови cancel_send_to_user(pending_id)."
        ),
    }


def confirm_send_to_user(pending_id: int, caller_id: str = "") -> dict:
    """Доставляет ранее подготовленное сообщение."""
    from tools import db
    pending = db.get_pending_send(int(pending_id), caller_id)
    if not pending:
        return {"ok": False, "error": "Нет такого черновика — возможно, истёк (10 минут) или ты не его автор."}
    # Проверка истечения
    try:
        expires = datetime.fromisoformat(pending["expires_at"])
        if datetime.now() > expires:
            db.delete_pending_send(int(pending_id))
            return {"ok": False, "error": "Срок подтверждения истёк, начни заново."}
    except ValueError:
        pass

    # Повторная проверка блока (вдруг получатель только что заблокировал)
    if _recipient_blocks_sender(pending["to_user_id"], caller_id):
        db.delete_pending_send(int(pending_id))
        return {"ok": False, "error": "Не получится — этот человек сейчас не принимает сообщения от тебя."}

    sender_profile = db.load_user_profile(caller_id) or {}
    sender_name = sender_profile.get("name") or "—"

    # 1) Запись в БД получателя
    msg_id = db.deliver_user_message(
        from_user_id=caller_id,
        from_name=sender_name,
        to_user_id=pending["to_user_id"],
        body=pending["body"],
    )

    # 2) Telegram DM получателю
    _deliver_telegram(pending["to_user_id"], sender_name, pending["body"])

    # 3) FCM push получателю (если есть)
    try:
        from tools import fcm_tools
        fcm_tools.send_push(
            user_id=pending["to_user_id"],
            title=f"Сообщение от {sender_name}",
            body=pending["body"][:240],
        )
    except Exception as e:
        logger.warning(f"messaging: FCM не сработал: {e}")

    db.delete_pending_send(int(pending_id))
    logger.info(f"messaging: delivered #{msg_id} {caller_id} → {pending['to_user_id']}")
    return {
        "ok": True,
        "delivered": True,
        "message_id": msg_id,
        "target_name": pending["target_name"],
    }


def cancel_send_to_user(pending_id: int, caller_id: str = "") -> dict:
    """Отменяет черновик. Идемпотентно (нет такого pending → тоже ok)."""
    from tools import db
    pending = db.get_pending_send(int(pending_id), caller_id)
    if pending:
        db.delete_pending_send(int(pending_id))
    return {"ok": True, "cancelled": True}


def block_sender(target: str, caller_id: str = "") -> dict:
    """Получатель просит больше не передавать сообщения от X.

    target — имя/username отправителя. Записываем X.id в
    caller.blocked_senders. После этого все send_to_user(target=caller)
    от X будут возвращать «не принимает сообщения».
    """
    if not caller_id:
        return {"ok": False, "error": "Не указан вызывающий."}
    f = find_user(target, caller_id=caller_id)
    if not f.get("ok"):
        return f
    sender = f["user"]
    from tools import db
    profile = db.load_user_profile(caller_id) or {}
    blocked = list(profile.get("blocked_senders") or [])
    if sender["id"] not in blocked:
        blocked.append(sender["id"])
        profile["blocked_senders"] = blocked
        db.save_user_profile(caller_id, profile)
    return {"ok": True, "blocked": sender["name"]}


def unblock_sender(target: str, caller_id: str = "") -> dict:
    """Снять блокировку отправителя."""
    if not caller_id:
        return {"ok": False, "error": "Не указан вызывающий."}
    f = find_user(target, caller_id=caller_id)
    if not f.get("ok"):
        return f
    sender = f["user"]
    from tools import db
    profile = db.load_user_profile(caller_id) or {}
    blocked = [x for x in (profile.get("blocked_senders") or []) if x != sender["id"]]
    profile["blocked_senders"] = blocked
    db.save_user_profile(caller_id, profile)
    return {"ok": True, "unblocked": sender["name"]}


def _deliver_telegram(to_user_id: str, from_name: str, body: str) -> None:
    """Шлёт получателю личное сообщение через бота Mira.

    to_user_id формата tg_<id>; используем <id> как chat_id для DM.
    Текст обёрнут «От {имя}: ...» — чтобы получатель сразу видел источник.
    Длинные сообщения чанкуются через access_tools._tg_split.
    """
    import os
    import json
    import threading
    import urllib.parse, urllib.request

    if not to_user_id.startswith("tg_"):
        return
    chat_id = to_user_id.split("_", 1)[1]
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id.isdigit():
        return

    header = f"📨 Сообщение от {from_name}:\n"
    full = header + body
    try:
        from tools.access_tools import _tg_split
        chunks = _tg_split(full, limit=3900)
    except Exception:
        chunks = [full]

    def _send():
        try:
            for chunk in chunks:
                data = urllib.parse.urlencode({"chat_id": chat_id, "text": chunk}).encode()
                urllib.request.urlopen(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=data, timeout=8,
                )
        except Exception as e:
            logger.warning(f"messaging: TG send to {to_user_id} failed: {e}")

    threading.Thread(target=_send, daemon=True).start()
