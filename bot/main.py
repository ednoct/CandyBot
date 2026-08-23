"""
main.py
-------
Module containing functionalities for main.
"""
# === IMPORTS ===
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import BOT_TOKEN
from database.db_manager import init_db
from bot.routers import checkout_router, admin_router, user_router, support_router
from cron.tasks import setup_cron_tasks
from aiohttp import web
from bot.config import WEB_HOST, WEB_PORT

# === LOGGING CONFIG ===
logging.basicConfig(level=logging.INFO)



# === STARTUP / SHUTDOWN HANDLERS ===
async def on_startup(bot: Bot):
    """Handles on startup."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Webhook deleted, starting long-polling...")
    except Exception as e:
        logging.error(f"Failed to delete webhook: {e}")

    # Recover PROCESSING invoices
    try:
        from payment.confirm import PaymentConfirmationManager
        import aiosqlite
        from database.db_manager import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM invoices WHERE status = 'processing'") as cursor:
                invoices = await cursor.fetchall()
        
        pcm = PaymentConfirmationManager(bot)
        for inv in invoices:
            logging.info(f"Recovering PROCESSING invoice: {inv['id']}")
            # Use loop.create_task to not block startup
            asyncio.create_task(pcm._provision_and_deliver(inv['id'], inv['user_id'], inv))
    except Exception as e:
        logging.error(f"Failed to recover processing invoices: {e}")

async def on_shutdown(bot: Bot):
    """Handles on shutdown."""
    logging.info("Shutting down...")

# === FRENZYEX IPN HANDLER ===
async def frenzyex_webhook_handler(request: web.Request):
    """Handles incoming FrenzyEx webhooks."""
    raw_body = await request.read()
    signature = request.headers.get("X-Frenzy-Signature", "")
    event_type = request.headers.get("X-Frenzy-Event", "")
    
    from database.db_manager import DB_PATH
    import aiosqlite
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'frenzyex_callback_secret'") as cursor:
            row = await cursor.fetchone()
            
    if not row or not row[0]:
        logging.critical("FrenzyEx Callback Secret is not set in the database.")
        return web.Response(status=500, text="Internal Server Error: Secret not configured")
        
    frenzyex_callback_secret = row[0]
    
    from payment.verifiers import PaymentVerifier
    if not PaymentVerifier.verify_frenzyex_signature(raw_body, signature, frenzyex_callback_secret):
        return web.Response(status=401, text="Unauthorized: Invalid signature")
        
    try:
        data = await request.json()
    except:
        return web.Response(status=400, text="Bad Request: Invalid JSON")
        
    if event_type == "payment.completed" and data.get("status") == "paid":
        order_ref = data.get("order_ref")
        
        from database.db_manager import DB_PATH
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, status FROM invoices WHERE id = ?", (order_ref,)) as cursor:
                inv = await cursor.fetchone()
                
        if inv:
            if inv['status'] != 'pending':
                # Already processed
                return web.json_response({"ok": True})
                
            from payment.confirm import PaymentConfirmationManager
            bot = request.app['bot']
            pcm = PaymentConfirmationManager(bot)
            success = await pcm.confirm_paid(order_ref, method="FrenzyEx Webhook")
            if success:
                return web.json_response({"ok": True})
            else:
                return web.Response(status=500, text="Internal Server Error during provisioning")
        else:
            return web.Response(status=404, text="Order not found")
            
    return web.json_response({"ok": True})

async def run_web_server(bot: Bot):
    """Runs aiohttp web server concurrently."""
    app = web.Application()
    app['bot'] = bot
    app.router.add_post('/ipn/frenzyex', frenzyex_webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    logging.info(f"Web server started on {WEB_HOST}:{WEB_PORT}")

# === MAIN ASYNC INITIALIZATION ===
async def main():
    # === INIT DATABASE ===
    """Handles main."""
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
        admin_xui_router,
        admin_discounts_router,
        admin_free_trial_router,
        checkout_router,
        payment_router,
        support_router, 
        user_router,
        user_free_trial_router,
        admin_support_router,
        agent_support_router
    )
    
    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(admin_reports_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_finance_router)
    dp.include_router(admin_users_router)
    dp.include_router(admin_shop_router)
    dp.include_router(admin_xui_router)
    dp.include_router(admin_discounts_router)
    dp.include_router(admin_free_trial_router)
    dp.include_router(admin_plans_router)
    dp.include_router(checkout_router)
    dp.include_router(payment_router)
    dp.include_router(support_router)
    dp.include_router(user_free_trial_router)
    dp.include_router(admin_support_router)
    dp.include_router(agent_support_router)
    
    # === CRON TASKS ===
    setup_cron_tasks(bot)
    
    # === START WEB SERVER ===
    await run_web_server(bot)
    
    # === START POLLING ===
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)

# === ENTRY POINT ===
if __name__ == "__main__":
    asyncio.run(main())