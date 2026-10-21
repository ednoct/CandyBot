"""
main.py
-------
Module containing functionalities for main.
Patched for 100% compliance with FrenzyEx Merchant API v1.0 & production security standards.
"""

# === IMPORTS ===
import asyncio
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
import os
import ssl
import time
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
from payment.confirm import PaymentConfirmationManager, get_invoice_lock
from payment.verifiers import PaymentVerifier
from utils.error_handler import error_middleware

# === LOGGING CONFIG ===
logging.basicConfig(level=logging.INFO)

# === CONCURRENCY, TASK TRACKING & SECRET CACHE ===
_STARTUP_COMPLETED: bool = False
_ACTIVE_BG_TASKS: set[asyncio.Task] = set()
_SECRET_CACHE: tuple[str, float] = ("", 0.0)
MAX_WEBHOOK_BODY_BYTES: int = 65536  # 64 KB cap against OOM DoS


def _get_invoice_lock(invoice_id: str):
    """Returns the shared process-wide reentrant lock for an invoice."""
    return get_invoice_lock(invoice_id)


def _spawn_background_task(coro) -> asyncio.Task:
    """Spawns an async task and retains a strong reference until completion."""
    task = asyncio.create_task(coro)
    _ACTIVE_BG_TASKS.add(task)
    task.add_done_callback(_ACTIVE_BG_TASKS.discard)
    return task


async def _get_cached_callback_secret() -> str:
    """Fetches frenzyex_callback_secret with a 60-second monotonic cache to prevent DB DoS."""
    global _SECRET_CACHE
    cached_secret, expires_at = _SECRET_CACHE
    now = time.monotonic()
    if cached_secret and now < expires_at:
        return cached_secret

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout = 5000;")
        async with db.execute("SELECT value FROM settings WHERE key = 'frenzyex_callback_secret'") as cursor:
            row = await cursor.fetchone()

    secret = str(row[0]).strip() if (row and row[0]) else ""
    if secret:
        _SECRET_CACHE = (secret, now + 60.0)
    return secret


