"""Инструмент генерации изображений через OpenRouter multimodal API."""

import os
import base64
import logging
from datetime import datetime

import httpx

logger = logging.getLogger("Ouroborus")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL  = "google/gemini-2.5-flash-image"
_TIMEOUT        = 60.0


def generate_image(
    user_id: str,
    prompt: str,
    model: str = _DEFAULT_MODEL,
) -> dict:
    """Генерирует изображение через OpenRouter multimodal API.

    Возвращает:
        {"ok": True,  "file": "image_TS.png", "size": N, "model": model, "text": "..."}
        {"ok": False, "error": "описание ошибки"}
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("API_OPENROUTER_KEY", "")
    if not api_key:
        return {"ok": False, "error": "OPENROUTER_API_KEY не задан в .env"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }

    try:
        resp = httpx.post(_OPENROUTER_URL, json=body, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        message   = data["choices"][0]["message"]
        image_url = message["images"][0]["image_url"]["url"]
        text      = message.get("content") or ""
    except (KeyError, IndexError) as e:
        return {"ok": False, "error": f"Неожиданная структура ответа API: {e}. Raw: {str(data)[:400]}"}

    try:
        _, b64_data = image_url.split(",", 1)
        img_bytes   = base64.b64decode(b64_data)
    except Exception as e:
        return {"ok": False, "error": f"Ошибка декодирования base64: {e}"}

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = f"image_{timestamp}.png"
    output_dir = os.path.join("workspace", user_id, "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path   = os.path.join(output_dir, filename)

    with open(out_path, "wb") as f:
        f.write(img_bytes)

    logger.info(f"generate_image: сохранено {out_path} ({len(img_bytes)} байт), model={model}")
    return {"ok": True, "file": filename, "size": len(img_bytes), "model": model, "text": text}
