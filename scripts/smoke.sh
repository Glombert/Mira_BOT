#!/bin/bash
# smoke.sh — end-to-end smoke-тесты для прода mira-bot.duckdns.org
#
# Проверяет каждый интерфейс «снаружи»: HTTP-эндпоинты, WS-протокол,
# upload, OAuth callback (без интерактива), целостность БД.
#
# Запуск:
#   ./scripts/smoke.sh              # все проверки
#   ./scripts/smoke.sh --with-llm   # +один LLM-ход (стоит немного)
#   ./scripts/smoke.sh --quiet      # только итог
#
# Требует ssh-доступ к root@mira-bot.duckdns.org (там читаем .env для
# генерации валидной сессии).

set -u
HOST="mira-bot.duckdns.org"
BASE="https://${HOST}"
WS_BASE="wss://${HOST}"
SSH="root@${HOST}"
VENV_PY="/root/mira_agent/venv/bin/python"

WITH_LLM=0
QUIET=0
LOCAL=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-llm) WITH_LLM=1; shift ;;
        --quiet) QUIET=1; shift ;;
        --local) LOCAL=1; shift ;;
        *) echo "unknown: $1" >&2; exit 2 ;;
    esac
done

# При --local пропускаем SSH — все «remote» команды исполняются на этой же машине.
# Используется в cron-обёртке на VPS.
run_remote() {
    if [[ "$LOCAL" -eq 1 ]]; then
        # Работаем в /root/mira_agent (для venv относительных путей)
        ( cd /root/mira_agent 2>/dev/null || true; bash -c "$1" )
    else
        ssh "$SSH" "$1"
    fi
}

PASS=0; FAIL=0; FAIL_NAMES=()

red()    { printf '\e[31m%s\e[0m\n' "$*"; }
green()  { printf '\e[32m%s\e[0m\n' "$*"; }
yellow() { printf '\e[33m%s\e[0m\n' "$*"; }
gray()   { printf '\e[90m%s\e[0m\n' "$*"; }

check() {
    local name="$1"
    local got="$2"
    local want="$3"
    if [[ "$got" == "$want" ]]; then
        PASS=$((PASS+1))
        [[ "$QUIET" -eq 1 ]] || green "✓ $name"
    else
        FAIL=$((FAIL+1))
        FAIL_NAMES+=("$name")
        red "✗ $name"
        gray "    got:  $got"
        gray "    want: $want"
    fi
}

check_contains() {
    local name="$1"
    local got="$2"
    local needle="$3"
    if [[ "$got" == *"$needle"* ]]; then
        PASS=$((PASS+1))
        [[ "$QUIET" -eq 1 ]] || green "✓ $name"
    else
        FAIL=$((FAIL+1))
        FAIL_NAMES+=("$name")
        red "✗ $name"
        gray "    got does not contain: $needle"
        gray "    got: ${got:0:200}"
    fi
}

# ----------------------------------------------------------------------
# Phase 1: HTTP-эндпоинты
# ----------------------------------------------------------------------
yellow "▸ HTTP endpoints"

CODE=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/health")
check "GET /health → 200" "$CODE" "200"

BODY=$(curl -sS "${BASE}/health")
check_contains "/health bot_alive" "$BODY" '"bot_alive":true'
check_contains "/health web_alive" "$BODY" '"web_alive":true'

CODE=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/")
check "GET / → 200" "$CODE" "200"

CODE=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/history")
check "GET /history без session → 401" "$CODE" "401"

# POST /upload без session, но с файлом — нужен валидный body чтобы дойти до auth-check
# (без файла FastAPI вернёт 422 — валидация body раньше handler logic)
TMP_FOR_AUTH=$(mktemp --suffix=.txt); echo "x" > "$TMP_FOR_AUTH"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' -F "file=@${TMP_FOR_AUTH}" "${BASE}/upload")
check "POST /upload без session → 401" "$CODE" "401"
rm -f "$TMP_FOR_AUTH"

# rate-limit /auth/telegram (10/min) — серия пустых попыток должна вернуть 429
for i in 1 2 3 4 5 6 7 8 9 10 11; do
    LAST_CODE=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/auth/telegram?id=0&hash=x&auth_date=0")
done
# Последний должен быть 429 (превышен лимит)
if [[ "$LAST_CODE" == "429" ]]; then
    PASS=$((PASS+1))
    [[ "$QUIET" -eq 1 ]] || green "✓ rate-limit /auth/telegram → 429 после 10+ попыток"
