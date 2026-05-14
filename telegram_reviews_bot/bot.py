import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")

START_TEXT = (
    "Здравствуйте! Это Telegram-версия бота. "
    "Логика Max-бота перенесена в проект и будет адаптирована под Telegram сценарий."
)


dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT)


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    await message.answer("Сообщение получено. Следующий шаг: подключаем полную бизнес-логику из core_logic.py.")


async def main() -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
