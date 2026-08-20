"""
This module corresponds to the 'cron/tasks.py' branch in the candy_architecture.md map.
Contains async background loops for DB cleanup, broadcasting, and payment checks (including expiring USDT/GRAM invoices).
Lottery feature removed.
"""
# === IMPORTS ===
import asyncio
import logging
import aiosqlite
from database.db_manager import DB_PATH
from bot.routers import checkout

# === BACKGROUND TASK: PAYMENT CHECK ===
async def cron_payment_check(bot=None):
    """
    Background loop to check pending payments (plisio, crypto, cards).
    Replaces old PHP /cronbot logic for payments.
    Runs every 60 seconds.
    """
    import time
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                current_time = int(time.time())
                
                # Check for expired offline payments (USDT / GRAM)
                async with db.execute(
                    "SELECT * FROM payment_reports WHERE status = 'Unpaid' AND payment_method IN ('usdt offline', 'gram offline') AND created_at < datetime('now', '-1 hour')"
                ) as cursor:
                    expired_reports = await cursor.fetchall()
                    
                for report in expired_reports:
                    logging.info(f"Expiring offline payment report {report['invoice_id']}")
                    # Update status to expire
                    await db.execute("UPDATE payment_reports SET status = 'expire' WHERE invoice_id = ?", (report['invoice_id'],))
                    
                    # Also expire the main invoice
                    await db.execute("UPDATE invoices SET status = 'expired' WHERE id = ?", (report['invoice_id'],))
                    # Send the exact expiration notification
                    if bot:
                        try:
                            await bot.send_message(report['user_id'], 'فاکتور خرید شما منقضی شد. برای صدور مجدد اقدام کنید.')
                        except Exception:
                            pass
                            
                await db.commit()
        except Exception as e:
            logging.error(f"Cron Payment Check Error: {e}")
        await asyncio.sleep(60)

# === BACKGROUND TASK: DB CLEANUP ===
async def cron_database_cleanup():
    """
    Daily task to clean up old abandoned invoices and clear stale cache.
    Replaces generic legacy cron sweeps.
    Runs every 86400 seconds (24h).
    """
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Cleanup old pending invoices older than 24 hours
                await db.execute("DELETE FROM invoices WHERE status = 'pending' AND created_at < datetime('now', '-1 day')")
                await db.commit()
                logging.info("Executed daily database cleanup")
        except Exception as e:
            logging.error(f"Cron DB Cleanup Error: {e}")
        await asyncio.sleep(86400)

# === BACKGROUND TASK: NOTIFICATIONS & BROADCAST ===
async def cron_broadcast():
    """
    Background loop to dispatch queued broadcast messages and notifications to users.
    Replaces old PHP `sendmessage` and `notifications` cronbots.
    Runs every 30 seconds.
    """
    while True:
        try:
            # Broadcast queue dispatch simulation
            # The actual send_message logic will tie into aiogram bot instance
            logging.debug("Running broadcast check")
        except Exception as e:
            logging.error(f"Cron Broadcast Error: {e}")
        await asyncio.sleep(30)

# === BACKGROUND TASK: HOUSEKEEPING ===
async def cron_housekeeping():
    """
    Background loop to manage expiring discounts, gift codes, and agent statuses.
    Replaces discount_expire.php, expireagent.php, gift.php.
    Runs every hour.
    """
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Expire past discount codes
                await db.execute("DELETE FROM discount_codes WHERE expiration_date < datetime('now')")
                # Expire past gift codes
                await db.execute("DELETE FROM gift_codes WHERE expiration_date < datetime('now')")
                
                # Agents whose status is no longer valid or have no affiliates can be downgraded
                await db.execute("UPDATE users SET agent = 'f' WHERE affiliatescount = 0 AND agent = 't'")
                await db.commit()
                logging.debug("Cron Housekeeping completed.")
        except Exception as e:
            logging.error(f"Cron Housekeeping Error: {e}")
        await asyncio.sleep(3600)

# === CRON SETUP ===
def setup_cron_tasks(bot=None, loop=None):
    """Handles setup cron tasks."""
    if loop is None:
        loop = asyncio.get_event_loop()
    loop.create_task(cron_payment_check(bot))
    loop.create_task(cron_database_cleanup())
    loop.create_task(cron_broadcast())
    loop.create_task(cron_housekeeping())
