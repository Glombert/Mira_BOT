"""tools/openrouter_tools.py — каталог моделей OpenRouter.

Зачем: чтобы Мира перестала придумывать id моделей по статьям-обзорам.
В каталоге openrouter.ai/api/v1/models всё реальное и актуальное, без auth.

Кеш на час — каталог меняется редко, нет смысла дёргать API на каждый
вызов. Лимит ответа — потому что 350+ моделей переполнят контекст.
"""

import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger("Ouroborus")

_CATALOG_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL   = 3600  # 1 час
_cache: dict = {"models": None, "fetched_at": 0.0}


def _fetch_catalog() -> list[dict]:
    """Достаёт полный каталог. Кешируется на час."""
    now = time.time()
    if _cache["models"] is not None and now - _cache["fetched_at"] < _CACHE_TTL:
        return _cache["models"]
    try:
        req = urllib.request.Request(
            _CATALOG_URL,
            headers={"User-Agent": "MiraBot/1.6"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        _cache["models"] = models
        _cache["fetched_at"] = now
        logger.info(f"openrouter_list_models: загружен каталог, {len(models)} моделей")
        return models
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning(f"openrouter_list_models: ошибка получения каталога: {e}")
        return []


def _output_modalities(model: dict) -> list[str]:
    """Унифицирует разные форматы поля output_modalities."""
    arch = model.get("architecture") or {}
    out = arch.get("output_modalities")
    if isinstance(out, list):
        return [m.lower() for m in out if m]
    # Старый формат: "text->image" в поле modality
    modality = arch.get("modality", "")
    if isinstance(modality, str) and "->" in modality:
        return [modality.split("->")[-1].strip().lower()]
    return []


def list_models(filter: str = "", capability: str = "", limit: int = 30) -> dict:
    """Возвращает модели OpenRouter с фильтром.

    filter     — подстрока в id или name (case-insensitive)
    capability — 'image', 'text', 'audio' — фильтр по output modality
    limit      — сколько вернуть (1-100, по умолчанию 30)
    """
    catalog = _fetch_catalog()
    if not catalog:
        return {"ok": False, "error": "Не удалось получить каталог OpenRouter."}

    f   = (filter or "").lower().strip()
    cap = (capability or "").lower().strip()
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 30

    matches = []
    for m in catalog:
        mid  = m.get("id", "")
        name = m.get("name", "")
        if f and f not in mid.lower() and f not in name.lower():
            continue
        if cap and cap not in _output_modalities(m):
            continue

        pricing = m.get("pricing") or {}
        arch    = m.get("architecture") or {}
        matches.append({
            "id":               mid,
            "name":             name,
            "context_length":   m.get("context_length", 0),
            "input_modalities":  arch.get("input_modalities")  or [],
            "output_modalities": _output_modalities(m),
            "prompt_price":     pricing.get("prompt", ""),
            "completion_price": pricing.get("completion", ""),
        })
        if len(matches) >= limit:
            break

    return {
        "ok": True,
        "count":             len(matches),
        "total_in_catalog":  len(catalog),
        "filter":            filter,
        "capability":        capability,
        "models":            matches,
    }


def _reset_cache() -> None:
    """Только для тестов."""
    _cache["models"] = None
    _cache["fetched_at"] = 0.0
