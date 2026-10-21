"""
main.py
-------
Module containing functionalities for main.
Patched for 100% compliance with FrenzyEx Merchant API v1.0 & production security standards.
"""

# === IMPORTS ===
import asyncio
import json
import logging
import os
import ssl
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.config import (
    BOT_TOKEN,
    ADMIN_IDS,
    WEB_HOST,
    WEB_PORT,
    WEBHOOK_DOMAIN,
    WEBHOOK_PATH,
    USE_WEBHOOK,
    SSL_CERT,
    SSL_PRIV,
)
from database.db_manager import init_db, get_processing_invoices, DB_PATH
from cron.tasks import setup_cron_tasks
from utils.error_handler import error_middleware

# === LOGGING CONFIG ===
logging.basicConfig(level=logging.INFO)

# === CONCURRENCY & STARTUP GUARDS ===
_INVOICE_LOCKS: dict[str, asyncio.Lock] = {}
_STARTUP_COMPLETED: bool = False


def _get_invoice_lock(invoice_id: str) -> asyncio.Lock:
    """Returns a per-invoice asyncio.Lock to prevent concurrent double-processing."""
    if invoice_id not in _INVOICE_LOCKS:
        if len(_INVOICE_LOCKS) > 5000:
            # Prune unlocked entries to bound memory usage
            unlocked_keys = [k for k, lk in _INVOICE_LOCKS.items() if not lk.locked()]
            for k in unlocked_keys[:2500]:
                _INVOICE_LOCKS.pop(k, None)
        _INVOICE_LOCKS[invoice_id] = asyncio.Lock()
    return _INVOICE_LOCKS[invoice_id]


async def _background_confirm_paid(bot: Bot, invoice_id: str, method: str = "FrenzyEx Webhook") -> None:
    """
    Executes payment confirmation, wallet/commission updates, and 3x-UI provisioning
    in the background while holding the per-invoice lock.
    """
    lock = _get_invoice_lock(invoice_id)
    async with lock:
        try:
            from payment.confirm import PaymentConfirmationManager
            pcm = PaymentConfirmationManager(bot)
            success = await pcm.confirm_paid(invoice_id, method=method)
            if not success:
                logging.warning(
                    f"Background confirm_paid returned False for invoice {invoice_id} (already processed or failed)."
                )
        except Exception as e:
            logging.error(f"Unhandled error in _background_confirm_paid for invoice {invoice_id}: {e}", exc_info=True)


async def _background_recover_invoice(bot: Bot, inv: dict) -> None:
    """Safely recovers an unprovisioned invoice on startup with per-invoice locking."""
    invoice_id = str(inv["id"])
    lock = _get_invoice_lock(invoice_id)
    async with lock:
        try:
            from payment.confirm import PaymentConfirmationManager
            pcm = PaymentConfirmationManager(bot)
            await pcm._provision_and_deliver(invoice_id, inv["user_id"], inv)
        except Exception as e:
            logging.error(f"Failed to recover invoice {invoice_id}: {e}", exc_info=True)


# === STARTUP / SHUTDOWN HANDLERS ===
async def on_startup(bot: Bot):
    """Handles on startup (idempotent to prevent duplicate execution in webhook mode)."""
    global _STARTUP_COMPLETED
    if _STARTUP_COMPLETED:
        return
    _STARTUP_COMPLETED = True

    try:
        if USE_WEBHOOK and WEBHOOK_DOMAIN and WEBHOOK_DOMAIN != 'localhost':
            webhook_url = f"https://{WEBHOOK_DOMAIN}{WEBHOOK_PATH}"
            await bot.set_webhook(webhook_url, drop_pending_updates=True)
            logging.info(f"Webhook set to {webhook_url}")
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info("Webhook deleted, using long-polling...")
    except Exception as e:
        logging.error(f"Failed to configure webhook on startup: {e}")

    # Recover PROCESSING / unprovisioned PAID product invoices (Fixes BUG-01)
    try:
        invoices = await get_processing_invoices()
        for inv in invoices:
            inv_dict = dict(inv)
            logging.info(f"Recovering unprovisioned invoice: {inv_dict['id']} (status={inv_dict['status']})")
            asyncio.create_task(_background_recover_invoice(bot, inv_dict))
    except Exception as e:
        logging.error(f"Failed to recover processing invoices: {e}")


