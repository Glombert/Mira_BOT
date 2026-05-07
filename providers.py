"""
providers.py — управление провайдерами и цепочками моделей.

PROVIDERS строится из .env:
    API_OPENROUTER_KEY=...
    API_OPENROUTER_URL=https://openrouter.ai/api/v1
    API_DEEPSEEK_KEY=...
    API_DEEPSEEK_URL=https://api.deepseek.com/v1

Каждый агент описывает model_chain в agents/*.json:
    [
      {"provider": "openrouter", "model": "anthropic/claude-sonnet-4-6", "temperature": 0.7},
      {"provider": "deepseek",   "model": "deepseek-chat",               "temperature": 0.7}
    ]

При вызове call() идём по цепочке, переключаемся при сбое, логируем.
"""

import os
import json
import logging
from datetime import datetime
from openai import OpenAI

logger = logging.getLogger("Ouroborus")
DECISIONS_LOG = os.path.join("memory", "decisions.log")

# Провайдеры: name → OpenAI client. Заполняется через init() после load_dotenv().
PROVIDERS: dict[str, OpenAI] = {}

# Ошибки в запросе — не переключаемся, сразу поднимаем.
_NON_RETRIABLE = (
    "context_length_exceeded",
    "invalid_request_error",
    "maximum context",
    "too many tokens",
)


# Провайдеры требующие дополнительных заголовков.
# Anthropic требует anthropic-version при обращении к их API напрямую.
_EXTRA_HEADERS: dict[str, dict] = {
    "anthropic": {"anthropic-version": "2023-06-01"},
}


def init() -> None:
    """
    Строит PROVIDERS из переменных окружения.
    Вызывается в agent.py один раз после load_dotenv().

    Формат .env:
        API_OPENROUTER_KEY=...   API_OPENROUTER_URL=https://openrouter.ai/api/v1
        API_ANTHROPIC_KEY=...    API_ANTHROPIC_URL=https://api.anthropic.com/v1
        API_DEEPSEEK_KEY=...     API_DEEPSEEK_URL=https://api.deepseek.com/v1
    """
    global PROVIDERS
    for key in os.environ:
        if not (key.startswith("API_") and key.endswith("_KEY")):
            continue
        name = key[4:-4].lower()          # API_ANTHROPIC_KEY → anthropic
        api_key = os.environ[key]
        base_url = os.getenv(f"API_{name.upper()}_URL")
        if api_key:
            try:
                extra = _EXTRA_HEADERS.get(name, {})
                PROVIDERS[name] = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers=extra,
                )
            except Exception as e:
                logger.warning(f"providers.init: не удалось создать клиент {name}: {e}")
    logger.info(f"providers: инициализированы {list(PROVIDERS.keys())}")


def _log_switch(from_entry: dict, to_entry: dict, reason: str) -> None:
    """Записывает переключение провайдера в decisions.log."""
    os.makedirs("memory", exist_ok=True)
    entry = {
        "ts":     datetime.now().isoformat(),
        "event":  "provider_switch",
        "from":   f"{from_entry.get('provider')}/{from_entry.get('model')}",
        "to":     f"{to_entry.get('provider')}/{to_entry.get('model')}",
        "reason": str(reason)[:300],
    }
    try:
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"providers: не удалось записать в decisions.log: {e}")


def _apply_prompt_caching(messages: list, provider: str, model: str) -> list:
    """
    Добавляет cache_control к системному сообщению для Anthropic-моделей
    через OpenRouter (согласно docs.openrouter.ai/docs/prompt-caching).

    Работает только для: provider=="openrouter" И model начинается с "anthropic/".
    Для остальных провайдеров возвращает оригинальный список без изменений.

    OpenRouter пробрасывает cache_control напрямую в Anthropic API.
    Минимальный размер кешируемого блока — 1024 токена (Claude 3.5+).
    Системный промпт с персоной и принципами обычно превышает этот порог.
    """
    if not (provider == "openrouter" and model.startswith("anthropic/")):
        return messages

    result = []
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            # Конвертируем строку в блочный формат с cache_control
            result.append({
                "role": "system",
                "content": [{
                    "type": "text",
                    "text": msg["content"],
                    "cache_control": {"type": "ephemeral"},
                }],
            })
        else:
            result.append(msg)
    return result


def call(model_chain: list[dict], messages: list, **kwargs) -> object:
    """
    Вызывает API, идя по цепочке при сбоях провайдера.

    model_chain — список:
        [{"provider": "openrouter", "model": "...", "temperature": 0.7}, ...]

    Возвращает объект ответа openai.
    Поднимает исключение если все провайдеры исчерпаны.
    """
    if not model_chain:
        raise ValueError("model_chain пуст")

    # Температура может быть в kwargs (устаревший способ) или в каждом entry.
    default_temperature = kwargs.pop("temperature", 0.7)
    last_error: Exception | None = None

    for i, entry in enumerate(model_chain):
        provider_name = entry.get("provider", "")
        model = entry.get("model", "")
        temperature = entry.get("temperature", default_temperature)

        client = PROVIDERS.get(provider_name)
        if not client:
            logger.warning(f"providers.call: '{provider_name}' не настроен, пропускаю.")
            continue

        try:
            cached_messages = _apply_prompt_caching(messages, provider_name, model)
            return client.chat.completions.create(
                model=model,
                messages=cached_messages,
                temperature=temperature,
                **kwargs,
            )

        except Exception as e:
            last_error = e
            err_str = str(e).lower()

            # Проблема в запросе, а не в провайдере — сразу поднимаем.
            if any(k in err_str for k in _NON_RETRIABLE):
                raise

            if i + 1 < len(model_chain):
                next_entry = model_chain[i + 1]
                logger.warning(
                    f"providers.call: {provider_name}/{model} упал ({e}). "
                    f"Переключаюсь на {next_entry.get('provider')}/{next_entry.get('model')}"
                )
                print(f"[!] {provider_name} недоступен, переключаюсь на резерв...")
                _log_switch(entry, next_entry, str(e))
            else:
                logger.error(f"providers.call: все провайдеры исчерпаны. Ошибка: {e}")

    if last_error:
        raise last_error
    raise RuntimeError("model_chain пуст или ни один провайдер не настроен.")


def first_client() -> OpenAI | None:
    """Возвращает первый доступный клиент. Для обратной совместимости."""
    return next(iter(PROVIDERS.values()), None)


def first_model_name() -> str:
    """Возвращает ключ первого провайдера. Для обратной совместимости."""
    return next(iter(PROVIDERS.keys()), "")
