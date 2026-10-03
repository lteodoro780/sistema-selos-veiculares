#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$APP_DIR"
[[ "$(uname -s)" == "Linux" ]] || { printf 'Execute este instalador no Linux.\n' >&2; exit 1; }
[[ "${EUID:-$(id -u)}" -ne 0 ]] || { printf 'Execute como usuário normal, sem sudo.\n' >&2; exit 1; }
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null || { printf 'Instale Python 3.12 ou superior e python3-venv.\n' >&2; exit 1; }
"$PYTHON_BIN" -c 'import sqlite3, sys, venv; assert sys.version_info >= (3, 12), "É necessário Python 3.12 ou superior."'
[[ ! -L data && ! -L .venv && ! -L .env ]] || { printf 'Configuração/dados/ambiente não podem ser links simbólicos.\n' >&2; exit 1; }
if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv || { printf 'Instale o módulo venv da sua distribuição e tente novamente.\n' >&2; exit 1; }
fi
[[ -x .venv/bin/python ]] || { printf 'Ambiente incompatível. Não copie a .venv do Windows.\n' >&2; exit 1; }
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python gerenciar_linux.py instalar
printf '\nInstalação concluída. Para iniciar: bash INICIAR_SELOS.sh\n'
printf 'Acesso local: http://127.0.0.1:8004 · Celular: consulte GUIA_LINUX.md.\n'
