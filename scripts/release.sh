#!/bin/bash
# release.sh — релиз mira_agent (бэк, без APK).
#
# Что делает:
#   1. Опционально обновляет version-badge в README.md
#   2. git commit изменений (если есть)
#   3. git tag vX.Y + git push tag
#   4. gh release create с auto-notes (commits since last tag) + extra notes
#
# Использование:
#   ./scripts/release.sh 2.2
#   ./scripts/release.sh 2.2 --notes "Дополнительные заметки"
#   ./scripts/release.sh 2.2 --skip-readme  # не трогать badge
#
# Скрипт не падает если README уже на нужной версии. Tag + release всегда.

set -euo pipefail

red()    { printf '\e[31m%s\e[0m\n' "$*"; }
green()  { printf '\e[32m%s\e[0m\n' "$*"; }
yellow() { printf '\e[33m%s\e[0m\n' "$*"; }
blue()   { printf '\e[34m%s\e[0m\n' "$*"; }

if [[ $# -lt 1 ]]; then
    red "usage: $0 <X.Y[.Z]> [--notes 'extra'] [--skip-readme]"
    echo "  e.g. $0 2.2"
    echo "       $0 2.2.1 --notes 'патч-релиз'"
    exit 1
fi

VERSION="$1"
EXTRA_NOTES=""
SKIP_README=0
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --notes) EXTRA_NOTES="$2"; shift 2 ;;
        --skip-readme) SKIP_README=1; shift ;;
        *) red "unknown arg: $1"; exit 1 ;;
    esac
done

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
    red "✗ Неправильный semver: $VERSION (X.Y или X.Y.Z)"
    exit 1
fi

TAG="v${VERSION}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    red "✗ Тег $TAG уже существует"
    exit 1
fi

GH=$(command -v gh || command -v ~/.local/bin/gh || true)
if [[ -z "$GH" ]]; then
    red "✗ gh CLI не найден"
    exit 1
fi

# --- README badge ---
if [[ "$SKIP_README" -ne 1 ]] && [[ -f README.md ]]; then
    if grep -qE "version-[0-9]+\.[0-9]+[\.0-9]*-brightgreen" README.md; then
        sed -i -E "s|version-[0-9]+\.[0-9]+[\.0-9]*-brightgreen|version-${VERSION}-brightgreen|" README.md
        sed -i -E "s|releases/tag/v[0-9]+\.[0-9]+[\.0-9]*\)|releases/tag/v${VERSION})|" README.md
        if [[ -n "$(git status --porcelain README.md)" ]]; then
            blue "▸ README badge → ${VERSION}"
            git add README.md
            git commit -m "docs(readme): bump version badge → ${VERSION}"
        fi
    fi
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Пуш ветки если есть unpushed
if [[ -n "$(git log "@{u}..HEAD" --oneline 2>/dev/null || true)" ]]; then
    git push origin "$CURRENT_BRANCH" 2>&1 | tail -3 || true
fi

# Auto-notes
LAST_TAG=$(git describe --tags --abbrev=0 HEAD 2>/dev/null || echo "")
AUTO_NOTES=""
if [[ -n "$LAST_TAG" ]]; then
    AUTO_NOTES=$(git log "${LAST_TAG}..HEAD" --pretty=format:"- %s" \
                 | grep -vE "^- chore: bump|^- chore: remove tsconfig" || true)
fi

# Tag + push
blue "▸ Тег $TAG"
git tag -a "$TAG" -m "$TAG"
git push origin "$TAG"

# Release
blue "▸ Создаю GitHub Release $TAG"
NOTES_FILE=$(mktemp)
{
    echo "## Что изменилось"
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
    if [[ -n "$LAST_TAG" ]]; then
        echo "**Diff:** [\`${LAST_TAG}...${TAG}\`](https://github.com/Glombert/Mira_BOT/compare/${LAST_TAG}...${TAG})"
    fi
} > "$NOTES_FILE"

$GH release create "$TAG" \
    --repo Glombert/Mira_BOT \
    --title "$TAG" \
    --notes-file "$NOTES_FILE"

rm -f "$NOTES_FILE"
green "✓ Релиз $TAG опубликован"
echo "  https://github.com/Glombert/Mira_BOT/releases/tag/$TAG"
