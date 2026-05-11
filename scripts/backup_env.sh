#!/bin/bash
# backup_env.sh — шифрует .env и загружает в Google Drive.
#
# Использование:
#   BACKUP_PASSPHRASE='секретная_фраза' ./scripts/backup_env.sh
#
# Куда уходит:
#   gdrive:Mira/secrets/env.gpg
#
# Зачем: .env содержит MEMORY_ENCRYPTION_KEY — без него все
# зашифрованные профили и сессии превращаются в мусор.
# Этот файл — последняя линия обороны для восстановления Миры
# на новом сервере.

set -euo pipefail

ENV_FILE="/root/mira_agent/.env"
REMOTE_PATH="gdrive:Mira/secrets"
ENCRYPTED_NAME="env.gpg"
TMP_FILE="/tmp/env.gpg.$$"

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    echo "[-] BACKUP_PASSPHRASE не задан"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "[-] $ENV_FILE не найден"
    exit 1
fi

# Шифруем .env симметричным AES256
gpg --batch --yes --quiet \
    --passphrase "$BACKUP_PASSPHRASE" \
    --symmetric --cipher-algo AES256 \
    --output "$TMP_FILE" \
    "$ENV_FILE"

# Загружаем на Drive
rclone copyto "$TMP_FILE" "$REMOTE_PATH/$ENCRYPTED_NAME"
rm -f "$TMP_FILE"

echo "[*] .env зашифрован и загружен: $REMOTE_PATH/$ENCRYPTED_NAME"
