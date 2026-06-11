#!/bin/bash
# wg_add_peer.sh — добавить пользователя VPN (свой WireGuard-пир + конфиг + QR).
#
# Использование (на VPS с WireGuard):
#   scripts/wg_add_peer.sh "Имя устройства"
#
# Что делает:
#   1. Генерирует ключи и пресхаред-ключ.
#   2. Находит свободный IP в 10.66.66.0/24 (и fd42:42:42::/64).
#   3. Добавляет пира в /etc/wireguard/wg0.conf И в живой интерфейс (без рестарта).
#   4. Пишет клиентский конфиг в /root/wg-clients/<имя>.conf (+ QR, если есть qrencode).
#   5. Регистрирует имя в memory/vpn_peers.json — экран «VPN» покажет его по-человечески.
#
# Окружение:
#   WG_IFACE     — интерфейс (default wg0)
#   WG_ENDPOINT  — куда коннектится клиент (default 5.42.98.236:51820 — РУ-мост)

set -euo pipefail

NAME="${1:?Использование: wg_add_peer.sh \"Имя устройства\"}"
IFACE="${WG_IFACE:-wg0}"
ENDPOINT="${WG_ENDPOINT:-5.42.98.236:51820}"
CONF="/etc/wireguard/${IFACE}.conf"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CLIENTS_DIR="/root/wg-clients"
PEERS_JSON="$REPO/memory/vpn_peers.json"

[[ -f "$CONF" ]] || { echo "ERROR: $CONF не найден"; exit 1; }
command -v wg >/dev/null || { echo "ERROR: wireguard-tools не установлены"; exit 1; }

# 1. Ключи
PRIV=$(wg genkey)
PUB=$(echo "$PRIV" | wg pubkey)
PSK=$(wg genpsk)
SERVER_PUB=$(wg show "$IFACE" public-key)

# 2. Свободный IP: максимум занятого последнего октета + 1
LAST=$(grep -oE '10\.66\.66\.[0-9]+' "$CONF" | awk -F. '{print $4}' | sort -n | tail -1)
OCTET=$(( ${LAST:-1} + 1 ))
[[ $OCTET -lt 255 ]] || { echo "ERROR: пул 10.66.66.0/24 исчерпан"; exit 1; }
IP4="10.66.66.$OCTET"
IP6="fd42:42:42::$OCTET"

# 3. В конфиг сервера + в живой интерфейс
PSK_FILE=$(mktemp)
echo "$PSK" > "$PSK_FILE"
cat >> "$CONF" <<EOF

# --- $NAME (добавлен wg_add_peer.sh $(date +%F)) ---
[Peer]
PublicKey = $PUB
PresharedKey = $PSK
AllowedIPs = $IP4/32, $IP6/128
EOF
wg set "$IFACE" peer "$PUB" preshared-key "$PSK_FILE" allowed-ips "$IP4/32,$IP6/128"
rm -f "$PSK_FILE"

# 4. Клиентский конфиг
mkdir -p "$CLIENTS_DIR"
SAFE_NAME=$(echo "$NAME" | tr ' /' '__')
CLIENT_CONF="$CLIENTS_DIR/$SAFE_NAME.conf"
cat > "$CLIENT_CONF" <<EOF
[Interface]
PrivateKey = $PRIV
Address = $IP4/32, $IP6/128
DNS = 1.1.1.1, 1.0.0.1

[Peer]
PublicKey = $SERVER_PUB
PresharedKey = $PSK
Endpoint = $ENDPOINT
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
chmod 600 "$CLIENT_CONF"

# 5. Имя пира для экрана «VPN»
python3 - "$PEERS_JSON" "$PUB" "$NAME" <<'PYEOF'
import json, sys, os
path, pub, name = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
data[pub] = name
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
PYEOF

# Однострочная ссылка для вставки из буфера (Hiddify / NekoBox / v2rayNG).
# Официальный клиент WireGuard её не понимает — ему QR или файл .conf.
WG_URI=$(python3 - "$PRIV" "$SERVER_PUB" "$PSK" "$ENDPOINT" "$IP4" "$IP6" "$NAME" <<'PYEOF'
import sys
from urllib.parse import quote
priv, spub, psk, ep, ip4, ip6, name = sys.argv[1:8]
print(f"wireguard://{quote(priv, safe='')}@{ep}"
      f"?address={ip4}/32,{ip6}/128"
      f"&publickey={quote(spub, safe='')}"
      f"&presharedkey={quote(psk, safe='')}"
      f"&mtu=1420&keepalive=25#{quote(name)}")
PYEOF
)

echo "✓ Пир «$NAME» добавлен: $IP4"
echo
echo "── Для СМС/мессенджера (вставка из буфера в Hiddify/NekoBox/v2rayNG): ──"
echo "$WG_URI"
echo "─────────────────────────────────────────────────────────────────────"
echo
echo "  Файл конфига (для официального клиента WireGuard): $CLIENT_CONF"
if command -v qrencode >/dev/null; then
    echo "  QR для сканирования приложением WireGuard:"
    qrencode -t ansiutf8 < "$CLIENT_CONF"
else
    echo "  (поставь qrencode, чтобы получать QR: apt install qrencode)"
fi
