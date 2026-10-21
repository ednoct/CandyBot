"""
cron/tasks.py
-------------
Contains async background loops for:
- Pending FrenzyEx active polling recovery & offline USDT/GRAM expiration (cron_payment_check)
- License traffic/time low alerts (cron_license_stats_check)
- Automatic cleanup of expired 3x-UI licenses >2 days past expiry from panel & DB (cron_expired_licenses_cleanup)
- Daily abandoned invoice expiration & nightly DB backup report (cron_database_cleanup)
- Broadcast queue processing (cron_broadcast)
- Housekeeping & bi-weekly DB optimization (cron_housekeeping, cron_biweekly_cleanup)
"""
# === IMPORTS ===
import asyncio
import logging
import aiosqlite
from database.db_manager import DB_PATH
from bot.services.sub_stats import fetch_sub_stats
from utils.backup import create_database_backup
from bot.services.notifications import NotificationService
from aiogram.types import FSInputFile
from database import db_manager
from payment.confirm import PaymentConfirmationManager
from payment.verifiers import PaymentVerifier


# === BACKGROUND TASK: LICENSE STATS ALERTS ===
async def cron_license_stats_check(bot=None):
    """
    Background loop to check license stats via sub-link and alert users
    when their traffic drops below 10% or they have less than 3 days left.
    Runs every 6 hours (21600 seconds).
    """
    if not bot:
        return

    while True:
        try:
            licenses = []
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA busy_timeout = 5000;")
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT l.id, l.user_id, l.sub_id, p.sub_link, l.alert_sent "
                    "FROM xui_licenses l "
                    "JOIN xui_panels p ON l.panel_id = p.id "
                    "WHERE p.sub_link IS NOT NULL AND p.sub_link != '' AND l.alert_sent = 0"
                ) as cursor:
                    rows = await cursor.fetchall()
                    licenses = [dict(r) for r in rows]

            alerted_lic_ids = []
            for lic in licenses:
                stats = await fetch_sub_stats(lic['sub_link'], lic['sub_id'])
                if not stats:
                    continue

                needs_alert = False
                reason = ""

                if not stats['is_unlimited_traffic'] and stats['fraction'] < 0.10:
                    needs_alert = True
                    reason = f"حجم باقی‌مانده شما به کمتر از ۱۰ درصد ({stats['remaining_gb']:.2f} GB) رسیده است."
                elif not stats['is_unlimited_time'] and stats['days_left'] < 3.0:
                    needs_alert = True
                    reason = f"اعتبار زمانی شما کمتر از ۳ روز ({int(stats['days_left'])} روز) است."

                if needs_alert:
                    try:
                        await bot.send_message(
                            lic['user_id'],
                            f"⚠️ <b>هشدار رو به اتمام بودن سرویس</b>\n\nکاربر گرامی، {reason}\nلطفاً برای تمدید سرویس خود اقدام کنید.",
                            parse_mode="HTML"
                        )
                        alerted_lic_ids.append(lic['id'])
                    except Exception as e:
                        logging.error(f"Failed to send alert to user {lic['user_id']}: {e}")

            if alerted_lic_ids:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    placeholders = ",".join("?" for _ in alerted_lic_ids)
                    await db.execute(f"UPDATE xui_licenses SET alert_sent = 1 WHERE id IN ({placeholders})", alerted_lic_ids)
                    await db.commit()

        except Exception as e:
            logging.error(f"Cron License Stats Check Error: {e}")

        await asyncio.sleep(21600)  # 6 hours


# === BACKGROUND TASK: EXPIRED XUI LICENSES CLEANUP (>2 DAYS PAST EXPIRY) ===
async def cron_expired_licenses_cleanup():
    """
    Periodically checks for XUI licenses that have been expired for at least 2 days (48 hours),
    removes them from the connected 3x-UI panel first, and then deletes them from the bot DB.
    Runs every 6 hours (21600 seconds).
    """
    while True:
        try:
            await db_manager.cleanup_expired_xui_licenses(grace_days=2)
        except Exception as e:
            logging.error(f"Cron Expired Licenses Cleanup Error: {e}", exc_info=True)
        await asyncio.sleep(21600)  # 6 hours


