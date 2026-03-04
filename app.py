import os
import logging
from flask import Flask, request
from aiogram import types
from aiogram.utils.executor import start_webhook

from bot import dp, bot

logging.basicConfig(level=logging.INFO)

WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_PATH = f"/webhook/{os.getenv('BOT_WEBHOOK_SECRET', 'secret')}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)

@app.post(WEBHOOK_PATH)
async def webhook():
    update = types.Update(**request.json)
    await dp.process_update(update)
    return "ok"

async def on_startup(_):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(_):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )