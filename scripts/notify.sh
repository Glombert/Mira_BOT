#!/bin/bash
# Отправляет уведомление владельцу в Telegram при падении mira-bot.
# Запускается через cron каждые 5 минут если сервис не активен.

ENV_FILE="/root/mira_agent/.env"
TOKEN=$(grep "^TELEGRAM_BOT_TOKEN" "$ENV_FILE" | cut -d= -f2)
OWNER=$(grep "^OWNER_TELEGRAM_ID"  "$ENV_FILE" | cut -d= -f2)

/root/mira_agent/venv/bin/python3 - <<PYEOF
import urllib.request, urllib.parse, subprocess
from datetime import datetime, timezone

token    = "$TOKEN"
chat_id  = "$OWNER"
time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

try:
    logs = subprocess.check_output(
        ['journalctl', '-u', 'mira-bot', '-n', '5', '--no-pager', '--output=cat'],
        text=True, stderr=subprocess.DEVNULL
    ).strip()
except Exception:
    logs = "(не удалось получить логи)"

text = (
    f"🔴 Мира упала\n"
    f"🕐 {time_str}\n"
    f"🖥 Сервер: fra-1-vm\n\n"
    f"Последние строки:\n{logs}\n\n"
    f"Команды:\n"
    f"  journalctl -u mira-bot -n 50\n"
    f"  systemctl restart mira-bot"
)

data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
urllib.request.urlopen(
    f"https://api.telegram.org/bot{token}/sendMessage", data=data
)
PYEOF
