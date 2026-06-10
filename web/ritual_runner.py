"""web/ritual_runner.py — фоновое выполнение ритуалов и шедул-задач.

Доставка: owner_inbox (всегда) + WS-push канала tech + Telegram при
IMPORTANCE >= notify_threshold ритуала.
"""

import time
import logging
from datetime import datetime

from tools.rituals import parse_importance, should_notify, run_handler
from web.alpha import _invoke_alpha
from web.sessions import _load_session, _save_session

logger = logging.getLogger("MiraWeb")


def _run_scheduled_task(user_id: str, prompt: str) -> str:
    """Выполняет отложенную задачу (kind='task')."""
    answer, _ = _invoke_alpha(user_id, prompt, source="scheduled_task")
    # Сохраняем ответ в сессию
    msgs = _load_session(user_id)
    msgs.append({"role": "assistant", "content": answer, "ts": time.time()})
    _save_session(user_id, msgs)
    return answer


def _run_ritual_background(ritual: dict, user_id: str) -> None:
    """Выполняет ритуал в фоне, сохраняет last_run, кладёт в owner_inbox и
    при IMPORTANCE >= порога — дублирует в Telegram владельцу."""
    from tools import db as _db
    from tools.access_tools import notify_owner as _notify

    if ritual.get("handler"):
        logger.info(f"rituals: запуск '{ritual['name']}' (script-handler)")
        answer = run_handler(ritual["handler"])
        if isinstance(answer, dict):
            # Гибрид: скрипт собрал данные, анализ — за Мирой
            answer, _ = _invoke_alpha(user_id, answer["llm_prompt"], source="ritual",
                                      agent_override=ritual.get("agent"))
    else:
        logger.info(f"rituals: запуск '{ritual['name']}' для {user_id} (агент {ritual.get('agent', 'alpha')})")
        answer, _ = _invoke_alpha(user_id, ritual["prompt"], source="ritual",
                                  agent_override=ritual.get("agent"))

    now_iso = datetime.now().isoformat()
    _db.save_ritual_run(ritual["name"], now_iso, answer[:300])

    importance = parse_importance(answer)
    threshold = ritual.get("notify_threshold", "MAJOR")
    name = ritual["name"]
    title = f"Ритуал: {name} [{importance}]"

    # 1) Тех-чат владельца в приложении — полный ответ, всегда
    inbox_id = _db.append_inbox(
        type_="ritual",
        title=title,
        body=answer,
        importance=importance,
        payload={"ritual": name, "threshold": threshold},
    )
    # 2) WS realtime → канал "tech"
    try:
        from tools.owner_channel import push_to_owner
        push_to_owner({
            "channel": "tech",
            "type": "ritual",
            "id": inbox_id,
            "ts": now_iso,
            "name": name,
            "importance": importance,
            "title": title,
            "body": answer,
        })
    except Exception as e:
        logger.warning(f"rituals: push_to_owner failed: {e}")

    # 3) Telegram владельцу — только если IMPORTANCE >= threshold (как раньше)
    if should_notify(importance, threshold):
        _notify(f"🔔 {title}\n{answer}")
        logger.info(f"rituals: '{name}' → inbox#{inbox_id} + tg ({importance})")
    else:
        logger.info(f"rituals: '{name}' → inbox#{inbox_id} ({importance}, below {threshold})")
