#!/usr/bin/env bash
# Health check: scraper proxy -> business.com.tm, Telegram reachability, bot token. Prints no secrets.
cd "$(dirname "$0")"
. ./settings.sh
ok()  { echo "  [OK]   $*"; }
bad() { echo "  [FAIL] $*"; }

echo "1. Scraper proxy (SCRAPER_PROXY)"
if [ -z "$SCRAPER_PROXY" ]; then
  bad "SCRAPER_PROXY is empty in settings.sh"
else
  P=(-x "$SCRAPER_PROXY" -s -m 40 --compressed)
  : > /tmp/bt_check.html
  info=$(curl "${P[@]}" https://ipinfo.io/json 2>/dev/null)
  if [ -n "$info" ]; then
    ok "proxy works: $(echo "$info" | grep -oE '"(country|org)": *"[^"]*"' | tr '\n' ' ')"
  else
    bad "proxy does not respond (check host/port/login, scheme http:// or socks5h://)"
  fi
  for url in "https://business.com.tm/ru/work/a/index?path=rabota%2Fvakansii&page=1" "https://business.com.tm/ru/work/5673"; do
    res=$(curl "${P[@]}" -o /tmp/bt_check.html -w "%{http_code} %{time_total}s, traffic %{size_download} bytes" -A "Mozilla/5.0" "$url" 2>/dev/null)
    size=$(wc -c < /tmp/bt_check.html 2>/dev/null || echo 0)
    if [[ "$res" == 200* ]] && [ "$size" -gt 10000 ]; then ok "business.com.tm: $res, ${size} bytes ($url)"
    else bad "business.com.tm: ${res:-no answer}, ${size} bytes ($url)"; fi
  done
  rm -f /tmp/bt_check.html
fi

echo "2. Telegram API"
code=$(curl -s -m 10 -o /dev/null -w "%{http_code}" https://api.telegram.org)
[[ "$code" =~ ^(200|302)$ ]] && ok "direct access: HTTP $code" || bad "direct access: HTTP $code (set TELEGRAM_PROXY)"
if [ -n "$TELEGRAM_PROXY" ]; then
  code=$(curl -s -m 15 -x "$TELEGRAM_PROXY" -o /dev/null -w "%{http_code}" https://api.telegram.org)
  [[ "$code" =~ ^(200|302)$ ]] && ok "via TELEGRAM_PROXY: HTTP $code" || bad "via TELEGRAM_PROXY: HTTP $code"
fi

echo "3. Bot token"
if [ -z "$BOT_TOKEN" ]; then bad "BOT_TOKEN is empty"
else
  TP=(); [ -n "$TELEGRAM_PROXY" ] && TP=(-x "$TELEGRAM_PROXY")
  me=$(curl -s -m 15 "${TP[@]}" "https://api.telegram.org/bot${BOT_TOKEN}/getMe")
  if echo "$me" | grep -q '"ok":true'; then ok "bot: @$(echo "$me" | grep -oE '"username":"[^"]*"' | cut -d'"' -f4)"
  else bad "getMe failed: $(echo "$me" | grep -oE '"description":"[^"]*"' || echo 'no answer')"; fi
fi
[ -n "$ADMIN_IDS" ] && ok "ADMIN_IDS set" || bad "ADMIN_IDS empty: /admin will not work"

echo "4. Python libs for proxies"
if [ -n "$TELEGRAM_PROXY" ]; then  # aiogram needs aiohttp-socks for ANY proxy, http included
  .venv/bin/python -c "import aiohttp_socks" 2>/dev/null && ok "aiohttp-socks installed" || bad "run .venv/bin/pip install aiohttp-socks"
fi
if [[ "$SCRAPER_PROXY" == socks* ]]; then
  .venv/bin/python -c "import socks" 2>/dev/null && ok "PySocks installed" || bad "socks proxy: run .venv/bin/pip install 'requests[socks]'"
fi
