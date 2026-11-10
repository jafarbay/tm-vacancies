# Деплой на сервер (Ubuntu, screen)

Нужен Linux-сервер с Python 3.10+. Сам business.com.tm отвечает только домашним/мобильным IP
из РФ/ТМ: с IP дата-центров соединение сбрасывается (`Connection refused`), поэтому парсеру
обычно нужен резидентный прокси (`SCRAPER_PROXY`). Трафика мало: ~9 КБ на страницу, ~15 МБ в месяц.

## 1. Код на сервер

```bash
git clone https://github.com/<user>/<repo>.git ~/vacancies
cd ~/vacancies
bash setup.sh                 # venv, зависимости, settings.sh из шаблона
nano settings.sh              # BOT_TOKEN, ADMIN_IDS, прокси, SITE_URL
bash check.sh                 # прокси -> business.com.tm, Telegram, токен
```

`settings.sh` хранит секреты и не попадает в git (`chmod 600` делает `setup.sh`).

## 2. Первичное наполнение базы

```bash
. ./settings.sh && .venv/bin/python -m app.scraper --full   # ~143 стр. списка + ~1400 вакансий, 5-10 мин
```

## 3. Запуск в screen

```bash
screen -dmS scraper ./run_scraper.sh   # парсер раз в SCRAPE_EVERY секунд (30 мин)
screen -dmS bot ./run_bot.sh           # Telegram-бот
screen -dmS site ./run_site.sh         # сайт на 127.0.0.1:8010
```

| действие | команда |
|---|---|
| список | `screen -ls` |
| подключиться / отключиться | `screen -r bot`, затем `Ctrl+A`, `D` |
| остановить | `screen -S bot -X quit` |
| логи | `tail -n 30 data/bot.log` (`scraper.log`, `site.log`) |

Скрипты сами перезапускают процесс при падении. Автозапуск после перезагрузки (`crontab -e`):
```
@reboot cd ~/vacancies && screen -dmS scraper ./run_scraper.sh
@reboot cd ~/vacancies && screen -dmS bot ./run_bot.sh
@reboot cd ~/vacancies && screen -dmS site ./run_site.sh
```

## 4. nginx (сайт на 80 порту)

```bash
apt install -y nginx
cp deploy/nginx.conf /etc/nginx/sites-available/vacancies
ln -sf /etc/nginx/sites-available/vacancies /etc/nginx/sites-enabled/vacancies
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```
Сайт открывается по `http://<ip-сервера>`. С доменом: заменить `server_name _;` на домен,
`certbot --nginx -d <домен>`, в `settings.sh` поставить `SITE_URL=https://<домен>`.

## 5. Telegram на российском сервере

Если `check.sh` показывает, что `api.telegram.org` напрямую недоступен, указать в `settings.sh`
`TELEGRAM_PROXY` (http или socks5). Бесплатный вариант: SSH-туннель через любой зарубежный сервер:
```bash
ssh -f -N -D 1080 user@<зарубежный-сервер>
# settings.sh: export TELEGRAM_PROXY="socks5://127.0.0.1:1080"
```

## Обслуживание

- Обновление кода: `git pull`, затем перезапустить нужный screen.
- После правки ключевых слов в `app/classify.py`: `.venv/bin/python -m app.scraper --reclassify`.
- После улучшения парсера страниц: `.venv/bin/python -m app.scraper --refetch` (перекачает полные тексты).
- Бэкап: `sqlite3 data/vacancies.db ".backup data/backup.db"`.
