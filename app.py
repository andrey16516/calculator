import os
import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from bot import dp  # dp exported from bot.py

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

BOT_WEBHOOK_SECRET = os.getenv("BOT_WEBHOOK_SECRET", "secret").strip()
WEBHOOK_PATH = f"/webhook/{BOT_WEBHOOK_SECRET}"

# Render provides this
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
if not WEBHOOK_HOST:
    logging.warning("RENDER_EXTERNAL_URL is not set yet (Render sets it at runtime).")

WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

PORT = int(os.getenv("PORT", "10000"))

# Create bot here and inject to dispatcher
bot = Bot(token=BOT_TOKEN)
dp["bot"] = bot  # store bot in dispatcher context


async def handle_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot=bot, update=update)
        return web.Response(text="ok")
    except Exception:
        logging.exception("Webhook handling error")
        return web.Response(status=500, text="error")


async def on_startup(app: web.Application):
    # Set webhook
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info("Webhook set to %s", WEBHOOK_URL)


async def on_cleanup(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()


def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()