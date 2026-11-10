"""Telegram bot entry point: python -m bot.main"""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, TelegramObject

from . import admin, notifier, storage, user
from .config import ADMIN_IDS, BOT_TOKEN, TELEGRAM_API_URL, TELEGRAM_PROXY


class BanMiddleware(BaseMiddleware):
    """Drop updates from banned users."""

    async def __call__(self, handler: Callable[..., Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        u = getattr(event, "from_user", None)
        if u and u.id not in ADMIN_IDS:
            row = storage.get_user(u.id)
            if row and row["is_banned"]:
                return None
        return await handler(event, data)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    storage.init()
    api = TelegramAPIServer.from_base(TELEGRAM_API_URL) if TELEGRAM_API_URL else PRODUCTION
    bot = Bot(BOT_TOKEN, session=AiohttpSession(api=api, proxy=TELEGRAM_PROXY),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher()
    dp.message.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(BanMiddleware())
    dp.include_routers(admin.router, user.router)  # admin first: its FSM states win
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="filters", description="Мои фильтры"),
        BotCommand(command="favorites", description="Избранное"),
        BotCommand(command="search", description="Поиск: /search бухгалтер"),
        BotCommand(command="help", description="Помощь"),
    ])
    asyncio.create_task(notifier.run(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
