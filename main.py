import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

async def main():
    bot = Bot(BOT_TOKEN)

    dp = Dispatcher()
    dp.include_router(router)

    print("Бот іске қосылды...")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
