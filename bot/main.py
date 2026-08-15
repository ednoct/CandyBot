# === IMPORTS ===
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import BOT_TOKEN, WEB_HOST, WEB_PORT, WEBHOOK_DOMAIN
from database.db_manager import init_db
from bot.routers import checkout_router, admin_router, user_router, support_router
from web.panel_api import init_web_app
from cron.tasks import setup_cron_tasks

# === LOGGING CONFIG ===
logging.basicConfig(level=logging.INFO)

# === WEBHOOK PATH ===
WEBHOOK_PATH = "/webhook/main"
WEBHOOK_URL = f"https://{WEBHOOK_DOMAIN}{WEBHOOK_PATH}"

# === STARTUP / SHUTDOWN HANDLERS ===
async def on_startup(bot: Bot):
    try:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook (might be rate-limited): {e}")

async def on_shutdown(bot: Bot):
    logging.info("Shutting down... deleting webhook.")
    await bot.delete_webhook()

# === MAIN ASYNC INITIALIZATION ===
async def main():
    # === INIT DATABASE ===
    await init_db()
    
    # === BOT SETUP ===
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Register startup and shutdown callbacks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # === ROUTER REGISTRATION ===
    from bot.routers import (
        admin_router, 
        admin_settings_router,
        admin_finance_router,
        admin_users_router,
        admin_shop_router,
        admin_plans_router,
        admin_reports_router,
        checkout_router,
        payment_router,
        support_router, 
        user_router
    )
    
    dp.include_router(admin_router)
    dp.include_router(admin_reports_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_finance_router)
    dp.include_router(admin_users_router)
    dp.include_router(admin_shop_router)
    dp.include_router(admin_plans_router)
    dp.include_router(checkout_router)
    dp.include_router(payment_router)
    dp.include_router(support_router)
    dp.include_router(user_router)
    
    # === CRON TASKS ===
    setup_cron_tasks(bot)
    
    # === WEB SERVER START ===
    web_app = await init_web_app()
    
    # Link aiogram to aiohttp web server
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(web_app, path=WEBHOOK_PATH)
    setup_application(web_app, dp, bot=bot)

    # Start aiohttp server
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    logging.info(f"Web API & Webhook running on http://{WEB_HOST}:{WEB_PORT}")
    
    # Set Telegram Webhook
    await on_startup(bot)

    # Keep the event loop running
    try:
        await asyncio.Event().wait()
    finally:
        await on_shutdown(bot)

# === ENTRY POINT ===
if __name__ == "__main__":
    asyncio.run(main())