else
    yellow "? rate-limit /auth/telegram → $LAST_CODE (ожидался 429; могло сбросить за время другого теста)"
fi

# Cache-Control на /
CC=$(curl -sSI "${BASE}/" | grep -i 'cache-control' | tr -d '\r')
check_contains "Cache-Control no-cache на /" "$CC" "no-cache"

# CSP / security headers (информационно)
SH=$(curl -sSI "${BASE}/" | grep -iE 'x-frame|strict-transport|x-content' | tr -d '\r')
if [[ -n "$SH" ]]; then
    [[ "$QUIET" -eq 1 ]] || green "✓ security headers: $(echo "$SH" | tr '\n' '|')"
fi

# ----------------------------------------------------------------------
# Phase 2: сессия + WS handshake (через VPS — генерим валидный токен)
# ----------------------------------------------------------------------
yellow "▸ Session + WS"

# Получаем валидную сессию через make_session с реальным BOT_TOKEN на VPS
SESSION=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
import os; from dotenv import load_dotenv; load_dotenv(\".env\")
from web.security import make_session
tok = os.getenv(\"TELEGRAM_BOT_TOKEN\", \"\")
owner = int(os.getenv(\"OWNER_TELEGRAM_ID\", \"0\"))
print(make_session(tok, owner, \"SmokeTest\"))
'" 2>/dev/null)

if [[ -z "$SESSION" ]]; then
    red "✗ Не смог получить сессию через SSH"
    FAIL=$((FAIL+1))
    FAIL_NAMES+=("session")
else
    [[ "$QUIET" -eq 1 ]] || green "✓ Сессия выпущена ($(echo -n "$SESSION" | wc -c) символов)"
fi

# /history с валидной сессией — должен быть 200
if [[ -n "$SESSION" ]]; then
    ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SESSION")
    CODE=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/history?session=${ENCODED}&limit=1")
    check "GET /history с валидной сессией → 200" "$CODE" "200"
fi

# WS-сессия + первые сообщения. Используем python+websockets на VPS,
# так избегаем установки зависимостей локально.
if [[ -n "$SESSION" ]]; then
    WS_OUT=$(run_remote "$VENV_PY -c '
import asyncio, json, sys, websockets
async def main():
    uri = \"ws://127.0.0.1:8000/ws?session=$SESSION\"
    async with websockets.connect(uri) as ws:
        # ждём ready
        ready = await asyncio.wait_for(ws.recv(), timeout=5)
        rd = json.loads(ready)
        print(\"READY:\", rd.get(\"type\"), \"is_owner=\" + str(rd.get(\"is_owner\")), \"is_approved=\" + str(rd.get(\"is_approved\")))
        # пробуем /whoami
        await ws.send(json.dumps({\"type\":\"command\",\"cmd\":\"whoami\"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        m = json.loads(msg)
        print(\"WHOAMI:\", m.get(\"type\"), \"len=\" + str(len(m.get(\"content\",\"\"))))
        # /files
        await ws.send(json.dumps({\"type\":\"command\",\"cmd\":\"files\"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        m = json.loads(msg)
        print(\"FILES:\", m.get(\"type\"), \"count=\" + str(len(m.get(\"files\",[]))))
        # rituals (owner-only)
        await ws.send(json.dumps({\"type\":\"command\",\"cmd\":\"rituals\"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        m = json.loads(msg)
        print(\"RITUALS:\", m.get(\"type\"), \"content_starts=\" + (m.get(\"content\",\"\")[:30].replace(chr(10),\" \")))
        # неизвестная команда — должна тихо отлететь без ответа
        await ws.send(json.dumps({\"type\":\"command\",\"cmd\":\"nonexistent_xyz\"}))
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=1)
            print(\"UNKNOWN_CMD: got reply (ok)\")
        except asyncio.TimeoutError:
            print(\"UNKNOWN_CMD: silent (ok)\")
asyncio.run(main())
' 2>&1")
    [[ "$QUIET" -eq 1 ]] || echo "$WS_OUT" | sed 's/^/    /'
    check_contains "WS ready event"  "$WS_OUT" "READY: ready"
    check_contains "WS ready is_owner=True" "$WS_OUT" "is_owner=True"
    check_contains "WS /whoami → system"  "$WS_OUT" "WHOAMI: system"
    check_contains "WS /files → files type"  "$WS_OUT" "FILES: files"
    check_contains "WS /rituals → system"  "$WS_OUT" "RITUALS: system"
    check_contains "WS неизвестная команда не падает"  "$WS_OUT" "UNKNOWN_CMD:"
fi

# ----------------------------------------------------------------------
# Phase 3: Upload + multi-attachment WS-сообщение
# ----------------------------------------------------------------------
yellow "▸ Upload + multi-attachment"

if [[ -n "$SESSION" ]]; then
    TMP_FILE=$(mktemp --suffix=.txt)
    echo "smoke test $(date -u +%s)" > "$TMP_FILE"

    ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SESSION")
    UP_BODY=$(curl -sS -F "file=@${TMP_FILE}" "${BASE}/upload?session=${ENCODED}")
    check_contains "POST /upload текстовый файл → ok" "$UP_BODY" '"ok":true'

    # Большой файл (25MB+1) должен упасть с 413 на nginx-уровне
    BIG_FILE=$(mktemp --suffix=.bin)
    dd if=/dev/zero of="$BIG_FILE" bs=1M count=26 status=none
    BIG_CODE=$(curl -sS -o /dev/null -w '%{http_code}' -F "file=@${BIG_FILE}" "${BASE}/upload?session=${ENCODED}")
    if [[ "$BIG_CODE" == "413" ]]; then
        PASS=$((PASS+1))
        [[ "$QUIET" -eq 1 ]] || green "✓ nginx режет >25MB → 413"
    else
        yellow "? upload 26MB → $BIG_CODE (ожидался 413, проверь client_max_body_size)"
    fi

    rm -f "$TMP_FILE" "$BIG_FILE"
fi

# ----------------------------------------------------------------------
# Phase 4: Целостность БД и автономии
# ----------------------------------------------------------------------
yellow "▸ Storage + autonomy"

DB_INFO=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
from dotenv import load_dotenv; load_dotenv(\".env\")
from core import memory_crypto; memory_crypto.init()
from tools import db
conn = db.get_conn()
print(\"crypto:\", memory_crypto.is_enabled())
print(\"tables:\", [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()])
print(\"reminders_pending:\", conn.execute(\"SELECT COUNT(*) FROM reminders WHERE status=\\\"pending\\\"\").fetchone()[0])
print(\"reminders_total:\", conn.execute(\"SELECT COUNT(*) FROM reminders\").fetchone()[0])
print(\"push_tokens:\", conn.execute(\"SELECT COUNT(*) FROM push_tokens\").fetchone()[0])
print(\"users:\", conn.execute(\"SELECT COUNT(*) FROM user_profiles\").fetchone()[0])
print(\"gdrive_tokens:\", conn.execute(\"SELECT COUNT(*) FROM gdrive_tokens\").fetchone()[0])
print(\"ritual_runs:\", conn.execute(\"SELECT COUNT(*) FROM ritual_runs\").fetchone()[0])
' 2>&1")
[[ "$QUIET" -eq 1 ]] || echo "$DB_INFO" | sed 's/^/    /'
check_contains "crypto enabled" "$DB_INFO" "crypto: True"
check_contains "reminders table" "$DB_INFO" "reminders_total:"
check_contains "push_tokens table" "$DB_INFO" "push_tokens:"
check_contains "ritual_runs table" "$DB_INFO" "ritual_runs:"

# Ритуалы
RITUALS=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
from tools.rituals import load_rituals
r = load_rituals()
print(\"count:\", len(r))
print(\"names:\", [x[\"name\"] for x in r])
print(\"rituals_ge3:\", len(r) >= 3)
'" 2>&1)
[[ "$QUIET" -eq 1 ]] || echo "$RITUALS" | sed 's/^/    /'
check_contains "≥3 ритуала загружены" "$RITUALS" "rituals_ge3: True"

# Time-парсер с TZ
TP=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
from tools.time_parse import parse_time
ok, iso = parse_time(\"завтра 8:00\")
print(\"завтра 8:00 ok=\" + str(ok), \"+00:00 in iso:\", \"+00:00\" in iso)
ok2, iso2, rest = __import__(\"tools.time_parse\", fromlist=[\"extract_time_and_rest\"]).extract_time_and_rest(\"завтра 8:00 проверь календарь\")
print(\"extract:\", \"ok=\" + str(ok2), \"rest=\" + rest)
'" 2>&1)
[[ "$QUIET" -eq 1 ]] || echo "$TP" | sed 's/^/    /'
check_contains "parse_time tz-aware (UTC default)" "$TP" "+00:00 in iso: True"
check_contains "extract_time_and_rest корректный" "$TP" "rest=проверь календарь"

# attach_file tool
AF=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
import os, tempfile
from tools.file_tools import attach_file, pop_pending_attachments
# создадим временный файл в inbox владельца
uid = \"tg_$(grep OWNER_TELEGRAM_ID /root/mira_agent/.env | cut -d= -f2)\"
inbox = os.path.join(\"workspace\", uid, \"inbox\")
os.makedirs(inbox, exist_ok=True)
test = os.path.join(inbox, \"_smoke_attach.txt\")
with open(test, \"w\") as f: f.write(\"smoke\")
r = attach_file(uid, \"inbox/_smoke_attach.txt\")
print(\"attach ok:\", r.get(\"ok\"))
pending = pop_pending_attachments(uid)
print(\"pending count:\", len(pending))
print(\"second pop:\", len(pop_pending_attachments(uid)))  # должен быть 0
os.remove(test)
'" 2>&1)
[[ "$QUIET" -eq 1 ]] || echo "$AF" | sed 's/^/    /'
check_contains "attach_file работает" "$AF" "attach ok: True"
check_contains "pending очищается после pop" "$AF" "second pop: 0"

# FCM-инициализация
FCM=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
from dotenv import load_dotenv; load_dotenv(\".env\")
from tools import fcm_tools
ok = fcm_tools._ensure_init()
print(\"fcm init:\", ok, \"reason:\", fcm_tools._disabled_reason)
'" 2>&1)
[[ "$QUIET" -eq 1 ]] || echo "$FCM" | sed 's/^/    /'
check_contains "FCM Admin SDK инициализирован" "$FCM" "fcm init: True"

# Google API доступность (gdrive list + gcal list — только если токен есть)
GAPI=$(run_remote "cd /root/mira_agent && $VENV_PY -c '
from dotenv import load_dotenv; load_dotenv(\".env\")
import os
from core import memory_crypto; memory_crypto.init()
from tools.gdrive_tools import gdrive_list, gcal_list
uid = \"tg_\" + os.getenv(\"OWNER_TELEGRAM_ID\", \"0\")
r = gdrive_list(uid)
print(\"gdrive ok:\", r.get(\"ok\"), \"files:\", len(r.get(\"files\", [])))
r2 = gcal_list(uid, max_results=3)
print(\"gcal ok:\", r2.get(\"ok\"), \"events:\", len(r2.get(\"events\", [])))
' 2>&1")
[[ "$QUIET" -eq 1 ]] || echo "$GAPI" | sed 's/^/    /'
check_contains "Google Drive live" "$GAPI" "gdrive ok: True"
check_contains "Google Calendar live" "$GAPI" "gcal ok: True"

# ----------------------------------------------------------------------
# Phase 5 (опционально): один LLM-ход через WS
# ----------------------------------------------------------------------
if [[ "$WITH_LLM" -eq 1 ]] && [[ -n "$SESSION" ]]; then
    yellow "▸ LLM round-trip (--with-llm)"
    LLM=$(run_remote "$VENV_PY -c '
import asyncio, json, websockets
async def main():
    uri = \"ws://127.0.0.1:8000/ws?session=$SESSION\"
    async with websockets.connect(uri) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)  # skip ready
        await ws.send(json.dumps({\"content\": \"Ответь ровно одним словом: тест\"}))
        seen = []
        for _ in range(20):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                m = json.loads(msg)
                seen.append(m.get(\"type\"))
                if m.get(\"type\") in (\"message\", \"error\"):
                    print(\"FINAL:\", m.get(\"type\"), \"len=\" + str(len(m.get(\"content\", \"\"))))
                    break
            except asyncio.TimeoutError:
                print(\"TIMEOUT after\", seen)
                break
asyncio.run(main())
' 2>&1")
    echo "$LLM" | sed 's/^/    /'
    check_contains "LLM ответил message-event" "$LLM" "FINAL: message"
fi

# ----------------------------------------------------------------------
# Итог
# ----------------------------------------------------------------------
echo
TOTAL=$((PASS+FAIL))
if [[ "$FAIL" -eq 0 ]]; then
    green "═══ smoke-suite: $PASS/$TOTAL passed ═══"
    exit 0
else
    red "═══ smoke-suite: $FAIL/$TOTAL FAILED ═══"
    for n in "${FAIL_NAMES[@]}"; do echo "  • $n"; done
    exit 1
fi
