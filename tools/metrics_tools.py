"""
tools/metrics_tools.py — чтение метрик использования LLM.

Формат логов: memory/metrics/YYYY-MM-DD.jsonl (одна строка = один вызов API).
"""

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("Ouroborus")
METRICS_DIR = os.path.join("memory", "metrics")


def metrics_read(days: int = 1) -> dict:
    """
    Читает метрики использования LLM за последние N дней.

    Возвращает:
        ok, days — сколько дней данных
        total_calls — общее число вызовов
        total_tokens — суммарные токены (prompt + completion)
        cost_est — оценка стоимости (USD)
        by_model — разбивка по моделям
        by_user — разбивка по пользователям
        by_day — разбивка по дням
    """
    days = max(1, min(int(days), 90))
    cutoff = datetime.now() - timedelta(days=days)
    total_calls = 0
    total_prompt = 0
    total_completion = 0
    total_cost = 0.0
    by_model: dict[str, dict] = {}
    by_user: dict[str, dict] = {}
    by_day: dict[str, dict] = {}

    try:
        if not os.path.isdir(METRICS_DIR):
            return {"ok": True, "days": days, "total_calls": 0, "total_tokens": 0,
                    "cost_est": 0.0, "by_model": {}, "by_user": {}, "by_day": {},
                    "note": "Нет данных метрик"}

        for fname in sorted(os.listdir(METRICS_DIR)):
            if not fname.endswith(".jsonl"):
                continue
            file_date = fname.replace(".jsonl", "")
            try:
                file_dt = datetime.strptime(file_date, "%Y-%m-%d")
                if file_dt < cutoff:
                    continue
            except ValueError:
                continue

            path = os.path.join(METRICS_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    prompt_tok = e.get("prompt_tokens", 0) or 0
                    comp_tok   = e.get("completion_tokens", 0) or 0
                    cost       = e.get("cost_est", 0) or 0
                    model      = e.get("model", "unknown")
                    user       = e.get("user_id", "") or "system"

                    total_calls += 1
                    total_prompt += prompt_tok
                    total_completion += comp_tok
                    total_cost += cost

                    # По моделям
                    if model not in by_model:
                        by_model[model] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_est": 0.0}
                    by_model[model]["calls"] += 1
                    by_model[model]["prompt_tokens"] += prompt_tok
                    by_model[model]["completion_tokens"] += comp_tok
                    by_model[model]["cost_est"] += cost

                    # По пользователям
                    if user not in by_user:
                        by_user[user] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_est": 0.0}
                    by_user[user]["calls"] += 1
                    by_user[user]["prompt_tokens"] += prompt_tok
                    by_user[user]["completion_tokens"] += comp_tok
                    by_user[user]["cost_est"] += cost

                    # По дням
                    day = e.get("ts", "")[:10]
                    if day not in by_day:
                        by_day[day] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_est": 0.0}
                    by_day[day]["calls"] += 1
                    by_day[day]["prompt_tokens"] += prompt_tok
                    by_day[day]["completion_tokens"] += comp_tok
                    by_day[day]["cost_est"] += cost

    except Exception as ex:
        logger.error(f"metrics_read error: {ex}")
        return {"ok": False, "error": str(ex)}

    return {
        "ok": True,
        "days": days,
        "total_calls": total_calls,
        "total_tokens": total_prompt + total_completion,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "cost_est": round(total_cost, 4),
        "by_model": by_model,
        "by_user": by_user,
        "by_day": by_day,
    }
