import os
import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from bot import build_dispatcher  # мы сделаем эту функцию в bot.py


logging.basicConfig(level=logging.INFO)

routes = web.RouteTableDef()


@routes.get("/health")
async def health(_: web.Request):
    return web.Response(text="ok")


def get_webhook_base_url(request: web.Request) -> str:
    # Render проксирует HTTPS; aiohttp внутри видит http, поэтому берём host
    host = request.headers.get("x-forwarded-host") or request.host
    proto = request.headers.get("x-forwarded-proto", "https")
    return f"{proto}://{host}"


async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    secret = os.getenv("BOT_WEBHOOK_SECRET", "")
    path = os.getenv("WEBHOOK_PATH", "/webhook")

    # Если WEBHOOK_URL не задан — собираем из домена сервиса
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        # Появится после первого запроса к сервису; это нормально.
        logging.warning("WEBHOOK_URL is not set. Webhook will be set on first request to /set_webhook.")
        return

    await bot.set_webhook(
        url=webhook_url + path,
        secret_token=secret or None,
        drop_pending_updates=True,
    )
    logging.info("Webhook set to %s%s", webhook_url, path)


async def on_cleanup(app: web.Application):
    bot: Bot = app["bot"]
    await bot.session.close()


@routes.post("/webhook")
async def webhook_handler(request: web.Request):
    bot: Bot = request.app["bot"]
    dp: Dispatcher = request.app["dp"]

    # Проверка секретного токена (защита от левых запросов)
    secret = os.getenv("BOT_WEBHOOK_SECRET", "")
    if secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != secret:
            return web.Response(status=403, text="forbidden")

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="ok")


@routes.get("/set_webhook")
async def set_webhook(request: web.Request):
    bot: Bot = request.app["bot"]
    secret = os.getenv("BOT_WEBHOOK_SECRET", "")
    path = os.getenv("WEBHOOK_PATH", "/webhook")

    base = os.getenv("WEBHOOK_URL") or get_webhook_base_url(request)
    url = base + path

    await bot.set_webhook(
        url=url,
        secret_token=secret or None,
        drop_pending_updates=True,
    )
    return web.Response(text=f"webhook set: {url}")


def create_app() -> web.Application:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    app = web.Application()
    app.add_routes(routes)

    bot = Bot(token=token)
    dp = build_dispatcher()

    app["bot"] = bot
    app["dp"] = dp

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    # Render uses PORT
    port = int(os.getenv("PORT", "10000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)