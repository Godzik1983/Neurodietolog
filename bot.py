import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

import handlers

log_handlers: list[logging.Handler] = [logging.StreamHandler()]
log_file = os.getenv("LOG_FILE", "").strip()
if log_file:
    try:
        if os.path.isdir(log_file):
            raise IsADirectoryError(log_file)
        log_handlers.append(logging.FileHandler(log_file))
    except Exception:
        # Не падаем на старте из-за проблем с файловым логом.
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")
if not WEBHOOK_BASE_URL:
    raise RuntimeError("WEBHOOK_BASE_URL is not set")

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

WEBHOOK_URL = f"{WEBHOOK_BASE_URL.rstrip('/')}{WEBHOOK_PATH}"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
dp.include_routers(handlers.router)


async def on_startup(bot: Bot) -> None:
    logging.info("Запуск бота в webhook-режиме...")
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET or None,
        drop_pending_updates=True,
    )
    logging.info("Webhook установлен: %s", WEBHOOK_URL)


async def on_shutdown(bot: Bot) -> None:
    logging.info("Остановка бота...")
    await bot.delete_webhook()
    await bot.session.close()


def create_app() -> web.Application:
    app = web.Application()

    request_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET or None,
    )
    request_handler.register(app, path=WEBHOOK_PATH)

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/health", health)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    setup_application(app, dp, bot=bot)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=WEBAPP_HOST, port=WEBAPP_PORT)
