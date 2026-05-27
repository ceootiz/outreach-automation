#!/usr/bin/env bash
set -u

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${LAUNCHER_DIR}/Gmail Рассылка.command"
