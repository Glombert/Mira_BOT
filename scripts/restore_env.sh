#!/bin/bash
# restore_env.sh — скачивает зашифрованный .env с Google Drive и расшифровывает.
#
# Использование (на новом сервере):
#   BACKUP_PASSPHRASE='секретная_фраза' ./scripts/restore_env.sh
#
# Что нужно ДО запуска:
#   - установленный rclone с настроенным remote 'gdrive:'
#   - установленный gpg
#   - правильная BACKUP_PASSPHRASE
#
# Что произойдёт:
#   gdrive:Mira/secrets/env.gpg → /root/mira_agent/.env

set -euo pipefail

ENV_FILE="/root/mira_agent/.env"
REMOTE_PATH="gdrive:Mira/secrets"
ENCRYPTED_NAME="env.gpg"
TMP_FILE="/tmp/env.gpg.$$"

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    echo "[-] BACKUP_PASSPHRASE не задан"
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    echo "[!] $ENV_FILE уже существует. Переименуй его или удали — restore не перезапишет."
    exit 1
fi

# Скачиваем
rclone copyto "$REMOTE_PATH/$ENCRYPTED_NAME" "$TMP_FILE"

# Расшифровываем
gpg --batch --yes --quiet \
    --passphrase "$BACKUP_PASSPHRASE" \
    --decrypt \
    --output "$ENV_FILE" \
    "$TMP_FILE"

rm -f "$TMP_FILE"
chmod 600 "$ENV_FILE"

echo "[*] .env восстановлен: $ENV_FILE"
