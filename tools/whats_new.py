"""tools/whats_new.py — список новых возможностей Миры.

Парсит WHATS_NEW.md в корне репозитория и возвращает фичи, отсортированные
от свежих к старым, с фильтром по audience.

Формат разделов:
    ## YYYY-MM-DD
    - [ALL] **Название**: описание.
    - [OWNER] **Название**: описание.

Audience:
  ALL    — видят все одобренные пользователи
  OWNER  — только владелец

`mtime` файла используется для сравнения с last_changelog_seen у профиля.
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("Ouroboros")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHATS_NEW_PATH = os.path.join(_PROJECT_ROOT, "WHATS_NEW.md")

_DATE_RE  = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
_ENTRY_RE = re.compile(r"^-\s+\[(ALL|OWNER)\]\s+(.+)$", re.DOTALL)


def _parse() -> list[dict]:
    """Возвращает список записей: {date, audience, text}.

    Поддерживает многострочные записи: всё после '- [AUD]' до следующего
    '- [' или '## ' попадает в text (через _DATE_RE/строчный сплит).
    """
    if not os.path.isfile(WHATS_NEW_PATH):
        return []
    try:
        with open(WHATS_NEW_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.warning(f"whats_new: не удалось прочитать {WHATS_NEW_PATH}: {e}")
        return []

    entries: list[dict] = []
    current_date: Optional[str] = None
    cur_aud: Optional[str] = None
    cur_buf: list[str] = []

    def flush():
        if cur_aud and cur_buf and current_date:
            text = " ".join(s.strip() for s in cur_buf).strip()
            if text:
                entries.append({"date": current_date, "audience": cur_aud, "text": text})

    for raw in lines:
        line = raw.rstrip("\n")
        m_date = _DATE_RE.match(line)
        if m_date:
            flush()
            cur_aud = None
            cur_buf = []
            current_date = m_date.group(1)
            continue
        if current_date is None:
            continue
        m_entry = _ENTRY_RE.match(line)
        if m_entry:
            flush()
            cur_aud = m_entry.group(1)
            cur_buf = [m_entry.group(2)]
            continue
        # Продолжение текущей записи (отступ или просто текст)
        if cur_aud is not None:
            if line.startswith("##") or line.strip().startswith("- "):
                flush()
                cur_aud = None
                cur_buf = []
            else:
                cur_buf.append(line)
    flush()
    return entries


def whats_new(audience: str = "all", limit: int = 8) -> dict:
    """Возвращает список новых фич Миры.

    audience='all'   — только записи [ALL]
    audience='owner' — все записи (включая [OWNER])

    limit — сколько последних фич вернуть.
    """
    aud_norm = (audience or "all").strip().lower()
    entries = _parse()
    if not entries:
        return {"ok": True, "entries": [], "summary": "Пока без свежих обновлений."}

    if aud_norm == "owner":
        visible = entries
    else:
        visible = [e for e in entries if e["audience"] == "ALL"]

    # Сортировка от свежих к старым по дате (строки YYYY-MM-DD сравниваются ОК)
    visible.sort(key=lambda e: e["date"], reverse=True)
    visible = visible[: max(1, min(limit, 50))]

    bullets = "\n".join(f"- ({e['date']}) {e['text']}" for e in visible)
    return {
        "ok": True,
        "entries": visible,
        "summary": bullets,
    }


def changelog_mtime() -> float:
    """Mtime WHATS_NEW.md — для сравнения с profile.last_changelog_seen."""
    try:
        return os.path.getmtime(WHATS_NEW_PATH)
    except OSError:
        return 0.0


def latest_entries_since(since_ts: float, audience: str = "all", limit: int = 5) -> list[dict]:
    """Записи, дата которых >= даты since_ts. Используется для подсказки
    «у тебя появились новые возможности» при первом сообщении после рестарта."""
    if since_ts <= 0:
        return whats_new(audience=audience, limit=limit)["entries"]
    cutoff_date = datetime.fromtimestamp(since_ts).strftime("%Y-%m-%d")
    data = whats_new(audience=audience, limit=50)["entries"]
    return [e for e in data if e["date"] >= cutoff_date][:limit]
