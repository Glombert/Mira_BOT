"""
providers.py — управление провайдерами и цепочками моделей.

Поддерживает два типа провайдеров:
  - OpenAI-совместимые (OpenRouter, DeepSeek, OpenAI) — через openai.OpenAI
  - Anthropic native (прямой API) — через anthropic.Anthropic SDK

PROVIDERS строится из .env:
    API_OPENROUTER_KEY=...   API_OPENROUTER_URL=https://openrouter.ai/api/v1
    API_ANTHROPIC_KEY=...    (URL не нужен — SDK знает адрес сам)
    API_DEEPSEEK_KEY=...     API_DEEPSEEK_URL=https://api.deepseek.com/v1

Каждый агент описывает model_chain в agents/*.json:
    [
      {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6", "temperature": 0.7},
      {"provider": "anthropic",  "model": "claude-opus-4-7",             "temperature": 0.2}
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

# OpenAI-совместимые провайдеры: name → OpenAI client
PROVIDERS: dict[str, OpenAI] = {}

# Нативный Anthropic клиент (инициализируется отдельно)
_anthropic_client = None

# Ошибки в запросе — не переключаемся, сразу поднимаем.
_NON_RETRIABLE = (
    "context_length_exceeded",
    "invalid_request_error",
    "maximum context",
    "too many tokens",
)


# ---------------------------------------------------------------------------
# Адаптер Anthropic → OpenAI-совместимый ответ
# ---------------------------------------------------------------------------

class _AnthropicResponseAdapter:
    """
    Оборачивает anthropic.Message чтобы снаружи выглядело как openai.ChatCompletion.
    Код в agent.py и conclave.py обращается к response.choices[0].message.content —
    адаптер делает этот интерфейс рабочим.

    Ограничение: tool_calls не адаптируются — прямой Anthropic используется как
    текстовый fallback когда OpenRouter недоступен. Инструменты работают через OpenRouter.
    """
    class _Message:
        def __init__(self, content: str):
            self.content    = content
            self.tool_calls = None

    class _Choice:
        def __init__(self, content: str):
            self.message = _AnthropicResponseAdapter._Message(content)

    def __init__(self, anthropic_msg):
        text = ""
        for block in (anthropic_msg.content or []):
            if hasattr(block, "text"):
                text += block.text
        self.choices = [self._Choice(text)]


# ---------------------------------------------------------------------------
# Инициализация
# ---------------------------------------------------------------------------

def init() -> None:
    """
    Строит PROVIDERS из переменных окружения.
    Вызывается в agent.py один раз после load_dotenv().

    Для провайдера 'anthropic' создаёт нативный Anthropic SDK клиент.
    URL не нужен — SDK знает адрес сам (https://api.anthropic.com).
    """
    global _anthropic_client

    for key in os.environ:
        if not (key.startswith("API_") and key.endswith("_KEY")):
            continue
        name    = key[4:-4].lower()           # API_ANTHROPIC_KEY → anthropic
        api_key = os.environ[key]
        if not api_key:
            continue

        if name == "anthropic":
            # Нативный Anthropic SDK — не OpenAI-совместимый
            try:
                import anthropic as _ant
                _anthropic_client = _ant.Anthropic(api_key=api_key)
                logger.info("providers: anthropic (native SDK) инициализирован")
            except ImportError:
                logger.warning(
                    "providers: пакет 'anthropic' не установлен. "
                    "Запусти: pip install anthropic"
                )
            except Exception as e:
                logger.warning(f"providers: не удалось создать anthropic клиент: {e}")
        else:
            # OpenAI-совместимые провайдеры
            base_url = os.getenv(f"API_{name.upper()}_URL")
            try:
                PROVIDERS[name] = OpenAI(api_key=api_key, base_url=base_url)
            except Exception as e:
                logger.warning(f"providers.init: не удалось создать клиент {name}: {e}")

    logger.info(f"providers: инициализированы {list(PROVIDERS.keys())}"
                + (" + anthropic(native)" if _anthropic_client else ""))


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _log_switch(from_entry: dict, to_entry: dict, reason: str) -> None:
    """Записывает переключение провайдера в decisions.log и уведомляет владельца."""
    os.makedirs("memory", exist_ok=True)
    from_str = f"{from_entry.get('provider')}/{from_entry.get('model')}"
    to_str   = f"{to_entry.get('provider')}/{to_entry.get('model')}"
    entry = {
        "ts":     datetime.now().isoformat(),
        "event":  "provider_switch",
        "from":   from_str,
        "to":     to_str,
        "reason": str(reason)[:300],
    }
    try:
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"providers: не удалось записать в decisions.log: {e}")

    # Уведомление в Telegram — отправляем в фоне чтобы не задерживать ответ
    import threading
    threading.Thread(
        target=_notify_switch,
        args=(from_str, to_str, str(reason)[:300]),
        daemon=True,
    ).start()


def _notify_switch(from_str: str, to_str: str, reason: str) -> None:
    """Отправляет Telegram-уведомление о переключении провайдера."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner = os.getenv("OWNER_TELEGRAM_ID", "")
    if not token or not owner:
        return
    try:
        import urllib.request, urllib.parse
        text = (
            f"⚡ Смена модели\n"
            f"От: {from_str}\n"
            f"На: {to_str}\n"
            f"Причина: {reason[:200]}"
        )
        data = urllib.parse.urlencode({"chat_id": owner, "text": text}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=5,
        )
    except Exception:
        pass  # Не блокируем основной поток


def _apply_prompt_caching(messages: list, provider: str, model: str) -> list:
    """
    Добавляет cache_control к системному сообщению для Claude через OpenRouter.
    Для остальных провайдеров возвращает список без изменений.
    """
    if not (provider == "openrouter" and model.startswith("anthropic/")):
        return messages

    result = []
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
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


def _call_anthropic_native(model: str, messages: list, temperature: float,
                           max_tokens: int) -> _AnthropicResponseAdapter:
    """
    Вызывает Anthropic API через нативный SDK.
    Конвертирует messages из OpenAI-формата в Anthropic-формат:
      - system-сообщение выносится в отдельный параметр
      - tool-сообщения фильтруются (Anthropic fallback — только текст)
    """
    system = ""
    ant_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""

        if role == "system":
            if isinstance(content, list):
                # Может быть блочный формат (prompt caching)
                system = " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            else:
                system = content
        elif role in ("user", "assistant"):
            if isinstance(content, str) and content:
                ant_messages.append({"role": role, "content": content})
        # tool-сообщения пропускаем — в fallback-режиме инструменты не нужны

    # Anthropic требует чтобы первое сообщение было от user
    if not ant_messages or ant_messages[0]["role"] != "user":
        ant_messages.insert(0, {"role": "user", "content": "(продолжи)"})

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        messages=ant_messages,
        temperature=temperature,
    )
    if system:
        kwargs["system"] = system

    response = _anthropic_client.messages.create(**kwargs)
    return _AnthropicResponseAdapter(response)


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

