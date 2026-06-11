#!/bin/bash
# wg_remove_peer.sh — удалить пользователя WireGuard.
#
# Использование (на VPS с WireGuard):
#   scripts/wg_remove_peer.sh "Имя устройства"
#
# Находит пира по имени (memory/vpn_peers.json → pubkey), убирает его из
# живого интерфейса (wg set ... remove), из wg0.conf и из vpn_peers.json,
# удаляет клиентский конфиг.
#
# Окружение: WG_IFACE (default wg0).

set -euo pipefail

NAME="${1:?Использование: wg_remove_peer.sh \"Имя устройства\"}"
IFACE="${WG_IFACE:-wg0}"
CONF="/etc/wireguard/${IFACE}.conf"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PEERS_JSON="$REPO/memory/vpn_peers.json"
CLIENTS_DIR="/root/wg-clients"

[[ -f "$CONF" ]] || { echo "ERROR: $CONF не найден"; exit 1; }
command -v wg >/dev/null || { echo "ERROR: wireguard-tools не установлены"; exit 1; }

# Найти pubkey по имени в vpn_peers.json (ключ — сам pubkey для WG)
PUB=$(python3 - "$PEERS_JSON" "$NAME" <<'PYEOF'
import json, sys, os
path, name = sys.argv[1], sys.argv[2]
if not os.path.exists(path):
    sys.exit(0)
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for k, v in data.items():
    if v == name and not k.startswith("reality:"):
        print(k); break
PYEOF
)
[[ -n "$PUB" ]] || { echo "ERROR: WG-пир «$NAME» не найден в vpn_peers.json"; exit 1; }

# 1. Из живого интерфейса
wg set "$IFACE" peer "$PUB" remove
echo "  пир убран из $IFACE"

# 2. Из wg0.conf — удалить блок [Peer] с этим PublicKey
python3 - "$CONF" "$PUB" "$NAME" <<'PYEOF'
import sys
path, pub, name = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path, encoding="utf-8").read().splitlines()
out, i = [], 0
while i < len(lines):
    # Блок пира: комментарий "# <name>" + [Peer] ... до пустой строки/конца
    if lines[i].strip() == "[Peer]":
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and lines[j].strip() and lines[j].strip() != "[Peer]":
            block.append(lines[j]); j += 1
        if any(pub in b for b in block):
            # выкинуть и предшествующий комментарий-заголовок
            while out and (out[-1].strip().startswith("#") or not out[-1].strip()):
                out.pop()
            i = j
            continue
        out.extend(block); i = j
    else:
        out.append(lines[i]); i += 1
open(path, "w", encoding="utf-8").write("\n".join(out).rstrip() + "\n")
PYEOF

# 3. vpn_peers.json + клиентский конфиг
python3 - "$PEERS_JSON" "$PUB" <<'PYEOF'
import json, sys, os
path, pub = sys.argv[1], sys.argv[2]
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.pop(pub, None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
PYEOF
SAFE_NAME=$(echo "$NAME" | tr ' /' '__')
rm -f "$CLIENTS_DIR/$SAFE_NAME.conf"

echo "✓ WireGuard-пир «$NAME» удалён. Его конфиг больше не подключится."
