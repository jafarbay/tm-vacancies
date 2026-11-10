"""Background loop: instant notifications and the daily digest."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import storage, ui
from .config import DIGEST_HOUR, NOTIFY_INTERVAL, NOTIFY_MAX_AGE_DAYS, TZ

log = logging.getLogger("bot.notifier")
PER_TICK = 10   # max instant messages per user per check
DIGEST_MAX = 15


async def send(bot: Bot, uid: int, text: str, markup=None) -> bool:
    for _ in range(2):
        try:
            await bot.send_message(uid, text, reply_markup=markup)
            await asyncio.sleep(0.05)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            storage.update_user(uid, is_active=0)
            return False
        except Exception as e:
            log.warning("send to %s failed: %s", uid, e)
            return False
    return False


async def tick(bot: Bot) -> None:
    if storage.flag("notify_paused"):
        return
    upto = storage.ready_max_id()

    for u in storage.users_for("instant"):
        if u["last_vacancy_id"] >= upto:
            continue
        items = storage.new_for(u, upto, PER_TICK, NOTIFY_MAX_AGE_DAYS)
        sent_to = upto if len(items) < PER_TICK else items[-1]["id"]
        for v in items:
            if not await send(bot, u["id"], "🔔 <b>Новая вакансия</b>\n\n" + ui.card(v), ui.card_kb(v, False, "-")):
                break
        storage.update_user(u["id"], last_vacancy_id=sent_to)

    now = datetime.now(TZ)
    today = now.date().isoformat()
    if now.hour >= DIGEST_HOUR:
        for u in storage.users_for("digest"):
            if u["last_digest"] == today:
                continue
            items = storage.new_for(u, upto, DIGEST_MAX, 2)
            if items:
                await send(bot, u["id"], ui.digest(items),
                           ui.kb([ui.btn("🔎 Смотреть в боте", "bl:0", style="primary")]))
            storage.update_user(u["id"], last_digest=today, last_vacancy_id=upto)


async def run(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception:
            log.exception("notifier tick failed")
        await asyncio.sleep(NOTIFY_INTERVAL)
