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
from bot.services.notifications import NotificationService


# === PAYMENT CONFIRMATION LOGIC ===
class PaymentConfirmationManager:
    """
    Handles side effects of payment states: Paid, Failed, Expired.
    Replaces legacy PaymentConfirm.php.
    """

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # PUBLIC: confirm_paid
    # ------------------------------------------------------------------
    async def confirm_paid(self, invoice_id: str, cashback_percent: int = 0, method: str = 'gateway') -> bool:
        """
        Marks an invoice as processing/paid, applies cashback, provisions a license if
        this is a product invoice, marks it approved, and notifies the user and admin.
        """
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()

                if not invoice:
                    return False

                # For product invoices (plan_id != 0), transition directly to 'processing'
                # For wallet top-ups (plan_id == 0), transition to 'approved'
                initial_target_status = 'processing' if invoice['plan_id'] != 0 else 'approved'

                cursor = await db.execute(
                    "UPDATE invoices SET status = ?, payment_method = COALESCE(payment_method, ?) "
                    "WHERE id = ? AND status NOT IN ('processing', 'paid', 'approved', 'completed')",
                    (initial_target_status, method, invoice_id)
                )
                if cursor.rowcount == 0:
                    return False

                try:
                    await db.execute("UPDATE payment_reports SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
                except Exception:
                    pass

                user_id = invoice['user_id']
                wallet_deduction = invoice['wallet_deduction'] if 'wallet_deduction' in invoice.keys() else 0

                if invoice['plan_id'] == 0:
                    added_balance = invoice['final_amount']
                    if added_balance > 0:
                        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (added_balance, user_id))

                if wallet_deduction and wallet_deduction > 0:
                    deduct_cur = await db.execute(
                        "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
                        (wallet_deduction, user_id, wallet_deduction)
                    )
                    if deduct_cur.rowcount == 0:
                        await db.rollback()
                        await db.execute("UPDATE invoices SET status = 'pending' WHERE id = ?", (invoice_id,))
                        await db.commit()
                        return False

                await db.commit()

            paid_amount = invoice['final_amount']

            # Cashback
            cashback_res = await db_manager.credit_cashback(invoice_id, user_id, paid_amount)
            if cashback_res:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"🎁 مبلغ <b>{cashback_res['amount']:,} تومان</b> هدیه کش‌بک به کیف پول شما اضافه شد.",
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
                        text=f"🎉 مبلغ <b>{ref_res['amount']:,} تومان</b> پورسانت معرفی به کیف پول شما واریز شد.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to send referral commission message: {e}")

            # Agent commission
            agent_res = await db_manager.credit_agent_commission(invoice_id)
            if agent_res:
                agent_id = agent_res['agent_id']
                try:
                    await self.bot.send_message(
                        chat_id=agent_id,
                        text=(
                            "💰 <b>پورسانت جدید دریافت شد!</b>\n\n"
                            f"یک خرید به مبلغ <b>{agent_res['order_amount']:,} تومان</b> توسط زیرمجموعه شما انجام شد.\n"
                            f"💵 <b>پورسانت شما:</b> <b>{agent_res['commission_amount']:,} تومان</b> ({agent_res['commission_percent']}%)\n"
                            f"🏦 <b>موجودی پورسانت:</b> <b>{agent_res['new_balance']:,} تومان</b>"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to send agent commission notification: {e}")

            if invoice['plan_id'] == 0:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ کیف پول شما به مبلغ <b>{paid_amount:,} تومان</b> با موفقیت شارژ شد.",
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
                    async with db.execute("SELECT username FROM users WHERE id = ?", (user_id,)) as cur:
                        u = await cur.fetchone()
                    username = u['username'] if u and u['username'] else "Unknown"
                    admin_text = (
                        f"✅ <b>گزارش پرداخت موفق</b>\n"
                        f"- نام کاربری: @{username}\n"
                        f"- آیدی عددی: <code>{user_id}</code>\n"
                        f"- مبلغ: {paid_amount:,} تومان\n"
                        f"- روش پرداخت: {method}"
                    )
                    try:
                        await self.bot.send_message(chat_id=channel_row['value'], text=admin_text, parse_mode="HTML")
                    except Exception as e:
                        logging.error(f"Failed to send admin report: {e}")

            try:
                notif_service = NotificationService(self.bot)
                topic_key = "buy_report" if invoice['plan_id'] != 0 else "finance_report"
                await notif_service.send_report(
                    topic_key=topic_key,
                    text=(
                        f"✅ <b>تایید پرداخت جدید</b>\n\n"
                        f"شماره فاکتور: <code>{invoice_id}</code>\n"
                        f"مبلغ: <b>{paid_amount:,} تومان</b>\n"
                        f"روش پرداخت: <b>{method}</b>"
                    ),
                    user_id=user_id
                )
            except Exception as e:
                logging.error(f"Failed to send finance/buy report via NotificationService: {e}")

            # ----------------------------------------------------------------
            # XUI PROVISIONING - only for product invoices (plan_id != 0)
            # ----------------------------------------------------------------
            if invoice['plan_id'] != 0:
                await db_manager.mark_invoice_processing(invoice_id)
                await self._provision_and_deliver(invoice_id, user_id, invoice)

                feedback_enabled = await db_manager.get_setting('feedback_enabled', '1')
                if feedback_enabled == '1':
                    try:
                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        fb_builder = InlineKeyboardBuilder()
                        for i in range(1, 6):
                            fb_builder.button(text=("⭐" * i), callback_data=f"fb_rate_{invoice_id}_{i}")
                        fb_builder.adjust(1)
                        await self.bot.send_message(
                            chat_id=user_id,
                            text="🌟 لطفاً میزان رضایت خود از فرآیند خرید را ثبت کنید:",
                            reply_markup=fb_builder.as_markup()
                        )
                    except Exception:
                        pass

                survey_enabled = await db_manager.get_setting('acquisition_survey_enabled', '0')
                if survey_enabled == '1':
                    should_ask = await db_manager.maybe_mark_acquisition_asked(user_id)
                    if should_ask:
                        try:
                            from aiogram.utils.keyboard import InlineKeyboardBuilder
                            acq_builder = InlineKeyboardBuilder()
                            acq_builder.button(text="👥 معرفی دوستان", callback_data="acq_friends")
                            acq_builder.button(text="📢 تلگرام", callback_data="acq_telegram")
                            acq_builder.button(text="📸 اینستاگرام", callback_data="acq_instagram")
                            acq_builder.button(text="🌐 سایر", callback_data="acq_other")
                            acq_builder.adjust(2, 2)
                            await self.bot.send_message(
                                chat_id=user_id,
                                text="🔍 چگونه با خدمات ما آشنا شدید؟",
                                reply_markup=acq_builder.as_markup()
                            )
                        except Exception:
                            pass

            return True
        except Exception as e:
            logging.error(f"Error in confirm_paid for invoice {invoice_id}: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # PRIVATE: _provision_and_deliver
    # ------------------------------------------------------------------
    async def _provision_and_deliver(self, invoice_id: str, user_id: int, invoice, is_free_test: bool = False) -> None:
        if not isinstance(invoice, dict):
            invoice = dict(invoice)

        plan_id = invoice.get('plan_id', 0)

        if is_free_test:
            panel_id = invoice.get('panel_id')
            binding = {'panel_id': panel_id} if panel_id else None
        else:
            binding = await db_manager.get_plan_panel(plan_id)

        if not binding:
            error_msg = f"هیچ پنلی به پلن {plan_id} متصل نشده است (جدول plan_panel)."
            logging.error(f"No panel bound to plan {plan_id} for invoice {invoice_id}. Cannot provision.")
            await db_manager.mark_invoice_issue(invoice_id, error_msg)
            await self._notify_provisioning_failure(
                user_id,
                invoice_id,
                "⚠️ پرداخت شما ثبت شد اما در اتصال به سرور مشکلی پیش آمد. پشتیبانی به زودی بررسی می‌کند.",
                notify_admins=True,
                admin_error=error_msg
            )
            return

        panel = await db_manager.get_xui_panel(binding['panel_id'])
        if not panel:
            error_msg = f"پنل شماره {binding['panel_id']} متصل به پلن {plan_id} در دیتابیس یافت نشد."
            logging.error(f"Panel {binding['panel_id']} referenced by plan {plan_id} not found.")
            await db_manager.mark_invoice_issue(invoice_id, error_msg)
            await self._notify_provisioning_failure(
                user_id,
                invoice_id,
                "⚠️ پرداخت شما ثبت شد اما سرور مورد نظر در دسترس نیست. پشتیبانی به زودی بررسی می‌کند.",
                notify_admins=True,
                admin_error=error_msg
            )
            return

        await db_manager.update_invoice_panel_id(invoice_id, panel['id'])

        try:
            from bot.services.xui_client import provision_license, renew_license, build_client_email
            full_invoice_row = await db_manager.get_invoice_by_id(invoice_id)
            full_invoice = dict(full_invoice_row) if full_invoice_row else dict(invoice)

            renew_lic_id = full_invoice.get('renew_license_id')
            is_renewal = bool(renew_lic_id)

            if is_renewal:
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT * FROM xui_licenses WHERE id = ?", (renew_lic_id,)) as cur:
                        old_lic = await cur.fetchone()

                if not old_lic:
                    raise RuntimeError("اشتراک قبلی جهت تمدید در دیتابیس یافت نشد.")

                email = build_client_email(old_lic['license_note'] or "", old_lic['user_id'], old_lic['invoice_id'])
                sub_id = await renew_license(panel, email, int(full_invoice['days'] or 0), float(full_invoice['gb'] or 0))

                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute(
                        "UPDATE xui_licenses SET invoice_id = ?, panel_id = ?, alert_sent = 0 WHERE id = ?",
                        (invoice_id, panel['id'], renew_lic_id)
                    )
                    await db.commit()
            else:
                xui_group = "Trial" if is_free_test else "Customers"
                sub_id = await provision_license(panel, full_invoice, user_id, group=xui_group)
        except Exception as e:
            error_text = str(e)[:600]
            logging.error(f"XUI provisioning failed for invoice {invoice_id}: {error_text}", exc_info=True)
            await db_manager.mark_invoice_issue(invoice_id, error_text)
            await self._notify_provisioning_failure(
                user_id,
                invoice_id,
                f"⚠️ خطا در ساخت اشتراک:\n<code>{error_text}</code>\n\nگزارش خطا برای مدیریت ارسال شد.",
                notify_admins=True,
                admin_error=error_text
            )
            return

        license_note = ""
        try:
            license_note = full_invoice.get('license_note') or ""
        except Exception:
            pass

        try:
            await db_manager.create_xui_license(
                invoice_id=invoice_id,
                user_id=user_id,
                panel_id=panel['id'],
                sub_id=sub_id,
                license_note=license_note
            )
        except Exception:
            pass

        await db_manager.mark_invoice_approved(invoice_id)
        await self._deliver_license(user_id, sub_id, license_note, invoice_id)

    # ------------------------------------------------------------------
    # PRIVATE: _deliver_license
    # ------------------------------------------------------------------
    async def _deliver_license(self, user_id: int, sub_id: str, license_note: str, invoice_id: str) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram import types as tg_types

        note_line = f"\n📝 نام سرویس: <b>{license_note}</b>" if license_note else ""
        caption = (
            f"✅ <b>اشتراک شما با موفقیت فعال شد!</b>\n\n"
            f"🧾 شماره فاکتور: <code>{invoice_id}</code>"
            f"{note_line}\n\n"
            "از طریق دکمه زیر می‌توانید سرویس خود را مشاهده و مدیریت کنید:"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            tg_types.InlineKeyboardButton(
                text="📱 اشتراک‌های من",
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
        try:
            await self.bot.send_message(chat_id=user_id, text=user_message, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send provisioning failure message to user {user_id}: {e}")

        if notify_admins:
            try:
                import html
                from bot.config import ADMIN_IDS
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                from aiogram import types as tg_types

                safe_admin_error = html.escape(str(admin_error)[:800])
                error_text = (
                    f"🚨 <b>خطا در صدور اشتراک</b>\n\n"
                    f"👤 کاربر: <code>{user_id}</code>\n"
                    f"🧾 فاکتور: <code>{invoice_id}</code>\n\n"
                    f"❌ متن خطا:\n<code>{safe_admin_error}</code>"
                )
                admin_builder = InlineKeyboardBuilder()
                admin_builder.row(
                    tg_types.InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data=f"retry_provision_{invoice_id}")
                )
                if user_id:
                    admin_builder.row(
                        tg_types.InlineKeyboardButton(
                            text="👤 مدیریت کاربر",
                            callback_data=f"manage_user_group_{user_id}"
                        )
                    )

                sent_to_group = False
                try:
                    notif_service = NotificationService(self.bot)
                    sent_to_group = await notif_service.send_report(
                        topic_key="error_report",
                        text=error_text,
                        user_id=user_id,
                        reply_markup=admin_builder.as_markup()
                    )
                except Exception as e:
                    logging.error(f"Failed to send error report via NotificationService: {e}")

                if not sent_to_group:
                    for admin_id in ADMIN_IDS:
                        try:
                            await self.bot.send_message(
                                chat_id=admin_id,
                                text=error_text,
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
    async def notify_failed(self, invoice_id: str, reason: str = 'عدم تایید پرداخت') -> bool:
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()

                if not invoice or invoice['status'] in ('paid', 'approved'):
                    return False

                await db.execute("UPDATE invoices SET status = 'failed' WHERE id = ?", (invoice_id,))
                await db.commit()

                price_fmt = f"{invoice['final_amount']:,}"
                text = (
                    f"❌ <b>پرداخت تایید نشد</b>\n\n"
                    f"🧾 شماره فاکتور: <code>{invoice_id}</code>\n"
                    f"💰 مبلغ: <b>{price_fmt}</b> تومان\n"
                    f"📝 علت: {reason}\n\n"
                    f"در صورت نیاز با پشتیبانی در ارتباط باشید."
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
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                    invoice = await cursor.fetchone()

                if not invoice or invoice['status'] in ('paid', 'approved'):
                    return False

                await db.execute("UPDATE invoices SET status = 'expired' WHERE id = ?", (invoice_id,))
                await db.commit()

                price_fmt = f"{invoice['final_amount']:,}"
                text = (
                    f"⏳ <b>انقضای فاکتور</b>\n\n"
                    f"🧾 شماره فاکتور: <code>{invoice_id}</code>\n"
                    f"💰 مبلغ: <b>{price_fmt}</b> تومان\n\n"
                    f"مهلت پرداخت این فاکتور به پایان رسیده است."
                )
                try:
                    await self.bot.send_message(chat_id=invoice['user_id'], text=text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send expire message to {invoice['user_id']}: {e}")
            return True
        except Exception as e:
            logging.error(f"Error in mark_expired for invoice {invoice_id}: {e}")
            return False