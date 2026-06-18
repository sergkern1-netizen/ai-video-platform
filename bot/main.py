import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.config import get_bot_token
from bot.handlers import router
from bot.state import init_db


def _configure_logging():
    log_path = os.environ.get("BOT_LOG_FILE", "logs/bot.log")
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=log_path,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main():
    load_dotenv()
    _configure_logging()
    init_db()

    bot = Bot(token=get_bot_token())
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
