import logging
import asyncio
from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
import handlers


# Логирование
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('bot.log'),
                              logging.StreamHandler()])

load_dotenv()
bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
dp = Dispatcher()
dp.include_routers(handlers.router,)


async def main():
    try:
        logging.info("Запуск бота...")
        await dp.start_polling(bot)
    finally:
        logging.info("Остановка бота...")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
