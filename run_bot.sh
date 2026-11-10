#!/usr/bin/env bash
# Telegram bot with auto-restart. Run in screen:  screen -dmS vac-bot ./run_bot.sh
cd "$(dirname "$0")"
. ./settings.sh
while true; do
  .venv/bin/python -m bot.main 2>&1 | tee -a data/bot.log
  echo "$(date '+%F %T') bot stopped, restart in 10s" | tee -a data/bot.log
  sleep 10
done
