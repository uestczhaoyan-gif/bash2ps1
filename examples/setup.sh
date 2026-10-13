#!/usr/bin/env bash
# Example: directory and UTF-8 config, no network calls.
set -e
PROJECT="demo project"
export APP_MODE=development
mkdir -p "$PROJECT"
cd "$PROJECT"
printf '%s\n' 'APP_MODE=development' > .env
touch README.md
[ -f .env ] && echo "Config created"
cat .env | grep -F APP_MODE
