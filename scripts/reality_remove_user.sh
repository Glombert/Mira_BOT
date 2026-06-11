#!/bin/bash
# reality_remove_user.sh — удалить пользователя Reality/VLESS.
#
# Использование (на VPS с reality-ezpz):
#   scripts/reality_remove_user.sh "Имя пользователя"
#
# Что делает:
#   1. Находит пользователя по имени-тегу в /opt/reality-ezpz/users.
#   2. Удаляет его из engine.conf (users[]) и из файла users.
#   3. Перезапускает sing-box (docker restart).
#   4. Убирает имя из memory/vpn_peers.json.
#
# Защита: нельзя удалить последнего пользователя (inbound без users[]
# может уронить sing-box).
#
# Окружение: REALITY_DIR, REALITY_CONTAINER (как в reality_add_user.sh).

set -euo pipefail

NAME="${1:?Использование: reality_remove_user.sh \"Имя пользователя\"}"
DIR="${REALITY_DIR:-/opt/reality-ezpz}"
CONTAINER="${REALITY_CONTAINER:-reality-ezpz-engine-1}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PEERS_JSON="$REPO/memory/vpn_peers.json"
ENGINE="$DIR/engine.conf"
USERS="$DIR/users"

[[ -f "$ENGINE" ]] || { echo "ERROR: $ENGINE не найден"; exit 1; }
command -v docker >/dev/null || { echo "ERROR: docker не найден"; exit 1; }

TAG=$(python3 -c "import re,sys; s=re.sub(r'[^\w]','_',sys.argv[1],flags=re.UNICODE).strip('_'); print(re.sub(r'_+','_',s))" "$NAME")
LINE=$(grep -n "^$TAG=" "$USERS" 2>/dev/null || true)
[[ -n "$LINE" ]] || { echo "ERROR: пользователь '$TAG' не найден"; exit 1; }
UUID="${LINE##*=}"

# Защита: не удаляем последнего
TOTAL=$(grep -c '=' "$USERS" || echo 0)
[[ "$TOTAL" -gt 1 ]] || { echo "ERROR: '$TAG' — последний пользователь, удаление оставит inbound пустым"; exit 1; }

# 1. engine.conf — убрать запись по uuid (и из v2ray stats по имени)
python3 - "$ENGINE" "$UUID" "$TAG" <<'PYEOF'
import json, sys
path, uuid, name = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
for inb in cfg.get("inbounds", []):
    if inb.get("type") == "vless":
        inb["users"] = [u for u in inb.get("users", []) if u.get("uuid") != uuid]
        break
stats = cfg.get("experimental", {}).get("v2ray_api", {}).get("stats")
if stats is not None:
    stats["users"] = [u for u in stats.get("users", []) if u != name]
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
PYEOF

# 2. users-файл
sed -i "/^$TAG=/d" "$USERS"

# 3. Рестарт sing-box
docker restart "$CONTAINER" >/dev/null
echo "  sing-box перезапущен"

# 4. Имя с экрана VPN
python3 - "$PEERS_JSON" "reality:$UUID" <<'PYEOF'
import json, sys, os
path, key = sys.argv[1], sys.argv[2]
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.pop(key, None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
PYEOF

echo "✓ Reality-пользователь «$NAME» удалён (uuid $UUID). Его ссылка больше не работает."
