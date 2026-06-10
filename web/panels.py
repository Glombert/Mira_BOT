"""web/panels.py — данные для экранов клиента (сайдбар, бэкапы, карточки памяти)."""

import os
import logging

from agent import MEMORY_DIR, WORKSPACE_DIR
from tools.rituals import load_rituals
from web.ws_protocol import BackupEntry, BackupsData

logger = logging.getLogger("MiraWeb")

MEMORY_CARD_MAX_DISTANCE = float(os.getenv("MEMORY_CARD_MAX_DISTANCE", "0.22"))


def _compute_sidebar_counts(user_id: str, is_approved: bool, is_owner: bool) -> dict:
    """Возвращает counts для ws_ready / permissions_update."""
    counts: dict = {}
    try:
        # Файлы в workspace
        ws_dir = os.path.join(WORKSPACE_DIR, user_id)
        file_count = 0
        for sub in ("inbox", "output"):
            sd = os.path.join(ws_dir, sub)
            if os.path.isdir(sd):
                file_count += len([f for f in os.listdir(sd)
                                  if os.path.isfile(os.path.join(sd, f)) and not f.startswith(".")])
        counts["files"] = file_count
    except Exception:
        counts["files"] = 0

    if is_approved:
        from tools.db import get_conn
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE user_id=? AND kind='reminder' AND status='pending'",
                (user_id,)
            ).fetchone()
            counts["reminders_today"] = rows[0] if rows else 0
            rows = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE user_id=? AND kind='task' AND status='pending'",
                (user_id,)
            ).fetchone()
            counts["tasks"] = rows[0] if rows else 0
        except Exception:
            counts["reminders_today"] = 0
            counts["tasks"] = 0

    if is_owner:
        try:
            from tools.db import get_conn as _gc
            conn = _gc()
            rows = conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()
            counts["users"] = max(rows[0] if rows else 0, 1)
        except Exception:
            counts["users"] = 1
        try:
            counts["rituals"] = len(load_rituals())
        except Exception:
            counts["rituals"] = 0
        try:
            import json
            evo_path = os.path.join(MEMORY_DIR, "evolution_counter.json")
            if os.path.exists(evo_path):
                with open(evo_path) as f:
                    evo = json.load(f)
                counts["evolutions"] = evo.get("count", 0)
            else:
                counts["evolutions"] = 0
        except Exception:
            counts["evolutions"] = 0

    return counts


def _build_cards(user_id: str,
                 matches: list[dict] | None = None,
                 max_distance: float | None = None,
                 exclude_facts: set[str] | None = None) -> list[dict] | None:
    """Структурированная карточка под ответом Миры (Aurora attachment model).

    memory-карточка только когда совпадение по-настоящему близкое
    (distance < max_distance) и этот факт ещё не показывали в сессии.
    Текст берём из m['text'] (чистый). Модель: {kind, label, fact, list}.
    """
    thr = MEMORY_CARD_MAX_DISTANCE if max_distance is None else max_distance
    if not matches:
        return None
    strong = sorted(
        (m for m in matches if m.get("distance", 1.0) < thr),
        key=lambda m: m.get("distance", 1.0),
    )
    facts: list[str] = []
    for m in strong:
        t = (m.get("text") or "").strip().replace("\n", " ")
        if len(t) >= 8 and t not in facts and (not exclude_facts or t[:200] not in exclude_facts):
            facts.append(t[:200])
    if not facts:
        return None
    return [{
        "kind": "memory",
        "label": "Из памяти",
        "fact": facts[0],
        "list": facts[1:4] if len(facts) > 1 else None,
    }]


def _collect_backups_data(user_id: str) -> BackupsData:
    """Список снапшотов бэкапа для owner-экрана Aurora. Снапшоты — датированные
    папки в gdrive:Mira/_archive/memory (versioned backup). rclone-вызов
    синхронный → caller оборачивает в asyncio.to_thread, чтобы не блокировать loop.
    Счётчики фактов/заметок — текущие (снапшоты их не хранят)."""
    import subprocess
    dates: list[str] = []
    try:
        out = subprocess.run(
            ["rclone", "lsf", "gdrive:Mira/_archive/memory/"],
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode == 0:
            dates = sorted((d.rstrip("/") for d in out.stdout.splitlines() if d.strip()),
                           reverse=True)
    except Exception as e:
        logger.warning(f"backups_data: rclone недоступен ({e})")
    try:
        from tools import semantic_memory
        facts = semantic_memory.count(user_id)
    except Exception:
        facts = 0
    try:
        from agent import load_reflections
        notes = len(load_reflections() or [])
    except Exception:
        notes = 0
    entries = [
        BackupEntry(id=d, created_at=d, type="auto",
                    fact_count=facts, note_count=notes, is_latest=(i == 0))
        for i, d in enumerate(dates[:30])
    ]
    return BackupsData(
        schedule="ежедневно 03:00 UTC",
        storage="Google Drive (gdrive:Mira)",
        backups=entries,
    )
