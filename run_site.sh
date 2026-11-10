#!/usr/bin/env bash
# Web site with auto-restart. Run in screen:  screen -dmS site ./run_site.sh
# SITE_HOST=127.0.0.1 (default) when nginx is in front; 0.0.0.0 to open http://IP:8010 directly.
cd "$(dirname "$0")"
. ./settings.sh
while true; do
  .venv/bin/uvicorn app.main:app --host "${SITE_HOST:-127.0.0.1}" --port "${SITE_PORT:-8010}" \
    --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header 2>&1 | tee -a data/site.log
  echo "$(date '+%F %T') site stopped, restart in 10s" | tee -a data/site.log
  sleep 10
done
