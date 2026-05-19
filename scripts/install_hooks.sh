#!/bin/bash
# install_hooks.sh — переключает git на .githooks/ как hooksPath репозитория.
#
# Запускать однократно после клонирования:
#   ./scripts/install_hooks.sh

set -e
cd "$(dirname "$0")/.."

git config core.hooksPath .githooks
chmod +x .githooks/*
echo "✓ git hooks установлены (core.hooksPath = .githooks)"
echo "  pre-commit: блокирует .env, credentials.json, *.pem и явные API-ключи."
