#!/bin/bash
# restore_env.sh — скачивает зашифрованные секреты с Google Drive и распаковывает.
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
#   gdrive:Mira/secrets/secrets.tar.gpg →
#     /root/mira_agent/.env
#     /root/mira_agent/credentials.json (если был в бэкапе)
#     /root/mira_agent/token.json       (если был в бэкапе)

set -euo pipefail

MIRA_DIR="/root/mira_agent"
REMOTE_PATH="gdrive:Mira/secrets"
ENCRYPTED_NAME="secrets.tar.gpg"
TMP_GPG="/tmp/secrets.tar.gpg.$$"
TMP_TAR="/tmp/secrets.tar.$$"

cleanup() {
    rm -f "$TMP_GPG" "$TMP_TAR"
}
trap cleanup EXIT

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    echo "[-] BACKUP_PASSPHRASE не задан"
    exit 1
fi

if [ -f "$MIRA_DIR/.env" ]; then
    echo "[!] $MIRA_DIR/.env уже существует. Переименуй его или удали — restore не перезапишет."
    exit 1
fi

rclone copyto "$REMOTE_PATH/$ENCRYPTED_NAME" "$TMP_GPG"

gpg --batch --yes --quiet \
    --passphrase "$BACKUP_PASSPHRASE" \
    --decrypt \
    --output "$TMP_TAR" \
    "$TMP_GPG"

cd "$MIRA_DIR"
tar -xf "$TMP_TAR"

[ -f .env ]              && chmod 600 .env
[ -f credentials.json ]  && chmod 600 credentials.json
[ -f token.json ]        && chmod 600 token.json

echo "[*] Секреты восстановлены в $MIRA_DIR:"
tar -tf "$TMP_TAR" | sed 's/^/    /'
