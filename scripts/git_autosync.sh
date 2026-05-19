#!/bin/bash
# git_autosync.sh — синк локальных коммитов /evolve с GitHub.
#
# Запускается по cron'у на VPS (например ежечасно). Логика:
#   1. Если есть незакоммиченные изменения (после /evolve safe_apply должен
#      был всё закоммитить — но мало ли) — лог и выход.
#   2. git fetch origin
#   3. Если локальный ahead — push.
#   4. Если remote ahead — pull --ff-only (только fast-forward, не merge).
#   5. Если diverged — лог "DIVERGED, ручное вмешательство".
#
# Установка cron:
#   crontab -e
#   0 * * * * /root/mira_agent/scripts/git_autosync.sh

set -u
LOG=/root/mira_autosync.log
REPO=/root/mira_agent

cd "$REPO" || { echo "$(date) - cd failed" >> "$LOG"; exit 1; }

# Английская локаль — стабильный парсинг
export LANG=C LC_ALL=C

ts() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }

# 1. Незакоммиченные изменения? — пропускаем (но не молча)
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "$(ts) [skip] working tree dirty:" >> "$LOG"
    git status --short >> "$LOG"
    exit 0
fi

# 2. Фетчим
if ! git fetch origin --quiet 2>>"$LOG"; then
    echo "$(ts) [error] fetch failed" >> "$LOG"
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse "@{u}" 2>/dev/null || echo "")

if [[ -z "$REMOTE" ]]; then
    echo "$(ts) [skip] no upstream for $BRANCH" >> "$LOG"
    exit 0
fi

if [[ "$LOCAL" = "$REMOTE" ]]; then
    # синхронизированы, ничего делать не надо
    exit 0
fi

BASE=$(git merge-base @ "@{u}")

if [[ "$LOCAL" = "$BASE" ]]; then
    # Локальный отстал — pull (fast-forward only)
    if git pull --ff-only --quiet origin "$BRANCH" 2>>"$LOG"; then
        NEW_HEAD=$(git rev-parse HEAD)
        echo "$(ts) [pull] $BRANCH ${LOCAL:0:7} -> ${NEW_HEAD:0:7}" >> "$LOG"

        # Если в pull'е есть изменения web-клиента — пересобрать бандл
        # и перезапустить mira-web. clients/apps/web/dist/ гитнорится,
        # значит git pull сам бандл не привезёт.
        if git diff --name-only "$LOCAL" "$NEW_HEAD" 2>/dev/null | grep -qE '^clients/(apps/web|packages/shared|package(-lock)?\.json)'; then
            echo "$(ts) [deploy] изменения web-клиента — запуск deploy_web.sh" >> "$LOG"
            if "$REPO/scripts/deploy_web.sh" >>"$LOG" 2>&1; then
                echo "$(ts) [deploy] ✓ готов" >> "$LOG"
            else
                echo "$(ts) [deploy] ✗ упал — см. лог выше" >> "$LOG"
            fi
        fi
    else
        echo "$(ts) [error] pull --ff-only failed for $BRANCH" >> "$LOG"
    fi
elif [[ "$REMOTE" = "$BASE" ]]; then
    # Локальный впереди — push
    if git push origin "$BRANCH" 2>>"$LOG"; then
        echo "$(ts) [push] $BRANCH ${REMOTE:0:7} -> ${LOCAL:0:7}" >> "$LOG"
    else
        echo "$(ts) [error] push failed for $BRANCH" >> "$LOG"
    fi
else
    # Расходятся — ручное разбирательство
    echo "$(ts) [diverged] $BRANCH local=${LOCAL:0:7} remote=${REMOTE:0:7} base=${BASE:0:7}" >> "$LOG"
fi
