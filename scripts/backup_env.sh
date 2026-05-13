#!/bin/bash
# backup_env.sh — шифрует .env + credentials.json + token.json и грузит в Google Drive.
#
# Использование:
#   BACKUP_PASSPHRASE='секретная_фраза' ./scripts/backup_env.sh
#
# Куда уходит:
#   gdrive:Mira/secrets/secrets.tar.gpg
#
# Зачем: .env содержит MEMORY_ENCRYPTION_KEY (без него зашифрованные
# профили — мусор), credentials.json/token.json — OAuth Google.
# Это последняя линия обороны для восстановления Миры на новом сервере.

set -euo pipefail

MIRA_DIR="/root/mira_agent"
REMOTE_PATH="gdrive:Mira/secrets"
ENCRYPTED_NAME="secrets.tar.gpg"
TMP_TAR="/tmp/secrets.tar.$$"
TMP_GPG="/tmp/secrets.tar.gpg.$$"

cleanup() {
    rm -f "$TMP_TAR" "$TMP_GPG"
}
trap cleanup EXIT

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    echo "[-] BACKUP_PASSPHRASE не задан"
    exit 1
fi

cd "$MIRA_DIR"

FILES=()
for f in .env credentials.json token.json; do
    [ -f "$f" ] && FILES+=("$f")
done

if [ ${#FILES[@]} -eq 0 ]; then
    echo "[-] Нет файлов для бэкапа"
    exit 1
fi

tar -cf "$TMP_TAR" "${FILES[@]}"

gpg --batch --yes --quiet \
    --passphrase "$BACKUP_PASSPHRASE" \
    --symmetric --cipher-algo AES256 \
    --output "$TMP_GPG" \
    "$TMP_TAR"

rclone copyto "$TMP_GPG" "$REMOTE_PATH/$ENCRYPTED_NAME"

echo "[*] Зашифровано и загружено: $REMOTE_PATH/$ENCRYPTED_NAME"
echo "[*] Включены: ${FILES[*]}"
