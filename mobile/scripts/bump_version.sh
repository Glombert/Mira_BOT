#!/bin/bash
# bump_version.sh — синхронно поднять версию мобильного приложения.
#
# Что обновляет:
#   1. package.json → "version"          (читается build.gradle для versionName,
#                                          GitHub Actions именует APK по этому полю)
#   2. src/config.ts → APP_VERSION        (runtime: экран логина + /mobile/version)
#   3. android/app/build.gradle → versionCode (Android требует строго возрастающий
#                                              integer для распознавания обновления)
#
# Использование:
#   ./scripts/bump_version.sh 0.8.1     # semver, без префикса v
#
# Должен запускаться из корня MiraMobile.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <semver>" >&2
    echo "  e.g. $0 0.8.1" >&2
    exit 1
fi

NEW_VERSION="$1"
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "✗ semver должен быть X.Y.Z, получено: $NEW_VERSION" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# 1. package.json
node -e "
  const fs = require('fs');
  const p = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  p.version = '$NEW_VERSION';
  fs.writeFileSync('package.json', JSON.stringify(p, null, 2) + '\n');
"
echo "✓ package.json → $NEW_VERSION"

# 2. config.ts
sed -i "s/^export const APP_VERSION = '.*';$/export const APP_VERSION = '$NEW_VERSION';/" src/config.ts
echo "✓ src/config.ts → APP_VERSION='$NEW_VERSION'"

# 3. versionCode (инкремент integer)
CURRENT_CODE=$(grep -oE "versionCode [0-9]+" android/app/build.gradle | grep -oE "[0-9]+")
NEW_CODE=$((CURRENT_CODE + 1))
sed -i "s/versionCode $CURRENT_CODE/versionCode $NEW_CODE/" android/app/build.gradle
echo "✓ versionCode $CURRENT_CODE → $NEW_CODE (build.gradle берёт versionName из package.json)"

echo ""
echo "Готово. Теперь:"
echo "  git add package.json src/config.ts android/app/build.gradle"
echo "  git commit -m 'release: v$NEW_VERSION'"
echo "  git push origin main   # триггерит build-apk.yml"