def _verify_signature_safe(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Verifies HMAC-SHA256 signature over exact raw HTTP body bytes safely.
    Catches TypeError/UnicodeEncodeError on malformed non-ASCII headers so 401 is returned instead of 500.
    """
    if not raw_body or not signature or not secret:
        return False
    try:
        expected_bytes = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest().encode("ascii")
        received_bytes = signature.strip().lower().encode("ascii")
        return hmac.compare_digest(expected_bytes, received_bytes)
    except Exception:
        return False


async def _background_confirm_paid(bot: Bot, invoice_id: str, method: str = "FrenzyEx Webhook") -> None:
    """
    Executes payment confirmation, wallet/commission updates, and 3x-UI provisioning
    in the background while holding the shared per-invoice lock.
    """
    lock = _get_invoice_lock(invoice_id)
    async with lock:
        try:
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
            _spawn_background_task(_background_recover_invoice(bot, inv_dict))
    except Exception as e:
        logging.error(f"Failed to recover processing invoices: {e}")


async def on_shutdown(bot: Bot):
    """Handles on shutdown, drains active fulfillment tasks, and closes shared HTTP resources cleanly."""
    logging.info("Shutting down...")
    if _ACTIVE_BG_TASKS:
        logging.info(f"Waiting for {len(_ACTIVE_BG_TASKS)} active background task(s) to finish...")
        try:
            await asyncio.wait(list(_ACTIVE_BG_TASKS), timeout=10.0)
        except Exception as e:
            logging.debug(f"Error while draining background tasks on shutdown: {e}")

    try:
        from payment.gateways import FrenzyExGateway
        if hasattr(FrenzyExGateway, "close_http_client"):
            await FrenzyExGateway.close_http_client()
    except Exception as e:
        logging.debug(f"Could not close FrenzyExGateway HTTP client on shutdown: {e}")


# === FRENZYEX IPN HANDLER ===
async def frenzyex_webhook_handler(request: web.Request) -> web.Response:
    """
    Handles incoming FrenzyEx IPN webhooks per Section 08, 09 & 10 of the API Guide:
    - Rejects missing signatures or oversized payloads (>64 KB) before DB access.
    - Verifies HMAC-SHA256 signature over exact raw HTTP body bytes.
    - Parses JSON directly from verified raw bytes.
    - Enforces presence and exact match of event, status, order_ref, request_id, currency (TMN), and invoice amount.
    - Stores tx_hash, paid_at, and request_id in payment_reports.
    - Dispatches fulfillment asynchronously and returns 200 OK immediately.
    """
    signature = request.headers.get("X-Frenzy-Signature", "").strip()
    header_event = request.headers.get("X-Frenzy-Event", "").strip()

    if not signature:
        return web.Response(status=401, text="Unauthorized: Missing signature")

    if request.content_length and request.content_length > MAX_WEBHOOK_BODY_BYTES:
        return web.Response(status=413, text="Payload Too Large")

    raw_body = await request.content.read(MAX_WEBHOOK_BODY_BYTES + 1)
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        return web.Response(status=413, text="Payload Too Large")

    frenzyex_callback_secret = await _get_cached_callback_secret()
    if not frenzyex_callback_secret:
        logging.critical("FrenzyEx Callback Secret is not set in the database.")
        return web.Response(status=500, text="Internal Server Error: Secret not configured")

    if not _verify_signature_safe(raw_body, signature, frenzyex_callback_secret):
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

    # Acknowledge non-completion events cleanly with 2xx as required by IPN spec
    if event_type != "payment.completed" or status != "paid":
        return web.json_response({"ok": True})

    order_ref = data.get("order_ref") or data.get("order_id")
    request_id = str(data.get("request_id") or data.get("payment_id") or "").strip()
    tx_hash = str(data.get("tx_hash") or "").strip()
    paid_at = str(data.get("paid_at") or "").strip()
    price_currency = str(data.get("price_currency") or "").upper().strip()
    paid_amount_raw = data.get("amount_toman") if data.get("amount_toman") is not None else data.get("price_amount")

    if not order_ref or not isinstance(order_ref, str):
        return web.Response(status=400, text="Bad Request: Missing order_ref")
    if not request_id:
        return web.Response(status=400, text="Bad Request: Missing request_id")
    if paid_amount_raw is None:
        return web.Response(status=400, text="Bad Request: Missing payment amount")

    order_ref = order_ref.strip()

    try:
        paid_amount_dec = Decimal(str(paid_amount_raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return web.Response(status=400, text="Bad Request: Invalid amount format")

    lock = _get_invoice_lock(order_ref)
    async with lock:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout = 5000;")
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

            # Validate currency (default to TMN only if price_currency was explicitly omitted by legacy endpoint)
            effective_ccy = price_currency or "TMN"
            if effective_ccy != "TMN":
                logging.critical(
                    f"FrenzyEx currency mismatch for invoice {order_ref}: expected TMN, got {effective_ccy}"
                )
                return web.Response(status=400, text="Bad Request: Currency mismatch")

            # Validate paid amount against invoice final_amount using exact Decimal arithmetic
            expected_amount_dec = Decimal(int(inv["final_amount"] or 0))
            if paid_amount_dec != expected_amount_dec:
                logging.critical(
                    f"FrenzyEx amount mismatch for invoice {order_ref}: "
                    f"expected {expected_amount_dec}, received {paid_amount_dec}"
                )
                return web.Response(status=400, text="Bad Request: Amount mismatch")

            # Validate request_id against stored gateway_request_id
            async with db.execute(
                "SELECT id, gateway_request_id, status FROM payment_reports WHERE invoice_id = ? ORDER BY id DESC LIMIT 1",
                (order_ref,)
            ) as pr_cursor:
                pr_row = await pr_cursor.fetchone()

            if pr_row and pr_row["gateway_request_id"]:
                if str(pr_row["gateway_request_id"]).strip() != request_id:
                    logging.critical(
                        f"FrenzyEx request_id mismatch for invoice {order_ref}: "
                        f"expected {pr_row['gateway_request_id']}, received {request_id}"
                    )
                    return web.Response(status=400, text="Bad Request: request_id mismatch")

            # If another webhook already marked payment_reports as paid and queued confirmation, return 200 OK
            if pr_row and pr_row["status"] == "paid":
                return web.json_response({"ok": True})

            # Persist reconciliation & audit metadata (request_id, tx_hash, paid_at)
            if pr_row:
                await db.execute(
                    """
                    UPDATE payment_reports
                    SET status = 'paid',
                        gateway_request_id = COALESCE(NULLIF(gateway_request_id, ''), ?),
                        crypto_hash = COALESCE(NULLIF(?, ''), crypto_hash),
                        receipt_time = COALESCE(NULLIF(?, ''), receipt_time)
                    WHERE id = ?
                    """,
                    (request_id, tx_hash, paid_at, pr_row["id"]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO payment_reports
                        (user_id, invoice_id, amount, payment_method, status, crypto_hash, gateway_request_id, receipt_time)
                    VALUES (?, ?, ?, 'frenzyex', 'paid', ?, ?, ?)
                    """,
                    (inv["user_id"], order_ref, int(expected_amount_dec), tx_hash, request_id, paid_at),
                )

            await db.commit()

    # Offload fulfillment, wallet credits, and Telegram notifications to background task
    bot = request.app["bot"]
    _spawn_background_task(_background_confirm_paid(bot, order_ref, method="FrenzyEx Webhook"))

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

# === START POLLING OR KEEP RUNNING FOR WEBHOOK
    if USE_WEBHOOK and WEBHOOK_DOMAIN and WEBHOOK_DOMAIN != 'localhost':
        logging.info("Running in Webhook mode...")
        await asyncio.Event().wait()
    else:
        logging.info("Starting bot polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())