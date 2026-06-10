"""tools/model_watch.py — слежение за каталогом моделей OpenRouter.

Гибридный ритуал agent_versions: скрипт сам считает дифф каталога между
запусками. Нет изменений — LLM не вызывается вовсе. Есть новые модели —
Мире уходит компактный дифф (а не весь каталог в 350+ моделей) на анализ.
"""

import json
import logging
import os

from tools.openrouter_tools import _fetch_catalog
from tools.paths import at_root

logger = logging.getLogger("Ouroboros")

SNAPSHOT_PATH = at_root("memory", "model_catalog.json")

# Вендоры, за которыми следим: текущие провайдеры Миры + флагманы рынка.
VENDORS = {"anthropic", "deepseek", "google", "openai", "x-ai", "meta-llama", "mistralai", "qwen"}


def _current_models() -> dict[str, str]:
    models = _fetch_catalog()
    return {
        m["id"]: (m.get("name") or m["id"])
        for m in models
        if isinstance(m.get("id"), str) and m["id"].split("/")[0] in VENDORS
    }


def _alpha_chain_summary() -> str:
    try:
        cfg = json.load(open(at_root("agents", "alpha.json"), encoding="utf-8"))
        return " → ".join(e.get("model", "?") for e in cfg.get("model_chain", []))
    except Exception:
        return "anthropic/claude-sonnet-4.6 → deepseek-v4-pro"


def model_catalog_diff() -> str | dict:
    """Handler ритуала agent_versions.

    Возвращает str (готовый отчёт, LLM не нужен) или
    {"llm_prompt": ...} — дифф для анализа Мирой.
    """
    current = _current_models()
    if not current:
        return "Каталог OpenRouter недоступен, дифф не посчитан.\n#IMPORTANCE: MINOR"

    prev: dict[str, str] | None = None
    if os.path.exists(SNAPSHOT_PATH):
        try:
            with open(SNAPSHOT_PATH, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception as e:
            logger.warning(f"model_watch: повреждённый снимок, пересоздаю: {e}")

    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1)

    if prev is None:
        return (f"Снимок каталога моделей создан: {len(current)} моделей "
                f"({', '.join(sorted(VENDORS))}). Дифф пойдёт со следующего запуска.\n"
                "#IMPORTANCE: NONE")

    added = sorted(set(current) - set(prev))
    removed = sorted(set(prev) - set(current))

    if not added and not removed:
        return "Новых моделей у отслеживаемых вендоров нет.\n#IMPORTANCE: NONE"

    lines = []
    if added:
        lines.append("Новые модели в каталоге OpenRouter:")
        lines.extend(f"+ {mid} ({current[mid]})" for mid in added)
    if removed:
        lines.append("Исчезли из каталога:")
        lines.extend(f"- {mid}" for mid in removed)
    diff_text = "\n".join(lines)

    prompt = (
        f"Селф-тест версий. Твоя цепочка моделей сейчас: {_alpha_chain_summary()}.\n"
        f"Скрипт сравнил каталог OpenRouter с прошлым запуском, вот дифф:\n\n{diff_text}\n\n"
        "Оцени по дифу: появилось ли что-то новее/способнее твоей текущей модели? "
        "Кратко скажи владельцу, какие из новинок интересны и почему. Конфиги не меняй — "
        "решение за владельцем. В конце строка #IMPORTANCE: NONE|MINOR|MAJOR|CRITICAL "
        "— MAJOR если вышла заметно более способная модель, чем текущая."
    )
    return {"llm_prompt": prompt}
