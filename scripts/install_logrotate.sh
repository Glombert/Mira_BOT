#!/bin/bash
# install_logrotate.sh — копирует logrotate-конфиги в /etc/logrotate.d/
# Запускать от root на VPS однократно (и после изменений конфигов).
#
#   sudo ./scripts/install_logrotate.sh

set -euo pipefail
SRC="$(cd "$(dirname "$0")/logrotate.d" && pwd)"
DST="/etc/logrotate.d"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "✗ Запусти от root" >&2
    exit 1
fi

for f in "$SRC"/*; do
    name=$(basename "$f")
    cp -v "$f" "$DST/$name"
    chmod 644 "$DST/$name"
done

echo "→ Проверка конфигов:"
logrotate -d "$DST/mira-smoke" 2>&1 | tail -5
echo ""
echo "✓ Установлено. logrotate (cron.daily) подхватит автоматически."
echo "  Принудительно: logrotate -f /etc/logrotate.d/mira-smoke"
