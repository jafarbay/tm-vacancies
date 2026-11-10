#!/usr/bin/env bash
# One-time setup: venv + dependencies + settings template.
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required, found " + sys.version.split()[0]'

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
[ -f settings.sh ] || { cp settings.example.sh settings.sh; chmod 600 settings.sh; }
chmod +x run_*.sh
mkdir -p data

echo "OK. Now fill settings.sh (BOT_TOKEN, ADMIN_IDS, TELEGRAM_PROXY if needed): nano settings.sh"