# === BACKGROUND TASK: PAYMENT CHECK ===
async def cron_payment_check(bot=None):
    """
    Background loop to check pending payments:
    1. Polls pending FrenzyEx payment requests to recover missed IPNs or mark expired/canceled orders.
    2. Expires stale offline payments (USDT / GRAM) after 24 hours.
    Runs every 60 seconds.
    """
    while True:
        try:
            # 1. Poll pending FrenzyEx gateway requests (recovery & 60m expiration lifecycle)
            if bot:
                try:
                    pcm = PaymentConfirmationManager(bot)
                    await PaymentVerifier.process_pending_invoices(pcm)
                except Exception as fe_err:
                    logging.error(f"Cron FrenzyEx Polling Error: {fe_err}", exc_info=True)

            # 2. Expire stale offline payments (USDT / GRAM) older than 24 hours
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA busy_timeout = 5000;")
                db.row_factory = aiosqlite.Row

                expired_invoice_ids = set()
                async with db.execute(
                    "SELECT * FROM payment_reports "
                    "WHERE status IN ('Unpaid', 'pending') "
                    "AND payment_method IN ('usdt offline', 'gram offline') "
                    "AND created_at < datetime('now', '-24 hours')"
                ) as cursor:
                    expired_reports = await cursor.fetchall()

                for report in expired_reports:
                    inv_id = report['invoice_id']
                    expired_invoice_ids.add(inv_id)
                    logging.info(f"Expiring offline payment report {inv_id}")
                    await db.execute(
                        "UPDATE payment_reports SET status = 'expire' WHERE invoice_id = ? AND status IN ('Unpaid', 'pending')",
                        (inv_id,)
                    )
                    cur_inv = await db.execute(
                        "UPDATE invoices SET status = 'expired' WHERE id = ? AND status = 'pending'",
                        (inv_id,)
                    )
                    if bot and cur_inv.rowcount > 0:
                        try:
                            await bot.send_message(report['user_id'], 'فاکتور خرید شما منقضی شد. برای صدور مجدد اقدام کنید.')
                        except Exception:
                            pass

                # Also expire any direct/orphan pending offline invoices older than 24 hours
                async with db.execute(
                    "SELECT * FROM invoices "
                    "WHERE status = 'pending' "
                    "AND payment_method IN ('usdt', 'gram') "
                    "AND created_at < datetime('now', '-24 hours')"
                ) as cursor:
                    expired_invoices = await cursor.fetchall()

                for inv in expired_invoices:
                    inv_id = inv['id']
                    if inv_id in expired_invoice_ids:
                        continue
                    logging.info(f"Expiring offline invoice {inv_id}")
                    cur_inv = await db.execute(
                        "UPDATE invoices SET status = 'expired' WHERE id = ? AND status = 'pending'",
                        (inv_id,)
                    )
                    await db.execute(
                        "UPDATE payment_reports SET status = 'expire' WHERE invoice_id = ? AND status IN ('Unpaid', 'pending')",
                        (inv_id,)
                    )
                    if bot and cur_inv.rowcount > 0:
                        try:
                            await bot.send_message(inv['user_id'], 'فاکتور خرید شما منقضی شد. برای صدور مجدد اقدام کنید.')
                        except Exception:
                            pass

                await db.commit()
        except Exception as e:
            logging.error(f"Cron Payment Check Error: {e}")
        await asyncio.sleep(60)


# === BACKGROUND TASK: DB CLEANUP & NIGHTLY REPORT ===
async def cron_database_cleanup(bot=None):
    """
    Daily task to mark abandoned pending invoices (>24h) as expired, generate stats,
    backup DB, and send nightly report.
    Runs every 86400 seconds (24h).
    """
    import os
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA busy_timeout = 5000;")
                await db.execute(
                    "UPDATE invoices SET status = 'expired' "
                    "WHERE status = 'pending' AND created_at < datetime('now', '-1 day')"
                )
                await db.execute(
                    "UPDATE payment_reports SET status = 'expire' "
                    "WHERE status IN ('pending', 'Unpaid') AND created_at < datetime('now', '-1 day')"
                )
                await db.commit()
                logging.info("Executed daily abandoned invoice expiration sweep")

            if bot:
                from datetime import datetime
                now = datetime.now()
                start = now.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
                stats = await db_manager.get_bot_stats("WHERE created_at >= ?", (start,))

                stats_text = (
                    "🌙 **گزارش روزانه و بکاپ شبانه**\n━━━━━━━━━━━━━━━━━━\n"
                    f"👥 ثبت نام امروز: {stats['users']} نفر\n"
                    f"🛍 سفارشات امروز: {stats['orders']} عدد\n"
                    f"🔑 اکانت‌های تست: {stats['tests']} عدد\n"
                    f"💸 فروش امروز: {stats['sales']:,} تومان\n"
                )

                zip_path = await create_database_backup()

                notif_service = NotificationService(bot)
                if zip_path and os.path.exists(zip_path):
                    await notif_service.send_report(
                        topic_key="nightly_report",
                        text=stats_text,
                        file=FSInputFile(zip_path, filename=os.path.basename(zip_path)),
                        caption=stats_text
                    )
                else:
                    await notif_service.send_report(
                        topic_key="nightly_report",
                        text=stats_text + "\n\n⚠️ خطا در تهیه فایل بکاپ دیتابیس."
                    )

        except Exception as e:
            logging.error(f"Cron DB Cleanup & Nightly Report Error: {e}")
        await asyncio.sleep(86400)


