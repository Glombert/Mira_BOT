"""
tools/search_tools.py — веб-поиск через DuckDuckGo.

Не требует API-ключей. Используется Scout-агентом.
"""

import json
import logging
import time

logger = logging.getLogger("Ouroborus")


def web_search(query: str, max_results: int = 5) -> dict:
    """
    Ищет в интернете через DuckDuckGo (бесплатно, без API-ключа).

    Возвращает список результатов: title, href, body.
    max_results ограничен 10.
    """
    max_results = min(max(1, int(max_results)), 10)
    t0 = time.time()
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=max_results))
        elapsed = time.time() - t0
        if not results:
            logger.info(f"web_search: '{query[:80]}' — ничего не найдено ({elapsed:.1f}s)")
            return {"ok": True, "query": query, "results": [], "note": "Ничего не найдено"}
        formatted = [
            {
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "snippet": r.get("body", "")[:500],
            }
            for r in results
        ]
        logger.info(f"web_search: '{query[:80]}' — {len(formatted)} результатов ({elapsed:.1f}s)")
        return {"ok": True, "query": query, "results": formatted}
    except ImportError:
        logger.warning("web_search: пакет 'ddgs' не установлен. Запусти: pip install ddgs")
        return {"ok": False, "error": "Пакет ddgs не установлен. Запусти: pip install ddgs"}
    except Exception as e:
        elapsed = time.time() - t0
        logger.warning(f"web_search error ({elapsed:.1f}s): {e}")
        return {"ok": False, "error": f"Ошибка поиска: {e}"}
