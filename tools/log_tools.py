"""tools/log_tools.py — чтение логов для ритуала log_audit.

Логи пишутся в logs/*.log (+ ротированные logs/*.log.YYYY-MM-DD,
TimedRotatingFileHandler в telegram_bot.py и web/app.py).

read_logs даёт ОГРАНИЧЕННЫЙ дайджест ошибок: группирует похожие строки в
«сигнатуры» (убирая таймстемпы/id/пути/числа) и возвращает топ по частоте.
Смысл — чтобы агент видел ПОВТОРЯЮЩИЕСЯ проблемы, а не тонул в полном логе.
Только чтение, объём ограничен.
"""

import os
import re
import glob
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("Ouroboros")
LOGS_DIR = "logs"

_ERROR_RE = re.compile(r"\b(ERROR|CRITICAL|Traceback|Exception)\b", re.IGNORECASE)
_ERROR_WARN_RE = re.compile(r"\b(ERROR|CRITICAL|Traceback|Exception|WARNING|WARN)\b", re.IGNORECASE)

# Нормализация строки в «сигнатуру» для группировки повторов: вырезаем
# изменчивое (время, id, hex, пути, голые числа) — остаётся суть ошибки.
_NORM = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d*"), "<ts>"),
    (re.compile(r"tg_\d+"), "<id>"),
    (re.compile(r"\b\d{4,}\b"), "<id>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<hex>"),
    (re.compile(r"(/[^\s:]+)+"), "<path>"),
    (re.compile(r"\b\d+\b"), "<n>"),
]


def read_logs(days: int = 14, include_warnings: bool = False, max_groups: int = 25) -> dict:
    """Дайджест ошибок из logs/ за последние N дней, сгруппированный по частоте.

    days: за сколько дней (1-30). include_warnings: включать WARNING.
    Возвращает: files_scanned, total_matched, unique_groups, groups[{count,sample}].
    """
    days = max(1, min(int(days), 30))
    cutoff = datetime.now() - timedelta(days=days)
    rx = _ERROR_WARN_RE if include_warnings else _ERROR_RE

    paths = sorted(glob.glob(os.path.join(LOGS_DIR, "*.log*")))
    if not paths:
        return {"ok": True, "days": days, "total_matched": 0, "unique_groups": 0,
                "groups": [], "note": "Логи не найдены (logs/ пуст)"}

    groups: dict[str, dict] = {}
    files_scanned: list[str] = []
    total_matched = 0

    for path in paths:
        try:
            if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                continue
            files_scanned.append(os.path.basename(path))
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not rx.search(line):
                        continue
                    total_matched += 1
                    sig = line.strip()
                    for pat, repl in _NORM:
                        sig = pat.sub(repl, sig)
                    sig = sig[:200]
                    g = groups.get(sig)
                    if g:
                        g["count"] += 1
                    else:
                        groups[sig] = {"count": 1, "sample": line.strip()[:300]}
        except Exception as ex:
            logger.warning(f"read_logs: {path}: {ex}")

    top = sorted(groups.values(), key=lambda v: v["count"], reverse=True)[:max_groups]
    return {
        "ok": True,
        "days": days,
        "files_scanned": files_scanned,
        "total_matched": total_matched,
        "unique_groups": len(groups),
        "groups": [{"count": v["count"], "sample": v["sample"]} for v in top],
    }