# === BACKGROUND TASK: NOTIFICATIONS & BROADCAST ===
async def cron_broadcast(bot=None):
    """
    Background loop to dispatch queued broadcast messages and notifications to users.
    Runs every 30 seconds.
    """
    from bot.services.broadcast import BroadcastService
    while True:
        try:
            if bot:
                service = BroadcastService(bot)
                await service.process_queue()
        except Exception as e:
            logging.error(f"Cron Broadcast Error: {e}")
        await asyncio.sleep(30)


# === BACKGROUND TASK: HOUSEKEEPING ===
async def cron_housekeeping():
    """
    Background loop to manage expiring discounts, gift codes, and agent statuses.
    Runs every hour.
    """
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA busy_timeout = 5000;")
                await db.execute("DELETE FROM discount_codes WHERE expiration_date < datetime('now')")
                await db.execute("DELETE FROM gift_codes WHERE expiration_date < datetime('now')")
                await db.execute("UPDATE users SET agent = 'f' WHERE affiliatescount = 0 AND agent = 't'")
                await db.commit()
                logging.debug("Cron Housekeeping completed.")
        except Exception as e:
            logging.error(f"Cron Housekeeping Error: {e}")
        await asyncio.sleep(3600)


# === BACKGROUND TASK: BI-WEEKLY EXPIRED DATA CLEANUP ===
async def cron_biweekly_cleanup(bot=None):
    """
    Bi-weekly background loop to clean up expired tickets, licenses (>2d expired), and old invoices.
    """
    import time
    import json
    while True:
        try:
            last_cleanup = await db_manager.get_setting("last_biweekly_cleanup")
            interval_days = int(await db_manager.get_setting("biweekly_cleanup_interval_days", "14"))
            interval_seconds = interval_days * 86400
            now = int(time.time())

            should_run = False
            if not last_cleanup:
                await db_manager.set_setting("last_biweekly_cleanup", str(now))
                should_run = False
            else:
                try:
                    last_time = int(last_cleanup)
                    if (now - last_time) >= interval_seconds:
                        should_run = True
                except ValueError:
                    await db_manager.set_setting("last_biweekly_cleanup", str(now))
                    should_run = False

            if should_run:
                logging.info("Starting bi-weekly database cleanup of expired tickets, licenses, and invoices...")
                result = await db_manager.cleanup_expired_data(retention_days=interval_days)
                await db_manager.set_setting("last_biweekly_cleanup", str(now))
                await db_manager.set_setting("last_biweekly_cleanup_result", json.dumps(result, ensure_ascii=False))
                logging.info(
                    f"Bi-weekly database cleanup executed: {result['deleted_tickets']} tickets, "
                    f"{result['deleted_licenses']} licenses, {result['deleted_invoices']} invoices cleaned. "
                    f"Freed {result['freed_bytes'] / 1024:.1f} KB."
                )

                if bot:
                    try:
                        notif_service = NotificationService(bot)
                        report_text = (
                            "🧹 <b>گزارش پاکسازی خودکار دیتابیس (دو هفته یکبار)</b>\n"
                            "━━━━━━━━━━━━━━━━━━\n"
                            f"🎟 تیکت‌های پشتیبانی پاکسازی شده: <b>{result['deleted_tickets']}</b> عدد\n"
                            f"💬 پیام‌های تیکت حذف شده: <b>{result['deleted_ticket_messages']}</b> عدد\n"
                            f"🔑 لایسنس‌های منقضی پاکسازی شده: <b>{result['deleted_licenses']}</b> عدد\n"
                            f"🧾 فاکتورهای منقضی پاکسازی شده: <b>{result['deleted_invoices']}</b> عدد\n"
                            f"💳 گزارش‌های پرداخت منقضی: <b>{result['deleted_payment_reports']}</b> عدد\n"
                            f"💾 حجم آزاد شده دیتابیس: <b>{result['freed_bytes'] / 1024:.1f} KB</b>\n"
                            f"🕒 تاریخ اجرا: <b>{result['jalali_date']}</b>\n\n"
                            "<i>(پاکسازی در پنل X-UI و حافظه دیتابیس ربات انجام شد و چت‌های پیوی کاربران دست‌نخورده باقی ماندند)</i>"
                        )
                        await notif_service.send_report(topic_key="nightly_report", text=report_text)
                    except Exception as ne:
                        logging.debug(f"Could not send cleanup notification: {ne}")

        except Exception as e:
            logging.error(f"Cron Bi-Weekly Cleanup Error: {e}")

        await asyncio.sleep(3600)


# === CRON SETUP ===
def setup_cron_tasks(bot=None, loop=None):
    """Handles setup cron tasks."""
    if loop is None:
        loop = asyncio.get_event_loop()
    loop.create_task(cron_payment_check(bot))
    loop.create_task(cron_license_stats_check(bot))
    loop.create_task(cron_expired_licenses_cleanup())
    loop.create_task(cron_database_cleanup(bot))
    loop.create_task(cron_broadcast(bot))
    loop.create_task(cron_housekeeping())
    loop.create_task(cron_biweekly_cleanup(bot))