#!/bin/bash
# reality_add_user.sh — добавить пользователя Reality/VLESS (свой uuid + ссылка).
#
# Использование (на VPS с reality-ezpz):
#   scripts/reality_add_user.sh "Имя пользователя"
#
# Что делает:
#   1. Генерирует uuid.
#   2. Добавляет пользователя в /opt/reality-ezpz/users И в inbound
#      engine.conf (users[]) с flow xtls-rprx-vision.
#   3. Перезапускает sing-box (docker restart) — мягко, существующие
#      пользователи не теряют ключи.
#   4. Собирает vless://-ссылку (на РУ-мост) + QR.
#   5. Регистрирует имя в memory/vpn_peers.json — экран «VPN» покажет
#      пользователя по-человечески (ключ "reality:<uuid>").
#
# Окружение:
#   REALITY_DIR       — каталог reality-ezpz (default /opt/reality-ezpz)
#   REALITY_ENDPOINT  — куда коннектится клиент (default 85.137.89.79:4443).
#                       Reality идёт на Амстердам НАПРЯМУЮ, а не через мост:
#                       TCP/TLS маскируется под google и проходит ТСПУ. Мост
#                       нужен только WireGuard (UDP душится). На Амстердаме
#                       443 занят nginx, Reality слушает 4443 (docker).
#   REALITY_CONTAINER — имя docker-контейнера (default reality-ezpz-engine-1)

set -euo pipefail

NAME="${1:?Использование: reality_add_user.sh \"Имя пользователя\"}"
DIR="${REALITY_DIR:-/opt/reality-ezpz}"
ENDPOINT="${REALITY_ENDPOINT:-85.137.89.79:4443}"
CONTAINER="${REALITY_CONTAINER:-reality-ezpz-engine-1}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PEERS_JSON="$REPO/memory/vpn_peers.json"
ENGINE="$DIR/engine.conf"
USERS="$DIR/users"
CONFIG="$DIR/config"

[[ -f "$ENGINE" ]] || { echo "ERROR: $ENGINE не найден"; exit 1; }
command -v docker >/dev/null || { echo "ERROR: docker не найден"; exit 1; }

# Имя-тег без пробелов/спецсимволов (sing-box name + ключ в users-файле)
TAG=$(echo "$NAME" | tr -c 'A-Za-z0-9_' '_' | sed 's/__*/_/g;s/^_//;s/_$//')
[[ -n "$TAG" ]] || TAG="user"
grep -q "^$TAG=" "$USERS" 2>/dev/null && { echo "ERROR: пользователь '$TAG' уже есть"; exit 1; }

UUID=$(cat /proc/sys/kernel/random/uuid)

# 1. engine.conf — добавить в users[] первого vless-inbound
python3 - "$ENGINE" "$UUID" "$TAG" <<'PYEOF'
import json, sys
path, uuid, name = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
for inb in cfg.get("inbounds", []):
    if inb.get("type") == "vless":
        inb.setdefault("users", []).append(
            {"uuid": uuid, "flow": "xtls-rprx-vision", "name": name})
        break
else:
    sys.exit("vless-inbound не найден в engine.conf")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
PYEOF

# 2. users-файл (формат Name=uuid)
echo "$TAG=$UUID" >> "$USERS"

# 3. Мягкий рестарт sing-box
docker restart "$CONTAINER" >/dev/null
echo "  sing-box перезапущен"

# 4. vless-ссылка из параметров config
PBK=$(grep -E '^public_key=' "$CONFIG" | cut -d= -f2-)
SID=$(grep -E '^short_id=' "$CONFIG" | cut -d= -f2-)
SNI=$(grep -E '^domain=' "$CONFIG" | cut -d= -f2-)
HOST="${ENDPOINT%:*}"; PORT="${ENDPOINT##*:}"
VLESS="vless://${UUID}@${HOST}:${PORT}?type=tcp&security=reality&sni=${SNI}&fp=chrome&pbk=${PBK}&sid=${SID}&flow=xtls-rprx-vision&packet_encoding=xudp#$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$NAME")"

# 5. Имя для экрана «VPN» (ключ reality:<uuid>)
python3 - "$PEERS_JSON" "reality:$UUID" "$NAME" <<'PYEOF'
import json, sys, os
path, key, name = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
data[key] = name
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
PYEOF

echo "✓ Reality-пользователь «$NAME» добавлен (uuid $UUID)"
echo
echo "── Для СМС/мессенджера (вставка из буфера в Hiddify/v2rayNG/NekoBox): ──"
echo "$VLESS"
echo "──────────────────────────────────────────────────────────────────────"
if command -v qrencode >/dev/null; then
    echo "  QR для сканирования:"
    qrencode -t ansiutf8 <<< "$VLESS"
else
    echo "  (поставь qrencode для QR: apt install qrencode)"
fi
