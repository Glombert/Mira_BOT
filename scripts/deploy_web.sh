#!/bin/bash
# deploy_web.sh — собрать веб-клиент и перезапустить mira-web на VPS.
#
# Сценарий:
#   1. Проверяет node 20+ и npm.
#   2. npm install в clients/ (только если package-lock новее node_modules).
#   3. npm run build:web → создаёт clients/apps/web/dist/.
#   4. systemctl restart mira-web (если unit активен).
#
# Запускать **на VPS** после изменений в clients/ (или после git pull).
# Идемпотентный: можно запускать сколько угодно раз.
#
# Использование:
#   /root/mira_agent/scripts/deploy_web.sh
#
# Опции окружения:
#   REPO=/путь/к/mira_agent  — переопределить корень репо
#   SKIP_RESTART=1           — пропустить systemctl restart

set -euo pipefail

REPO="${REPO:-/root/mira_agent}"
SKIP_RESTART="${SKIP_RESTART:-0}"

cd "$REPO"

# 1. Проверка node
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: node не установлен." >&2
    echo "Установи node 20+: https://github.com/nodesource/distributions" >&2
    exit 1
fi
NODE_MAJOR=$(node -p "process.versions.node.split('.')[0]")
if [[ "$NODE_MAJOR" -lt 20 ]]; then
    echo "ERROR: нужен node 20+, у тебя $(node --version)" >&2
    exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm не найден (странно — обычно идёт с node)." >&2
    exit 1
fi

# 2. npm install — только если package-lock новее node_modules
cd "$REPO/clients"
if [[ ! -d node_modules ]] || [[ package-lock.json -nt node_modules ]]; then
    echo "→ npm install"
    npm install --no-audit --no-fund
fi

# 3. build:web
echo "→ npm run build:web"
npm run build:web

# Sanity-check: dist должен появиться
if [[ ! -f "$REPO/clients/apps/web/dist/index.html" ]]; then
    echo "ERROR: build прошёл, но dist/index.html не найден." >&2
    exit 1
fi

# 4. Рестарт mira-web
cd "$REPO"
if [[ "$SKIP_RESTART" == "1" ]]; then
    echo "  (SKIP_RESTART=1 — пропускаю systemctl restart)"
elif systemctl list-unit-files mira-web.service >/dev/null 2>&1; then
    echo "→ systemctl restart mira-web"
    systemctl restart mira-web
else
    echo "  mira-web.service не установлен — рестартуй сервис вручную."
fi

echo "✓ deploy готов: $(node -p "require('./clients/apps/web/package.json').version")"
