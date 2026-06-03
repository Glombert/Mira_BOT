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
import time
import threading
import logging
from datetime import datetime
from openai import OpenAI

logger = logging.getLogger("Ouroboros")
DECISIONS_LOG = os.path.join("memory", "decisions.log")
METRICS_DIR = os.path.join("memory", "metrics")

# Цены моделей (USD за 1M токенов): (input_price, output_price)
# Приблизительные, май 2026. Для расчёта ~стоимости, не точной бухгалтерии.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "anthropic/claude-sonnet-4.6":     (3.00, 15.00),
    "anthropic/claude-opus-4.7":      (15.00, 75.00),
    "anthropic/claude-haiku-4.5":     (0.80, 4.00),
    "deepseek/deepseek-v4-pro":       (0.50, 2.00),
    "deepseek/deepseek-chat":         (0.14, 0.28),
    "deepseek/deepseek-v4-flash":     (0.10, 0.20),
    "google/gemini-flash-1.5":        (0.075, 0.30),
    "google/gemini-3.1-pro-preview":  (1.25, 5.00),
    "perplexity/sonar":               (1.00, 5.00),
    "perplexity/sonar-pro":           (3.00, 15.00),
    "claude-sonnet-4.6":              (3.00, 15.00),
    "claude-opus-4.7":               (15.00, 75.00),
    "claude-haiku-4.5":              (0.80, 4.00),
    "deepseek-chat":                  (0.14, 0.28),
    "gemini-flash-1.5":               (0.075, 0.30),
}

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
    class _Usage:
        def __init__(self, input_tokens: int = 0, output_tokens: int = 0):
            self.prompt_tokens     = input_tokens
            self.completion_tokens = output_tokens
            self.total_tokens      = input_tokens + output_tokens

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
        # Извлекаем usage если есть (Anthropic SDK возвращает .usage с input_tokens/output_tokens)
        try:
            u = anthropic_msg.usage
            self.usage = self._Usage(u.input_tokens, u.output_tokens)
        except Exception:
            self.usage = None


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
            if not base_url:
                logger.warning(
                    f"providers.init: для '{name}' не задан API_{name.upper()}_URL. "
                    f"OpenAI-клиент будет использовать api.openai.com по умолчанию."
                )
            try:
                PROVIDERS[name] = OpenAI(api_key=api_key, base_url=base_url)
                logger.info(f"providers.init: клиент '{name}' создан (base_url={base_url or 'default'})")
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
    threading.Thread(
        target=_notify_switch,
        args=(from_str, to_str, str(reason)[:300]),
        daemon=True,
    ).start()


_metrics_lock = threading.Lock()


