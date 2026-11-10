import os
from datetime import timedelta, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
# If Telegram is throttled on the RU server: http/socks5 proxy or a self-hosted Bot API server / reverse proxy.
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY") or None      # socks5 needs `pip install aiohttp-socks`
TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL") or None  # e.g. https://tg-proxy.example.com
TZ = timezone(timedelta(hours=5))  # Ashgabat
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "9"))  # local time
NOTIFY_INTERVAL = int(os.getenv("NOTIFY_INTERVAL", "60"))  # seconds between checks for new vacancies
NOTIFY_MAX_AGE_DAYS = 3  # never push vacancies older than this (e.g. after a backlog import)