def call(model_chain: list[dict], messages: list, **kwargs) -> object:
    """
    Вызывает API, идя по цепочке при сбоях провайдера.

    Поддерживает два типа провайдеров:
      - OpenAI-совместимые (openrouter, deepseek, openai, ...) — через PROVIDERS
      - "anthropic" — через нативный SDK (_anthropic_client)

    При "anthropic"-провайдере tools игнорируются (только текстовый fallback).
    Возвращает объект с интерфейсом response.choices[0].message.content.
    """
    if not model_chain:
        raise ValueError("model_chain пуст")

    default_temperature = kwargs.pop("temperature", 0.7)
    last_error: Exception | None = None

    for i, entry in enumerate(model_chain):
        provider_name = entry.get("provider", "")
        model         = entry.get("model", "")
        temperature   = entry.get("temperature", default_temperature)

        try:
            if provider_name == "anthropic":
                # Нативный Anthropic SDK
                if _anthropic_client is None:
                    logger.warning("providers.call: anthropic клиент не инициализирован, пропускаю.")
                    continue
                max_tokens = kwargs.get("max_tokens", 4096)
                return _call_anthropic_native(model, messages, temperature, max_tokens)

            else:
                # OpenAI-совместимый провайдер
                client = PROVIDERS.get(provider_name)
                if not client:
                    logger.warning(f"providers.call: '{provider_name}' не настроен, пропускаю.")
                    continue
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
    """Возвращает первый OpenAI-совместимый клиент. Для обратной совместимости."""
    return next(iter(PROVIDERS.values()), None)


def first_model_name() -> str:
    """Возвращает ключ первого провайдера. Для обратной совместимости."""
    return next(iter(PROVIDERS.keys()), "")
