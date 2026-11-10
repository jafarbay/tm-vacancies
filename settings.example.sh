# Copy to settings.sh and fill in:  cp settings.example.sh settings.sh && nano settings.sh && chmod 600 settings.sh
# settings.sh holds secrets: do not commit or share it.

# --- Telegram bot ---
export BOT_TOKEN=""            # from @BotFather
export ADMIN_IDS=""            # your telegram id (from @userinfobot), several: "111,222"
export DIGEST_HOUR="9"         # daily digest hour, Ashgabat time

# Proxy for Telegram if api.telegram.org is slow/blocked from this server (leave empty if it works):
#   http://user:pass@host:port      - works out of the box
#   socks5://user:pass@host:port    - needs: .venv/bin/pip install aiohttp-socks
export TELEGRAM_PROXY=""
export TELEGRAM_API_URL=""     # alternative: own reverse proxy to api.telegram.org, e.g. https://tg.example.com

# --- scraper ---
export SCRAPE_EVERY="1800"     # seconds between runs (30 min)
export SCRAPE_WORKERS="4"      # parallel detail downloads
export SCRAPE_DELAY="1.5"      # pause between requests per worker, seconds
export SCRAPER_PROXY=""        # not needed on a RU server

# --- site (later, when there is a domain) ---
export SITE_URL=""             # e.g. https://jobs.example.com; empty = bot links go to business.com.tm
export SITE_PORT="8010"
export SITE_HOST="127.0.0.1"   # 127.0.0.1 behind nginx; 0.0.0.0 to open http://IP:8010 without nginx
