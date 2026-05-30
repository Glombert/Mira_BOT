"""tools/observability.py — опциональная отправка ошибок в Sentry.

Без переменной окружения SENTRY_DSN — полный no-op: пакет sentry_sdk даже не
импортируется, жёсткой зависимости нет, пока ты сам не включишь. Когда DSN
задан — ошибки из бота и веба летят в Sentry, секреты вычищаются before_send
(той же логикой, что и в логах — tools/redaction_filter.redact).

Включить:
    pip install sentry-sdk
    в .env:  SENTRY_DSN=https://...ingest.sentry.io/...
    (необязательно) MIRA_ENV=prod|dev, MIRA_RELEASE=<версия>

Вызывается один раз при старте: init("bot") в telegram_bot.py, init("web") в web/app.py.
"""

import os
import logging

logger = logging.getLogger("Ouroboros")

_initialized = False


def _scrub(event: dict, hint: dict) -> dict:
    """before_send: маскирует секреты в сообщении и значениях исключений."""
    from tools.redaction_filter import redact

    try:
        msg = event.get("logentry", {}).get("message")
        if isinstance(msg, str):
            event["logentry"]["message"] = redact(msg)

        for exc in event.get("exception", {}).get("values", []):
            val = exc.get("value")
            if isinstance(val, str):
                exc["value"] = redact(val)
    except Exception:
        pass  # скраб не должен ронять отправку события
    return event


def init(component: str) -> bool:
    """Инициализирует Sentry, если задан SENTRY_DSN. Возвращает True если включён."""
    global _initialized
    if _initialized:
        return True

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "observability: SENTRY_DSN задан, но sentry-sdk не установлен. "
            "Запусти: pip install sentry-sdk"
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("MIRA_ENV", "prod"),
        release=os.getenv("MIRA_RELEASE") or None,
        # Только ошибки, без перф-трейсинга — экономно для маленького VPS.
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=_scrub,
    )
    sentry_sdk.set_tag("component", component)
    _initialized = True
    logger.info(f"observability: Sentry включён (component={component})")
    return True