def _log_metrics(user_id: str, agent_name: str, provider: str, model: str,
                 prompt_tokens: int, completion_tokens: int, latency_ms: float) -> None:
    """Записывает вызов LLM в memory/metrics/YYYY-MM-DD.jsonl (thread-safe)."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(METRICS_DIR, exist_ok=True)
        path = os.path.join(METRICS_DIR, f"{today}.jsonl")

        # Оценка стоимости
        input_price, output_price = MODEL_PRICES.get(model, (0, 0))
        cost = (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price

        entry = {
            "ts": datetime.now().isoformat(),
            "user_id": user_id or "",
            "agent": agent_name or "",
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 1),
            "cost_est": round(cost, 6),
        }
        with _metrics_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"providers: не удалось записать метрики: {e}")


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


DYNAMIC_MARKER = "<<MIRA_DYNAMIC>>"


def _apply_prompt_caching(messages: list, provider: str, model: str) -> list:
    """
    Добавляет cache_control к системному сообщению для Claude через OpenRouter.
    Разделяет system по маркеру DYNAMIC_MARKER на две части:
      static (характер + регламент) — попадает в кэш
      dynamic (время, summary, augments) — НЕ кэшируется
    Без маркера — кэширует всё (legacy).
    """
    if not (provider == "openrouter" and model.startswith("anthropic/")):
        return messages

    result = []
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            content = msg["content"]
            if DYNAMIC_MARKER in content:
                static, dynamic = content.split(DYNAMIC_MARKER, 1)
                static = static.rstrip()
                dynamic = dynamic.lstrip()
                blocks: list = [{
                    "type": "text",
                    "text": static,
                    "cache_control": {"type": "ephemeral"},
                }]
                if dynamic:
                    blocks.append({"type": "text", "text": dynamic})
            else:
                blocks = [{
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }]
            result.append({"role": "system", "content": blocks})
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

# Потолок одновременных LLM-вызовов на процесс. Защищает маленький VPS (на нём
# ещё VPN) от шторма: при 10 пользователях не даём 10 турам жечь память/деньги
# разом — лишние ждут своей очереди. agent.run крутится в asyncio.to_thread,
# поэтому threading.Semaphore блокирует рабочий поток, а не event loop.
_MAX_CONCURRENT_LLM = int(os.getenv("MIRA_MAX_CONCURRENT_LLM", "6"))
_llm_semaphore = threading.Semaphore(_MAX_CONCURRENT_LLM)


def call(model_chain: list[dict], messages: list, **kwargs) -> object:
    """Публичная точка вызова LLM. Ограничивает одновременность семафором,
    затем делегирует в _call_impl (цепочка провайдеров с fallback)."""
    with _llm_semaphore:
        return _call_impl(model_chain, messages, **kwargs)


def _call_impl(model_chain: list[dict], messages: list, **kwargs) -> object:
    """
    Вызывает API, идя по цепочке при сбоях провайдера.

    Поддерживает два типа провайдеров:
      - OpenAI-совместимые (openrouter, deepseek, openai, ...) — через PROVIDERS
      - "anthropic" — через нативный SDK (_anthropic_client)

    При "anthropic"-провайдере tools игнорируются (только текстовый fallback).
    Возвращает объект с интерфейсом response.choices[0].message.content.

    Необязательные kwargs:
      - user_id: str — для метрик (кто вызвал)
      - agent_name: str — для метрик (какой агент)
    """
    if not model_chain:
        raise ValueError("model_chain пуст")

    # Извлекаем метаданные для метрик (не передаём в API)
    metric_user_id = kwargs.pop("user_id", "")
    metric_agent   = kwargs.pop("agent_name", "")

    default_temperature = kwargs.pop("temperature", 0.7)
    last_error: Exception | None = None
    t_start = time.time()

    logger.debug(f"providers.call: начало, chain={[(e.get('provider'), e.get('model')) for e in model_chain]}, messages={len(messages)}")

    for i, entry in enumerate(model_chain):
        provider_name = entry.get("provider", "")
        model         = entry.get("model", "")
        temperature   = entry.get("temperature", default_temperature)
        t_call = time.time()

        try:
            if provider_name == "anthropic":
                # Нативный Anthropic SDK
                if _anthropic_client is None:
                    logger.warning("providers.call: anthropic клиент не инициализирован, пропускаю.")
                    continue
                max_tokens = kwargs.get("max_tokens", 4096)
                logger.info(f"providers.call [{i+1}/{len(model_chain)}]: anthropic/{model} (temp={temperature}, msgs={len(messages)})")
                result = _call_anthropic_native(model, messages, temperature, max_tokens)
                dt = time.time() - t_call
                logger.info(f"providers.call [{i+1}/{len(model_chain)}]: anthropic/{model} OK ({dt:.1f}s, ответ={len(result.choices[0].message.content or '')} символов)")
                # Метрики
                if result.usage:
                    _log_metrics(metric_user_id, metric_agent, provider_name, model,
                                 result.usage.prompt_tokens, result.usage.completion_tokens, dt * 1000)
                return result

            else:
                # OpenAI-совместимый провайдер
                client = PROVIDERS.get(provider_name)
                if not client:
                    logger.warning(f"providers.call: '{provider_name}' не настроен, пропускаю.")
                    continue
                cached_messages = _apply_prompt_caching(messages, provider_name, model)
                logger.info(f"providers.call [{i+1}/{len(model_chain)}]: {provider_name}/{model} (temp={temperature}, msgs={len(messages)})")
                result = client.chat.completions.create(
                    model=model,
                    messages=cached_messages,
                    temperature=temperature,
                    **kwargs,
                )
                dt = time.time() - t_call
                if not getattr(result, "choices", None):
                    # OpenRouter иногда отдаёт 200 с choices=null + error в теле,
                    # когда upstream-провайдер (Claude через Vertex) моргнул.
                    # Бросаем понятную ошибку → failover с осмысленной причиной.
                    err = getattr(result, "error", None) or "пустой ответ (choices=null)"
                    raise RuntimeError(f"{provider_name}/{model}: {err}")
                has_tools = bool(getattr(result.choices[0].message, 'tool_calls', None))
                # Пустой content без tool_calls (например, сработал content-filter
                # провайдера) — не валидный ответ. Делаем failover на следующего,
                # а не отдаём пользователю пустоту.
                if not (result.choices[0].message.content or "").strip() and not has_tools:
                    raise RuntimeError(f"{provider_name}/{model}: пустой content без tool_calls")
                logger.info(f"providers.call [{i+1}/{len(model_chain)}]: {provider_name}/{model} OK ({dt:.1f}s, ответ={len(result.choices[0].message.content or '')} символов, tool_calls={has_tools})")
                # Метрики
                if getattr(result, 'usage', None):
                    u = result.usage
                    _log_metrics(metric_user_id, metric_agent, provider_name, model,
                                 u.prompt_tokens or 0, u.completion_tokens or 0, dt * 1000)
                return result

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            dt = time.time() - t_call

            if any(k in err_str for k in _NON_RETRIABLE):
                logger.error(f"providers.call [{i+1}/{len(model_chain)}]: {provider_name}/{model} невосстановимая ошибка ({dt:.1f}s): {e}")
                raise

            if i + 1 < len(model_chain):
                next_entry = model_chain[i + 1]
                logger.warning(
                    f"providers.call [{i+1}/{len(model_chain)}]: {provider_name}/{model} упал ({dt:.1f}s). "
                    f"Переключаюсь на {next_entry.get('provider')}/{next_entry.get('model')}: {e}"
                )
                print(f"[!] {provider_name} недоступен, переключаюсь на резерв...")
                _log_switch(entry, next_entry, str(e))
            else:
                logger.error(f"providers.call: все провайдеры исчерпаны ({time.time()-t_start:.1f}s total). Ошибка: {e}")

    if last_error:
        raise last_error
    raise RuntimeError("model_chain пуст или ни один провайдер не настроен.")


def first_client() -> OpenAI | None:
    """Возвращает первый OpenAI-совместимый клиент. Для обратной совместимости."""
    return next(iter(PROVIDERS.values()), None)


def first_model_name() -> str:
    """Возвращает ключ первого провайдера. Для обратной совместимости."""
    return next(iter(PROVIDERS.keys()), "")
