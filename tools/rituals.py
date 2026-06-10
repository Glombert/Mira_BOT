"""tools/rituals.py — периодические само-проверки Миры.

Загружает ритуалы из agents/rituals/*.json. Каждый ритуал — это
cron-выражение + промпт. Фоновый поток в telegram_bot проверяет
расписание и запускает просроченные ритуалы в отдельных потоках.

Минимальный интервал между запусками — 60 секунд (защита от
«каждую секунду»).
"""

import json
import os
import re
import logging
import threading
from datetime import datetime
from tools.paths import at_root

logger = logging.getLogger("Ouroboros")

RITUALS_DIR = at_root("agents", "rituals")
MIN_INTERVAL_SEC = 60  # минимальный интервал между запусками

IMPORTANCE_ORDER = {"NONE": 0, "MINOR": 1, "MAJOR": 2, "CRITICAL": 3}


def load_rituals() -> list[dict]:
    """Читает agents/rituals/*.json. Возвращает список словарей ритуалов."""
    rituals: list[dict] = []
    if not os.path.isdir(RITUALS_DIR):
        return rituals
    for fname in sorted(os.listdir(RITUALS_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(RITUALS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rituals.append(data)
        except Exception as e:
            logger.warning(f"rituals: не удалось загрузить {fname}: {e}")
    return rituals


def parse_importance(text: str) -> str:
    """Извлекает #IMPORTANCE: NONE|MINOR|MAJOR|CRITICAL из ответа Миры."""
    m = re.search(r"#IMPORTANCE:\s*(NONE|MINOR|MAJOR|CRITICAL)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return "NONE"


def should_notify(importance: str, threshold: str) -> bool:
    """Должен ли ритуал слать push при данной важности и пороге."""
    imp_level = IMPORTANCE_ORDER.get(importance, 0)
    thr_level = IMPORTANCE_ORDER.get(threshold, 0)
    return imp_level >= thr_level
