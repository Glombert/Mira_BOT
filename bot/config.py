"""bot/config.py — конфигурация и логирование Telegram-слоя."""

import os
import logging
from logging.handlers import TimedRotatingFileHandler

TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_TG_ID  = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
MAX_HISTORY  = 20
MAX_MSG_LEN  = 4000   # Telegram ограничивает сообщения ~4096 символами

from tools.paths import at_root

os.makedirs(at_root("logs"), exist_ok=True)
# Отдельный файл для бота: agent.log принадлежит "Ouroboros" (см. agent.py),
# и тот логгер с propagate=False, поэтому записи не пересекаются.
_file_handler = TimedRotatingFileHandler(
    at_root("logs", "telegram_bot.log"),
    when="midnight",
    interval=1,
    backupCount=14,  # 2 недели — чтобы биweekly-ритуал log_audit видел весь период
    encoding="utf-8",
)
_file_handler.suffix = "%Y-%m-%d"
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger("MiraBot")
# Redaction filter — маскировка секретов в логах (ASVS V7.1)
from tools.redaction_filter import install as _install_redact
_install_redact()
from tools import observability as _observability
_observability.init("bot")

# Безопасность: httpx/httpcore логируют полный URL запроса на уровне INFO,
# а python-telegram-bot шлёт getUpdates на https://api.telegram.org/bot<TOKEN>/...
# → токен бота утекал в journald и файл-лог открытым текстом. Глушим до WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


_MIRA_PUBLIC_URL = os.getenv("MIRA_PUBLIC_URL", "https://mira-bot.duckdns.org")
