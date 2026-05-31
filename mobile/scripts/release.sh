#!/bin/bash
# release.sh — полный цикл релиза мобайла.
#
# Что делает:
#   1. ./scripts/bump_version.sh X.Y.Z  (правит package.json/config.ts/build.gradle)
#   2. git commit + push (триггерит CI-сборку APK)
#   3. git tag vX.Y.Z + push
#   4. Ждёт пока Actions соберёт APK (polling)
#   5. Скачивает APK из артефактов
#   6. Создаёт GitHub Release с auto-собранными notes + APK
#
# Использование:
#   ./scripts/release.sh 0.15.0
#   ./scripts/release.sh 0.15.0 --notes "Дополнительные заметки к релизу"
#
# Зависимости: gh CLI (https://cli.github.com/), git, bump_version.sh
#
# Скрипт идемпотентен в начале: если git status грязный — упадёт; если tag
# уже существует — упадёт. Запускается из корня MiraMobile.

set -euo pipefail

red()    { printf '\e[31m%s\e[0m\n' "$*"; }
green()  { printf '\e[32m%s\e[0m\n' "$*"; }
yellow() { printf '\e[33m%s\e[0m\n' "$*"; }
blue()   { printf '\e[34m%s\e[0m\n' "$*"; }

# --- parse args ---
if [[ $# -lt 1 ]]; then
    red "usage: $0 <semver> [--notes 'extra notes']"
    echo "  e.g. $0 0.15.0"
    exit 1
fi

VERSION="$1"
EXTRA_NOTES=""
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --notes) EXTRA_NOTES="$2"; shift 2 ;;
        *) red "unknown arg: $1"; exit 1 ;;
    esac
done

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    red "✗ Неправильный semver: $VERSION (надо X.Y.Z)"
    exit 1
fi

TAG="v${VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- preflight ---
blue "▸ Preflight"

if [[ -n "$(git status --porcelain)" ]]; then
    red "✗ Рабочее дерево грязное — закоммить или stash сначала:"
    git status --short
    exit 1
fi

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    red "✗ Тег $TAG уже существует. Удали или возьми другой номер."
    exit 1
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    yellow "⚠ Ты на ветке '$CURRENT_BRANCH', не на main. Продолжить? [y/N]"
    read -r ans
    [[ "$ans" =~ ^[yY]$ ]] || exit 0
fi

GH=$(command -v gh || command -v ~/.local/bin/gh || true)
if [[ -z "$GH" ]]; then
    red "✗ gh CLI не найден. Поставь https://cli.github.com/ или ~/.local/bin/gh"
    exit 1
fi

# --- 1. bump version ---
blue "▸ Бамп версии → $VERSION"
./scripts/bump_version.sh "$VERSION"

# --- 2. commit + push ---
blue "▸ Commit + push (триггерит CI APK-сборку)"
git add package.json src/config.ts android/app/build.gradle
git commit -m "release: v$VERSION"

LAST_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
if [[ -n "$LAST_TAG" ]]; then
    AUTO_NOTES=$(git log "${LAST_TAG}..HEAD^" --pretty=format:"- %s" \
                 | grep -vE "^- (chore|docs)(\(|:)" || true)
else
    AUTO_NOTES=$(git log HEAD^ -n 20 --pretty=format:"- %s")
fi

git push origin "$CURRENT_BRANCH"

# --- 3. tag + push ---
blue "▸ Тег $TAG"
git tag -a "$TAG" -m "$TAG"
git push origin "$TAG"

# --- 4. ждём CI ---
blue "▸ Жду пока CI соберёт APK (5-10 минут)…"
sleep 15  # дать Actions время триггернуться

RUN_ID=""
for attempt in {1..40}; do
    LINE=$($GH run list --repo Glombert/Mira_Mobile --workflow build-apk.yml \
           --branch "$CURRENT_BRANCH" --limit 1 \
           --json databaseId,headSha,status,conclusion \
           --jq '.[0]' 2>/dev/null || echo "")
    if [[ -z "$LINE" ]]; then
        echo "  ⏳ run ещё не появился..."
        sleep 15
        continue
    fi
    HEAD_SHA=$(echo "$LINE" | python3 -c "import json,sys; print(json.load(sys.stdin)['headSha'])")
    STATUS=$(echo "$LINE" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
    CURRENT_SHA=$(git rev-parse HEAD)
    if [[ "$HEAD_SHA" != "$CURRENT_SHA" ]]; then
        echo "  ⏳ ждём run на текущий коммит ($CURRENT_SHA первые 7: ${CURRENT_SHA:0:7})..."
        sleep 15
        continue
    fi
    if [[ "$STATUS" == "completed" ]]; then
        CONCL=$(echo "$LINE" | python3 -c "import json,sys; print(json.load(sys.stdin)['conclusion'])")
        if [[ "$CONCL" == "success" ]]; then
            RUN_ID=$(echo "$LINE" | python3 -c "import json,sys; print(json.load(sys.stdin)['databaseId'])")
            green "  ✓ CI-сборка готова (run $RUN_ID)"
            break
        else
            red "✗ CI упал: conclusion=$CONCL"
            echo "  Лог: gh run view $LINE --repo Glombert/Mira_Mobile --log-failed"
            exit 1
        fi
    fi
    echo "  ⏳ ($attempt/40) status=$STATUS"
    sleep 15
done

if [[ -z "$RUN_ID" ]]; then
    red "✗ Timeout — CI run не завершился за 10 минут. Проверь Actions вручную."
    exit 1
fi

# --- 5. download APK ---
blue "▸ Скачиваю APK"
TMP=$(mktemp -d)
$GH run download "$RUN_ID" --repo Glombert/Mira_Mobile --dir "$TMP" >/dev/null
APK=$(find "$TMP" -name "*.apk" | head -1)
if [[ ! -f "$APK" ]]; then
    red "✗ APK не найден в артефактах $RUN_ID"
    exit 1
fi
green "  ✓ $APK ($(du -h "$APK" | cut -f1))"

# --- 6. create release ---
blue "▸ Создаю GitHub Release $TAG"
NOTES_FILE=$(mktemp)
{
    echo "## Изменения"
    echo ""
    if [[ -n "$AUTO_NOTES" ]]; then
        echo "$AUTO_NOTES"
    else
        echo "_см. полную историю в git log_"
    fi
    if [[ -n "$EXTRA_NOTES" ]]; then
        echo ""
        echo "## Заметки"
        echo ""
        echo "$EXTRA_NOTES"
    fi
    echo ""
    echo "## Установка"
    echo ""
    echo "Скачай \`$(basename "$APK")\` ниже и установи поверх предыдущей версии."
    echo "Подпись та же → апгрейд работает без переустановки."
} > "$NOTES_FILE"

$GH release create "$TAG" \
    --repo Glombert/Mira_Mobile \
    --title "$TAG" \
    --notes-file "$NOTES_FILE" \
    "$APK"

rm -rf "$TMP" "$NOTES_FILE"
green "✓ Релиз $TAG опубликован"
echo "  https://github.com/Glombert/Mira_Mobile/releases/tag/$TAG"
