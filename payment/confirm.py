# === IMPORTS ===
import logging
import aiosqlite
from typing import Optional, Dict, Any
from database import db_manager

# === PAYMENT CONFIRMATION LOGIC ===
class PaymentConfirmationManager:
    """
    Handles side effects of payment states: Paid, Failed, Expired.
    Replaces legacy PaymentConfirm.php.
    """
    def __init__(self, bot):
        self.bot = bot

    async def confirm_paid(self, invoice_id: str, cashback_percent: int = 0, method: str = 'gateway') -> bool:
        """
        Marks an invoice as paid, applies cashback, and notifies the user and admin.
        Replaces payment_confirm_paid() from PHP.
        """
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                
                # Fetch invoice
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()
                
                if not invoice or invoice['status'] == 'paid':
                    return False
                
                # Mark as paid
                await db.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
                
                # Fetch user
                user_id = invoice['user_id']
                async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                    user = await cursor.fetchone()
                
                # Handle cashback
                cashback_amount = 0
                if cashback_percent > 0:
                    cashback_amount = int((invoice['final_amount'] * cashback_percent) / 100)
                    if cashback_amount > 0:
                        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (cashback_amount, user_id))
                        try:
                            await self.bot.send_message(
                                chat_id=user_id,
                                text=f"🎁 کاربر عزیز مبلغ {cashback_amount} تومان به عنوان هدیه به حساب شما واریز گردید.",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logging.error(f"Failed to send cashback message: {e}")

                await db.commit()

                # Notify user of successful payment
                price_fmt = f"{invoice['final_amount']:,}"
                new_balance_fmt = f"{(user['balance'] + cashback_amount):,}" if user else "0"
                
                success_text = (
                    f"✅ <b>پرداخت شما با موفقیت تایید شد</b>\n\n"
                    f"🛒 کد فاکتور: <code>{invoice_id}</code>\n"
                    f"💰 مبلغ: <b>{price_fmt}</b> تومان\n"
                    f"💎 موجودی جدید: <b>{new_balance_fmt}</b> تومان"
                )
                try:
                    await self.bot.send_message(chat_id=user_id, text=success_text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send success message to user {user_id}: {e}")

                # Notify admin channel
                # We would fetch admin channel ID from settings
                async with db.execute("SELECT value FROM settings WHERE key = 'Channel_Report'") as cursor:
                    channel_row = await cursor.fetchone()
                if channel_row and channel_row['value']:
                    username = user['username'] if user else "Unknown"
                    admin_text = (
                        f"💵 پرداخت جدید\n"
                        f"- 👤 نام کاربری کاربر : @{username}\n"
                        f"- 🆔 آیدی عددی کاربر : {user_id}\n"
                        f"- 💸 مبلغ تراکنش : {invoice['final_amount']}\n"
                        f"- 💳 روش پرداخت : {method}"
                    )
                    try:
                        await self.bot.send_message(chat_id=channel_row['value'], text=admin_text, parse_mode="HTML")
                    except Exception as e:
                        logging.error(f"Failed to send admin report: {e}")

            return True
        except Exception as e:
            logging.error(f"Error in confirm_paid for invoice {invoice_id}: {e}")
            return False

    async def notify_failed(self, invoice_id: str, reason: str = 'تراکنش از سمت درگاه لغو شد') -> bool:
        """
        Marks an invoice as failed/rejected and notifies the user.
        Replaces payment_notify_user_failed() from PHP.
        """
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()
                
                if not invoice or invoice['status'] == 'paid':
                    return False
                
                await db.execute("UPDATE invoices SET status = 'failed' WHERE id = ?", (invoice_id,))
                await db.commit()
                
                price_fmt = f"{invoice['final_amount']:,}"
                text = (
                    f"❌ <b>پرداخت تأیید نشد</b>\n\n"
                    f"🛒 کد فاکتور: <code>{invoice_id}</code>\n"
                    f"💸 مبلغ: <b>{price_fmt}</b> تومان\n"
                    f"📝 دلیل: {reason}\n\n"
                    f"اگر مطمئنید پرداخت انجام شده، با پشتیبانی تماس بگیرید."
                )
                try:
                    await self.bot.send_message(chat_id=invoice['user_id'], text=text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send failure message to {invoice['user_id']}: {e}")
            return True
        except Exception as e:
            logging.error(f"Error in notify_failed for invoice {invoice_id}: {e}")
            return False

    async def mark_expired(self, invoice_id: str) -> bool:
        """
        Marks an invoice as expired after timeout and notifies the user.
        Replaces payment_mark_expired() from PHP.
        """
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()
                
                if not invoice or invoice['status'] == 'paid':
                    return False
                
                await db.execute("UPDATE invoices SET status = 'expired' WHERE id = ?", (invoice_id,))
                await db.commit()
                
                price_fmt = f"{invoice['final_amount']:,}"
                text = (
                    f"⏰ <b>پرداخت بعد از ۳۰ دقیقه تأیید نشد</b>\n\n"
                    f"🛒 کد فاکتور: <code>{invoice_id}</code>\n"
                    f"💸 مبلغ: <b>{price_fmt}</b> تومان\n\n"
                    f"💡 اگر پرداخت کرده‌اید، ممکنه شبکه‌ی کریپتو هنوز confirm نکرده باشه. "
                    f"چند دقیقه دیگر صبر کنید.\n"
                    f"اگر هنوز تأیید نشد، با پشتیبانی تماس بگیرید."
                )
                try:
                    await self.bot.send_message(chat_id=invoice['user_id'], text=text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send expire message to {invoice['user_id']}: {e}")
            return True
        except Exception as e:
            logging.error(f"Error in mark_expired for invoice {invoice_id}: {e}")
            return False