async def on_shutdown(bot: Bot):
    """Handles on shutdown and closes shared HTTP resources cleanly."""
    logging.info("Shutting down...")
    try:
        from payment.gateways import FrenzyExGateway
        if hasattr(FrenzyExGateway, "close_http_client"):
            await FrenzyExGateway.close_http_client()
    except Exception as e:
        logging.debug(f"Could not close FrenzyExGateway HTTP client on shutdown: {e}")


# === FRENZYEX IPN HANDLER ===
async def frenzyex_webhook_handler(request: web.Request) -> web.Response:
    """
    Handles incoming FrenzyEx IPN webhooks:
    - Verifies HMAC-SHA256 signature over exact raw HTTP body bytes.
    - Parses JSON directly from verified raw bytes.
    - Validates event, status, order_ref, request_id, currency (TMN), and exact invoice amount.
    - Stores tx_hash, paid_at, and request_id in payment_reports.
    - Dispatches fulfillment asynchronously and returns 200 OK immediately.
    """
    raw_body = await request.read()
    signature = request.headers.get("X-Frenzy-Signature", "").strip()
    header_event = request.headers.get("X-Frenzy-Event", "").strip()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'frenzyex_callback_secret'") as cursor:
            row = await cursor.fetchone()

    if not row or not row[0] or not str(row[0]).strip():
        logging.critical("FrenzyEx Callback Secret is not set in the database.")
        return web.Response(status=500, text="Internal Server Error: Secret not configured")

    frenzyex_callback_secret = str(row[0]).strip()

    from payment.verifiers import PaymentVerifier
    if not PaymentVerifier.verify_frenzyex_signature(raw_body, signature, frenzyex_callback_secret):
        logging.warning(f"Rejected FrenzyEx webhook with invalid signature from IP {request.remote}")
        return web.Response(status=401, text="Unauthorized: Invalid signature")

    try:
        data = json.loads(raw_body.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Payload is not a JSON object")
    except Exception:
        return web.Response(status=400, text="Bad Request: Invalid JSON")

    event_type = data.get("event") or header_event
    status = str(data.get("status") or "").lower().strip()
    order_ref = data.get("order_ref") or data.get("order_id")
    request_id = data.get("request_id") or data.get("payment_id") or ""
    tx_hash = data.get("tx_hash") or ""
    paid_at = data.get("paid_at") or ""
    price_currency = str(data.get("price_currency") or "TMN").upper().strip()
    paid_amount_raw = data.get("amount_toman") if data.get("amount_toman") is not None else data.get("price_amount")

    # Acknowledge non-completion events cleanly with 2xx as required by IPN spec
    if event_type != "payment.completed" or status != "paid":
        return web.json_response({"ok": True})

    if not order_ref or not isinstance(order_ref, str):
        return web.Response(status=400, text="Bad Request: Missing order_ref")

    order_ref = order_ref.strip()
    lock = _get_invoice_lock(order_ref)

    async with lock:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id, plan_id, status, final_amount FROM invoices WHERE id = ?",
                (order_ref,)
            ) as cursor:
                inv = await cursor.fetchone()

            if not inv:
                logging.warning(f"FrenzyEx webhook received for non-existent order_ref: {order_ref}")
                return web.Response(status=404, text="Order not found")

            # Idempotency guard: if already in processing or completed state, return 200 OK
            if inv["status"] != "pending":
                return web.json_response({"ok": True})

            # Validate currency
            if price_currency != "TMN":
                logging.critical(
                    f"FrenzyEx currency mismatch for invoice {order_ref}: expected TMN, got {price_currency}"
                )
                return web.Response(status=400, text="Bad Request: Currency mismatch")

            # Validate paid amount against invoice final_amount
            expected_amount = int(inv["final_amount"] or 0)
            if paid_amount_raw is not None:
                try:
                    paid_amount_int = int( round(float(paid_amount_raw)) )
                except (ValueError, TypeError):
                    return web.Response(status=400, text="Bad Request: Invalid amount format")

                if paid_amount_int != expected_amount:
                    logging.critical(
                        f"FrenzyEx amount mismatch for invoice {order_ref}: "
                        f"expected {expected_amount}, received {paid_amount_int}"
                    )
                    return web.Response(status=400, text="Bad Request: Amount mismatch")

            # Validate request_id against stored gateway_request_id (if recorded)
            async with db.execute(
                "SELECT id, gateway_request_id FROM payment_reports WHERE invoice_id = ? ORDER BY id DESC LIMIT 1",
                (order_ref,)
            ) as pr_cursor:
                pr_row = await pr_cursor.fetchone()

            if pr_row and pr_row["gateway_request_id"] and request_id:
                if str(pr_row["gateway_request_id"]).strip() != str(request_id).strip():
                    logging.critical(
                        f"FrenzyEx request_id mismatch for invoice {order_ref}: "
                        f"expected {pr_row['gateway_request_id']}, received {request_id}"
                    )
                    return web.Response(status=400, text="Bad Request: request_id mismatch")

            # Persist reconciliation & audit metadata (request_id, tx_hash, paid_at)
            if pr_row:
                await db.execute(
                    """
                    UPDATE payment_reports
                    SET status = 'paid',
                        gateway_request_id = COALESCE(NULLIF(gateway_request_id, ''), ?),
                        crypto_hash = COALESCE(NULLIF(?, ''), crypto_hash),
                        receipt_time = COALESCE(NULLIF(?, ''), receipt_time)
                    WHERE invoice_id = ?
                    """,
                    (str(request_id), str(tx_hash), str(paid_at), order_ref),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO payment_reports
                        (user_id, invoice_id, amount, payment_method, status, crypto_hash, gateway_request_id, receipt_time)
                    VALUES (?, ?, ?, 'frenzyex', 'paid', ?, ?, ?)
                    """,
                    (inv["user_id"], order_ref, expected_amount, str(tx_hash), str(request_id), str(paid_at)),
                )

            await db.commit()

    # Offload fulfillment, wallet credits, and Telegram notifications to background task
    bot = request.app["bot"]
    asyncio.create_task(_background_confirm_paid(bot, order_ref, method="FrenzyEx Webhook"))

    return web.json_response({"ok": True})


async def run_web_server(bot: Bot, dp: Dispatcher):
    """Runs aiohttp web server concurrently with error_middleware and SSL support (Fixes BUG-05 & BUG-10)."""
    app = web.Application(middlewares=[error_middleware])
    app['bot'] = bot
    app.router.add_post('/ipn/frenzyex', frenzyex_webhook_handler)

    # Register Telegram webhook endpoint so /webhook/main is always valid
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    ssl_context = None
    if SSL_CERT and SSL_PRIV and os.path.exists(SSL_CERT) and os.path.exists(SSL_PRIV):
        try:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=SSL_CERT, keyfile=SSL_PRIV)
            logging.info(f"Loaded SSL certificates from {SSL_CERT}")
        except Exception as e:
            logging.error(f"Failed to load SSL certificates ({SSL_CERT}): {e}")
            ssl_context = None

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT, ssl_context=ssl_context)
    await site.start()
    scheme = "https" if ssl_context else "http"
    logging.info(f"Web server started on {scheme}://{WEB_HOST}:{WEB_PORT}")
    return runner


# === MAIN ASYNC INITIALIZATION ===
async def main():
    """Handles main."""
    await init_db()

    # === SYNC ADMIN IDS FROM DB ===
    try:
        from database.db_manager import get_db_admin_ids
        db_admin_ids = await get_db_admin_ids()
        for aid in db_admin_ids:
            if aid not in ADMIN_IDS:
                ADMIN_IDS.append(aid)
        logging.info(f"Loaded {len(ADMIN_IDS)} admin ID(s): {ADMIN_IDS}")
    except Exception as e:
        logging.warning(f"Could not load admins from DB: {e}")

    # === BOT SETUP ===
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # === MIDDLEWARES ===
    from bot.middlewares import ForceJoinMiddleware
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # === ROUTER REGISTRATION ===
    from bot.routers import (
        admin_router,
        admin_settings_router,
        admin_finance_router,
        admin_users_router,
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
        agent_support_router,
        agent_router,
        admin_agent_router,
    )

    dp.include_router(user_router)
    dp.include_router(agent_router)
    dp.include_router(admin_router)
    dp.include_router(admin_agent_router)
    dp.include_router(admin_reports_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_finance_router)
    dp.include_router(admin_users_router)
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
    await run_web_server(bot, dp)

    # === START POLLING OR KEEP RUNNING FOR WEBHOOK ===
    if USE_WEBHOOK and WEBHOOK_DOMAIN and WEBHOOK_DOMAIN != 'localhost':
        logging.info("Running in Webhook mode...")
        await on_startup(bot)
        await asyncio.Event().wait()
    else:
        logging.info("Starting bot polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())