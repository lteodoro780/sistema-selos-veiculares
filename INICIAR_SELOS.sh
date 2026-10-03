#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$APP_DIR"
[[ "${EUID:-$(id -u)}" -ne 0 ]] || { printf 'Execute sem sudo.\n' >&2; exit 1; }
[[ -x .venv/bin/python ]] || { printf 'Execute INSTALAR_LINUX.sh primeiro.\n' >&2; exit 1; }
exec .venv/bin/python gerenciar_linux.py iniciar
