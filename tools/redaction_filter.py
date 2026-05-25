"""tools/redaction_filter.py — logging.Filter для маскировки секретов.

Подключается к корневому логгеру в telegram_bot.py и web/app.py.
Маскирует: sk-..., github_pat_..., bot-токены Telegram, Fernet-ключи,
token=... в query-строках.

ASVS V7.1 — defense in depth: если где-то случайно залогируем секрет,
фильтр его замаскирует до того как он уйдёт в файл / journald.
"""

import re
import logging

# Паттерны: (regex, replacement)
_PATTERNS = [
    # OpenAI/DeepSeek/OpenRouter: sk-... и sk-or-...
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "sk-***REDACTED***"),
    # GitHub PAT: github_pat_...
    (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "github_pat_***REDACTED***"),
    # Anthropic: sk-ant-...
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "sk-ant-***REDACTED***"),
    # Telegram bot token в URL: bot<digits>:<alphanum>
    (re.compile(r"bot\d+:[a-zA-Z0-9_-]{30,}"), "bot***REDACTED***"),
    # Fernet-ключи: gAAAA... base64
    (re.compile(r"gAAAA[A-Za-z0-9+/=_-]{40,}"), "gAAAA***REDACTED***"),
    # token=... в query-строках (сессионные токены)
    (re.compile(r"(token=)[^&\s]{10,}"), r"\1***REDACTED***"),
    # session=... в query-строках
    (re.compile(r"(session=)[^&\s]{10,}"), r"\1***REDACTED***"),
    # Authorization: Bearer ...
    (re.compile(r"(Authorization.*?Bearer\s+)[^\s,]+"), r"\1***REDACTED***"),
]


class SecretRedactionFilter(logging.Filter):
    """Маскирует известные паттерны секретов в log-сообщениях."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in _PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()  # сбрасываем args чтобы избежать повторного форматирования
        return True


def install() -> None:
    """Подключает фильтр к корневому логгеру (один раз, идемпотентно)."""
    root = logging.getLogger()
    # Проверяем, не установлен ли уже
    if any(isinstance(f, SecretRedactionFilter) for f in root.filters):
        return
    root.addFilter(SecretRedactionFilter())
