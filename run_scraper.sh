#!/usr/bin/env bash
# Scraper loop: new vacancies every SCRAPE_EVERY seconds. Run in screen:  screen -dmS vac-scraper ./run_scraper.sh
cd "$(dirname "$0")"
. ./settings.sh
while true; do
  echo "$(date '+%F %T') === scraper run start ===" | tee -a data/scraper.log
  .venv/bin/python -m app.scraper --details 300 2>&1 | tee -a data/scraper.log
  echo "$(date '+%F %T') === next run at $(date -d "+${SCRAPE_EVERY:-1800} sec" '+%H:%M') ===" | tee -a data/scraper.log
  sleep "${SCRAPE_EVERY:-1800}"
done
