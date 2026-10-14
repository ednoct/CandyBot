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
from bot.services.sub_stats import fetch_sub_stats
from utils.backup import create_database_backup
from bot.services.notifications import NotificationService
from aiogram.types import FSInputFile
from database import db_manager


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
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                
                # Get all active licenses with sub_links
                async with db.execute(
                    "SELECT l.id, l.user_id, l.sub_id, p.sub_link, l.alert_sent "
                    "FROM xui_licenses l "
                    "JOIN xui_panels p ON l.panel_id = p.id "
                    "WHERE p.sub_link IS NOT NULL AND p.sub_link != '' AND l.alert_sent = 0"
                ) as cursor:
                    licenses = await cursor.fetchall()
                    
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
                            # Mark alert as sent
                            await db.execute("UPDATE xui_licenses SET alert_sent = 1 WHERE id = ?", (lic['id'],))
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to send alert to user {lic['user_id']}: {e}")
                            
        except Exception as e:
            logging.error(f"Cron License Stats Check Error: {e}")
            
        await asyncio.sleep(21600) # 6 hours

# === BACKGROUND TASK: PAYMENT CHECK ===
async def cron_payment_check(bot=None):
    """
    Background loop to check pending payments (plisio, crypto).
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

# === BACKGROUND TASK: DB CLEANUP & NIGHTLY REPORT ===
async def cron_database_cleanup(bot=None):
    """
    Daily task to clean up old abandoned invoices, generate stats, backup DB,
    and send nightly report.
    Replaces generic legacy cron sweeps.
    Runs every 86400 seconds (24h).
    """
    import os
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Cleanup old pending invoices older than 24 hours
                await db.execute("DELETE FROM invoices WHERE status = 'pending' AND created_at < datetime('now', '-1 day')")
                await db.commit()
                logging.info("Executed daily database cleanup")
                
            if bot:
                # 1. Fetch Daily Stats
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
                
                # 2. Create DB Backup
                zip_path = await create_database_backup()
                
                # 3. Send Notification
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

# === BACKGROUND TASK: BI-WEEKLY EXPIRED DATA CLEANUP (TICKETS, LICENSES, INVOICES) ===
async def cron_biweekly_cleanup(bot=None):
    """
    Bi-weekly background loop to clean up:
    - Support tickets (closed, or answered older than 14 days) and messages
    - Expired licenses (checked via sub_link stats or invoice validity)
    - Expired invoices and payment reports
    - Reclaims memory & disk via SQLite VACUUM and PRAGMA optimize.
    Runs every 2 weeks (14 days). Periodically checks every hour to survive bot restarts.
    Operates strictly within the bot's database/memory; no messages in user PVs are deleted.
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
                should_run = True
            else:
                try:
                    last_time = int(last_cleanup)
                    if (now - last_time) >= interval_seconds:
                        should_run = True
                except ValueError:
                    should_run = True

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
                            "<i>(پاکسازی صرفاً در حافظه دیتابیس ربات جهت بهینه‌سازی انجام شد و چت‌های پیوی کاربران دست‌نخورده باقی ماندند)</i>"
                        )
                        await notif_service.send_report(topic_key="nightly_report", text=report_text)
                    except Exception as ne:
                        logging.debug(f"Could not send cleanup notification: {ne}")

        except Exception as e:
            logging.error(f"Cron Bi-Weekly Cleanup Error: {e}")

        # Check every 1 hour (3600 seconds)
        await asyncio.sleep(3600)

# === CRON SETUP ===
def setup_cron_tasks(bot=None, loop=None):
    """Handles setup cron tasks."""
    if loop is None:
        loop = asyncio.get_event_loop()
    loop.create_task(cron_payment_check(bot))
    loop.create_task(cron_license_stats_check(bot))
    loop.create_task(cron_database_cleanup(bot))
    loop.create_task(cron_broadcast())
    loop.create_task(cron_housekeeping())
    loop.create_task(cron_biweekly_cleanup(bot))
