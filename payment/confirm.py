"""
confirm.py
----------
Module containing functionalities for confirm.
"""
# === IMPORTS ===
import logging
import aiosqlite
from io import BytesIO
from typing import Optional
from database import db_manager

# === PAYMENT CONFIRMATION LOGIC ===
class PaymentConfirmationManager:
    """
    Handles side effects of payment states: Paid, Failed, Expired.
    Replaces legacy PaymentConfirm.php.

    On a successful product purchase (plan_id != 0):
      1. Marks invoice as paid
      2. Applies cashback / wallet credit
      3. Looks up the XUI panel bound to the plan
      4. Provisions a license on that panel (idempotent)
      5. Delivers sub_id + QR code to the user
    """
    def __init__(self, bot):
        """Handles   init  ."""
        self.bot = bot

    # ------------------------------------------------------------------
    # PUBLIC: confirm_paid
    # ------------------------------------------------------------------
    async def confirm_paid(self, invoice_id: str, cashback_percent: int = 0, method: str = 'gateway') -> bool:
        """
        Marks an invoice as paid, applies cashback, provisions a license if
        this is a product invoice, and notifies the user and admin.
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

                added_balance = 0

                # Wallet-top-up invoice (plan_id == 0)
                if invoice['plan_id'] == 0:
                    added_balance += invoice['final_amount']

                if added_balance > 0:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (added_balance, user_id))
                    
                await db.commit()
                
            # Now trigger async helpers (Cashback and Referral)
            paid_amount = invoice['final_amount']
            
            # Cashback (applied by new helper)
            cashback_res = await db_manager.credit_cashback(invoice_id, user_id, paid_amount)
            if cashback_res:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"🎁 کاربر عزیز مبلغ {cashback_res['amount']:,} تومان به عنوان کش‌بک به حساب شما واریز گردید.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to send cashback message: {e}")

            # Referral commission
            ref_res = await db_manager.credit_referral_commission(invoice_id)
            if ref_res:
                referrer_id = ref_res['referrer_id']
                try:
                    await self.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎁 تبریک! مبلغ {ref_res['amount']:,} تومان پورسانت بابت خرید زیرمجموعه شما به کیف پولتان اضافه شد.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to send referral commission message: {e}")

            if invoice['plan_id'] == 0:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ کیف پول شما با موفقیت به مبلغ {paid_amount:,} تومان شارژ شد.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            # Notify admin channel
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT value FROM settings WHERE key = 'Channel_Report'") as cursor:
                    channel_row = await cursor.fetchone()
                
                if channel_row and channel_row['value']:
                    # Re-fetch user for username
                    async with db.execute("SELECT username FROM users WHERE id = ?", (user_id,)) as cur:
                        u = await cur.fetchone()
                    username = u['username'] if u and u['username'] else "Unknown"
                    admin_text = (
                        f"💵 پرداخت جدید\n"
                        f"- 👤 نام کاربری: @{username}\n"
                        f"- 🆔 آیدی: {user_id}\n"
                        f"- 💸 مبلغ: {paid_amount:,} تومان\n"
                        f"- 💳 روش: {method}"
                    )
                    try:
                        await self.bot.send_message(chat_id=channel_row['value'], text=admin_text, parse_mode="HTML")
                    except Exception as e:
                        logging.error(f"Failed to send admin report: {e}")

            # ----------------------------------------------------------------
            # XUI PROVISIONING — only for product invoices (plan_id != 0)
            # ----------------------------------------------------------------
            if invoice['plan_id'] != 0:
                # Mark as processing
                await db_manager.mark_invoice_processing(invoice_id)
                await self._provision_and_deliver(invoice_id, user_id, invoice)
                
                # Feedback & Acquisition
                feedback_enabled = await db_manager.get_setting('feedback_enabled', '1')
                if feedback_enabled == '1':
                    try:
                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        from aiogram import types as tg_types
                        fb_builder = InlineKeyboardBuilder()
                        for i in range(1, 6):
                            fb_builder.button(text=("⭐" * i), callback_data=f"fb_rate_{invoice_id}_{i}")
                        fb_builder.adjust(1)
                        await self.bot.send_message(
                            chat_id=user_id,
                            text="چقدر از تجربه خرید خود رضایت دارید؟ (۱ تا ۵ ستاره)",
                            reply_markup=fb_builder.as_markup()
                        )
                    except Exception as e:
                        pass
                        
                survey_enabled = await db_manager.get_setting('acquisition_survey_enabled', '0')
                if survey_enabled == '1':
                    should_ask = await db_manager.maybe_mark_acquisition_asked(user_id)
                    if should_ask:
                        try:
                            from aiogram.utils.keyboard import InlineKeyboardBuilder
                            from aiogram import types as tg_types
                            acq_builder = InlineKeyboardBuilder()
                            acq_builder.button(text="معرفی دوستان", callback_data="acq_friends")
                            acq_builder.button(text="تلگرام", callback_data="acq_telegram")
                            acq_builder.button(text="اینستاگرام", callback_data="acq_instagram")
                            acq_builder.button(text="سایر", callback_data="acq_other")
                            acq_builder.adjust(2, 2)
                            await self.bot.send_message(
                                chat_id=user_id,
                                text="شما از چه طریقی با ما آشنا شدید؟ لطفاً برای بهبود خدمات یکی از گزینه‌های زیر را انتخاب کنید:",
                                reply_markup=acq_builder.as_markup()
                            )
                        except Exception as e:
                            pass

            return True

        except Exception as e:
            logging.error(f"Error in confirm_paid for invoice {invoice_id}: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # PRIVATE: _provision_and_deliver
    # ------------------------------------------------------------------
    async def _provision_and_deliver(self, invoice_id: str, user_id: int, invoice, is_free_test: bool = False) -> None:
        """
        1. Find the panel bound to the invoice's plan.
        2. Provision a license on that panel.
        3. Store the license row.
        4. Deliver sub_id + QR code to user.
        """
        # Convert sqlite3.Row to dict to avoid .get() issues
        if not isinstance(invoice, dict):
            invoice = dict(invoice)
            
        plan_id = invoice.get('plan_id', 0)

        # Fetch the panel binding for this plan
        if is_free_test:
            panel_id = invoice.get('panel_id')
            binding = {'panel_id': panel_id} if panel_id else None
        else:
            binding = await db_manager.get_plan_panel(plan_id)
        if not binding:
            logging.error(f"No panel bound to plan {plan_id} for invoice {invoice_id}. Cannot provision.")
            await self._notify_provisioning_failure(
                user_id,
                invoice_id,
                "❌ پرداخت شما تایید شد اما هنوز هیچ پنلی به این پلن متصل نشده است. "
                "با پشتیبانی تماس بگیرید تا لایسنس شما صادر شود."
            )
            return

        panel = await db_manager.get_xui_panel(binding['panel_id'])
        if not panel:
            logging.error(f"Panel {binding['panel_id']} referenced by plan {plan_id} not found.")
            await db_manager.mark_invoice_issue(invoice_id, "پنل تعریف شده برای این پلن وجود ندارد.")
            await self._notify_provisioning_failure(
                user_id, invoice_id,
                "❌ خطای داخلی: پنل تعریف شده برای این پلن در دیتابیس وجود ندارد. با پشتیبانی تماس بگیرید."
            )
            return

        # Store panel_id on invoice record
        await db_manager.update_invoice_panel_id(invoice_id, panel['id'])

        # Provision the license via XUI API
        try:
            from bot.services.xui_client import provision_license, renew_license, build_client_email
            # Re-fetch the full invoice with new license_note column
            full_invoice_row = await db_manager.get_invoice_by_id(invoice_id)
            if full_invoice_row:
                full_invoice = dict(full_invoice_row)
            else:
                full_invoice = dict(invoice)
            
            renew_lic_id = full_invoice.get('renew_license_id')
            is_renewal = bool(renew_lic_id)
            
            if is_renewal:
                import aiosqlite
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT * FROM xui_licenses WHERE id = ?", (renew_lic_id,)) as cur:
                        old_lic = await cur.fetchone()
                        
                if not old_lic:
                    raise RuntimeError("لایسنس قبلی جهت تمدید در دیتابیس یافت نشد.")
                    
                email = build_client_email(old_lic['license_note'] or "", old_lic['user_id'], old_lic['invoice_id'])
                sub_id = await renew_license(panel, email, int(full_invoice['days'] or 0), float(full_invoice['gb'] or 0))
                
                # Update DB to point to new invoice
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("UPDATE xui_licenses SET invoice_id = ?, panel_id = ? WHERE id = ?", (invoice_id, panel['id'], renew_lic_id))
                    await db.commit()
            else:
                # Paid plan = "Customers" group, Free trial = "Trial" group
                xui_group = "Trial" if is_free_test else "Customers"
                sub_id = await provision_license(panel, full_invoice, user_id, group=xui_group)
        except Exception as e:
            error_text = str(e)[:600]
            logging.error(f"XUI provisioning failed for invoice {invoice_id}: {error_text}", exc_info=True)
            await db_manager.mark_invoice_issue(invoice_id, error_text)
            await self._notify_provisioning_failure(
                user_id, invoice_id,
                f"❌ پرداخت شما تایید شد اما صدور/تمدید لایسنس با خطا مواجه شد:\n"
                f"<code>{error_text}</code>\n\n"
                "با پشتیبانی تماس بگیرید و کد فاکتور را ارسال نمایید.",
                notify_admins=True,
                admin_error=error_text
            )
            return

        # Get license_note from invoice
        license_note = ""
        try:
            license_note = full_invoice['license_note'] or ""
        except Exception:
            pass

        # Store license record (Idempotent: unique on invoice_id)
        try:
            await db_manager.create_xui_license(
                invoice_id=invoice_id,
                user_id=user_id,
                panel_id=panel['id'],
                sub_id=sub_id,
                license_note=license_note
            )
        except Exception as e:
            # Already exists
            pass

        # Mark as approved
        await db_manager.mark_invoice_approved(invoice_id)

        # Deliver to user
        await self._deliver_license(user_id, sub_id, license_note, invoice_id)

    # ------------------------------------------------------------------
    # PRIVATE: _deliver_license
    # ------------------------------------------------------------------
    async def _deliver_license(
        self,
        user_id: int,
        sub_id: str,
        license_note: str,
        invoice_id: str
    ) -> None:
        """
        Deliver the license to the user:
          - QR code image of sub_id (with Pillow fallback to text)
          - Caption: "لایسنس اختصاصی شما"
          - Inline button: "کپی لایسنس" (copy_text)
        """
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram import types as tg_types

        note_line = f"\n📝 یادداشت لایسنس: <b>{license_note}</b>" if license_note else ""
        caption = (
            f"🎉 <b>سرویس شما فعال شد</b>\n\n"
            f"🛒 کد فاکتور: <code>{invoice_id}</code>"
            f"{note_line}\n\n"
            "برای مشاهده مشخصات سرویس به بخش لایسنس های من مراجعه کنید."
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            tg_types.InlineKeyboardButton(
                text="📦 لایسنس های من",
                callback_data="my_services"
            )
        )

        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logging.error(f"Failed to deliver license text to user {user_id}: {e}")

    # ------------------------------------------------------------------
    # PRIVATE: _notify_provisioning_failure
    # ------------------------------------------------------------------
    async def _notify_provisioning_failure(
        self,
        user_id: int,
        invoice_id: str,
        user_message: str,
        notify_admins: bool = False,
        admin_error: str = ""
    ) -> None:
        """Send a failure message to the user and optionally alert admins."""
        try:
            await self.bot.send_message(chat_id=user_id, text=user_message, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send provisioning failure message to user {user_id}: {e}")

        if notify_admins:
            try:
                from bot.config import ADMIN_IDS
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                from aiogram import types as tg_types
                
                admin_builder = InlineKeyboardBuilder()
                admin_builder.button(text="🔄 تلاش مجدد", callback_data=f"retry_provision_{invoice_id}")
                
                for admin_id in ADMIN_IDS:
                    try:
                        await self.bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"🚨 <b>خطای صدور لایسنس</b>\n\n"
                                f"👤 کاربر: <code>{user_id}</code>\n"
                                f"🛒 فاکتور: <code>{invoice_id}</code>\n\n"
                                f"📋 جزئیات خطا:\n<code>{admin_error[:800]}</code>"
                            ),
                            parse_mode="HTML",
                            reply_markup=admin_builder.as_markup()
                        )
                    except Exception:
                        pass
            except Exception as e:
                logging.error(f"Failed to notify admins of provisioning failure: {e}")

    # ------------------------------------------------------------------
    # PUBLIC: notify_failed
    # ------------------------------------------------------------------
    async def notify_failed(self, invoice_id: str, reason: str = 'تراکنش از سمت درگاه لغو شد') -> bool:
        """
        Marks an invoice as failed/rejected and notifies the user.
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

    # ------------------------------------------------------------------
    # PUBLIC: mark_expired
    # ------------------------------------------------------------------
    async def mark_expired(self, invoice_id: str) -> bool:
        """
        Marks an invoice as expired after timeout and notifies the user.
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
