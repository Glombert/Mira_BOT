"""
tools/search_tools.py — веб-поиск через DuckDuckGo.

Не требует API-ключей. Используется Scout-агентом.
"""

import json
import logging

logger = logging.getLogger("Ouroborus")


def web_search(query: str, max_results: int = 5) -> dict:
    """
    Ищет в интернете через DuckDuckGo.

    Возвращает список результатов: title, href, body.
    max_results ограничен 10.
    """
    max_results = min(max(1, max_results), 10)
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return {"ok": True, "query": query, "results": [], "note": "Ничего не найдено"}
        formatted = [
            {
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "snippet": r.get("body", "")[:500],
            }
            for r in results
        ]
        return {"ok": True, "query": query, "results": formatted}
    except ImportError:
        return {"ok": False, "error": "Пакет ddgs не установлен. Запусти: pip install ddgs"}
    except Exception as e:
        logger.warning(f"web_search error: {e}")
        return {"ok": False, "error": str(e)}
