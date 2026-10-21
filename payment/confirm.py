"""
payment/confirm.py
------------------
Handles side effects of payment states: Paid, Failed, Expired.
Patched for:
- BUG-08: Reads `renew_mode` ('change_plan' vs 'keep_plan') from invoices table (with fallback to transfer_method).
- 3x-UI v3.10.2 sync: Passes `sub_id=preserved_sub_id` to `renew_license` so multi-inbound clients are matched by subId.
"""

# === IMPORTS ===
import asyncio
import html
import logging
import time
import aiosqlite
from typing import Optional
from database import db_manager
from bot.services.notifications import NotificationService


# === SHARED TASK-REENTRANT INVOICE LOCK ===
class _AsyncRLock:
    """Task-reentrant async lock to prevent deadlocks across nested callers while enforcing mutual exclusion."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: Optional[asyncio.Task] = None
        self._count: int = 0

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self):
        current = asyncio.current_task()
        if current is not None and self._owner is current:
            self._count += 1
            return self
        await self._lock.acquire()
        self._owner = current
        self._count = 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._count -= 1
        if self._count <= 0:
            self._count = 0
            self._owner = None
            self._lock.release()


_INVOICE_LOCKS: dict[str, _AsyncRLock] = {}


def get_invoice_lock(invoice_id: str) -> _AsyncRLock:
    """Returns a process-wide per-invoice reentrant lock shared by webhook, polling, and startup recovery."""
    key = str(invoice_id).strip()
    if key not in _INVOICE_LOCKS:
        if len(_INVOICE_LOCKS) > 5000:
            unlocked_keys = [k for k, lk in _INVOICE_LOCKS.items() if not lk.locked()]
            for k in unlocked_keys[:2500]:
                _INVOICE_LOCKS.pop(k, None)
        _INVOICE_LOCKS[key] = _AsyncRLock()
    return _INVOICE_LOCKS[key]


# === PAYMENT CONFIRMATION LOGIC ===
class PaymentConfirmationManager:
    """
    Handles side effects of payment states: Paid, Failed, Expired.
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def _safe_delete_xui_client(panel: dict, email: str, sub_id: Optional[str] = None) -> bool:
        """Safely deletes a client from a 3x-UI panel using XUIClient instance."""
        if not panel or not panel.get("url") or not panel.get("bearer_token"):
            return False
        from bot.services.xui_client import XUIClient
        async with XUIClient(panel["url"], panel["bearer_token"]) as client:
            try:
                return await client.delete_client(email, sub_id=sub_id)
            except TypeError:
                return await client.delete_client(email)

    @staticmethod
    async def _safe_provision_xui_client(
        panel: dict,
        inbound_ids: list[int],
        email: str,
        sub_id: str,
        total_gb: float,
        days: int,
        user_id: int,
        comment: str = "",
        group: str = "Customers",
    ) -> str:
        """Safely provisions a client on 3x-UI matching XUIClient.provision's signature."""
        from bot.services.xui_client import XUIClient
        limit_ip = int(panel.get("ip_limit") or 1)
        async with XUIClient(panel["url"], panel["bearer_token"]) as client:
            return await client.provision(
                email=email,
                total_gb=float(total_gb),
                days=int(days),
                tg_id=user_id,
                limit_ip=limit_ip,
                inbound_ids=inbound_ids,
                group=group,
                sub_id=sub_id,
                comment=comment,
            )

    # ------------------------------------------------------------------
    # PUBLIC: confirm_paid
    # ------------------------------------------------------------------
    async def confirm_paid(self, invoice_id: str, cashback_percent: int = 0, method: str = 'gateway') -> bool:
        """
        Marks an invoice as processing/paid, applies cashback, provisions or renews a license
        if this is a product invoice, marks it approved, and notifies the user and admin.
        """
        lock = get_invoice_lock(invoice_id)
        async with lock:
            try:
                now_ts = int(time.time())
                shortfall_refunded = False
                paid_gateway_amount = 0
                wallet_deduction = 0
                user_id = 0

                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    await db.execute("PRAGMA foreign_keys = ON;")
                    db.row_factory = aiosqlite.Row

                    async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                        invoice = await cursor.fetchone()

                    if not invoice:
                        return False

                    initial_target_status = 'processing' if invoice['plan_id'] != 0 else 'approved'

                    cursor = await db.execute(
                        "UPDATE invoices SET status = ?, payment_method = COALESCE(payment_method, ?) "
                        "WHERE id = ? AND status NOT IN ('processing', 'paid', 'approved', 'completed', 'issue')",
                        (initial_target_status, method, invoice_id)
                    )
                    if cursor.rowcount == 0:
                        return False

                    try:
                        await db.execute("UPDATE payment_reports SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
                    except Exception:
                        pass

                    user_id = invoice['user_id']
                    wallet_deduction = int(invoice['wallet_deduction'] or 0) if 'wallet_deduction' in invoice.keys() else 0
                    paid_gateway_amount = int(invoice['final_amount'] or 0)

                    # 1. Wallet Top-Up (plan_id == 0)
                    if invoice['plan_id'] == 0:
                        if paid_gateway_amount > 0:
                            await db.execute(
                                "UPDATE users SET balance = balance + ? WHERE id = ?",
                                (paid_gateway_amount, user_id)
                            )
                            async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as bal_cur:
                                bal_row = await bal_cur.fetchone()
                                balance_after = int(bal_row['balance']) if bal_row else paid_gateway_amount
                            await db.execute(
                                """
                                INSERT OR IGNORE INTO wallet_transactions
                                    (user_id, amount, balance_after, type, description, related_invoice_id, unique_key, created_at)
                                VALUES (?, ?, ?, 'PURCHASE', ?, ?, ?, ?)
                                """,
                                (
                                    user_id,
                                    paid_gateway_amount,
                                    balance_after,
                                    f"شارژ کیف پول (فاکتور {invoice_id})",
                                    invoice_id,
                                    f"topup:{invoice_id}",
                                    now_ts,
                                )
                            )

                    # 2. Hybrid Payment Wallet Deduction
                    if wallet_deduction > 0:
                        deduct_cur = await db.execute(
                            "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
                            (wallet_deduction, user_id, wallet_deduction)
                        )
                        if deduct_cur.rowcount > 0:
                            async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as bal_cur:
                                bal_row = await bal_cur.fetchone()
                                balance_after = int(bal_row['balance']) if bal_row else 0
                            await db.execute(
                                """
                                INSERT OR IGNORE INTO wallet_transactions
                                    (user_id, amount, balance_after, type, description, related_invoice_id, unique_key, created_at)
                                VALUES (?, ?, ?, 'PURCHASE', ?, ?, ?, ?)
                                """,
                                (
                                    user_id,
                                    -wallet_deduction,
                                    balance_after,
                                    f"کسر از کیف پول بابت فاکتور {invoice_id}",
                                    invoice_id,
                                    f"deduct:{invoice_id}",
                                    now_ts,
                                )
                            )
                        else:
                            shortfall_refunded = True
                            if paid_gateway_amount > 0:
                                await db.execute(
                                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                                    (paid_gateway_amount, user_id)
                                )
                                async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as bal_cur:
                                    bal_row = await bal_cur.fetchone()
                                    balance_after = int(bal_row['balance']) if bal_row else paid_gateway_amount
                                await db.execute(
                                    """
                                    INSERT OR IGNORE INTO wallet_transactions
                                        (user_id, amount, balance_after, type, description, related_invoice_id, unique_key, created_at)
                                    VALUES (?, ?, ?, 'REFUND', ?, ?, ?, ?)
                                    """,
                                    (
                                        user_id,
                                        paid_gateway_amount,
                                        balance_after,
                                        f"انتقال وجه پرداختی درگاه به کیف پول به علت کسری موجودی اولیه (فاکتور {invoice_id})",
                                        invoice_id,
                                        f"refund_shortfall:{invoice_id}",
                                        now_ts,
                                    )
                                )
                            await db.execute(
                                "UPDATE invoices SET status = 'issue', last_error = ? WHERE id = ?",
                                ("کسری موجودی کیف‌پول در لحظه تایید درگاه؛ مبلغ پرداختی به کیف‌پول منتقل شد.", invoice_id)
                            )

                    await db.commit()

                if shortfall_refunded:
                    await self._notify_provisioning_failure(
                        user_id=user_id,
                        invoice_id=invoice_id,
                        user_message=(
                            f"⚠️ <b>موجودی کیف‌پول شما برای تکمیل فاکتور <code>{html.escape(str(invoice_id))}</code> کافی نبود.</b>\n\n"
                            f"مبلغ پرداخت‌شده در درگاه (<b>{paid_gateway_amount:,} تومان</b>) به صورت کامل به موجودی کیف‌پول شما اضافه شد."
                        ),
                        notify_admins=True,
                        admin_error=(
                            f"کسری موجودی کیف‌پول در پرداخت ترکیبی (نیاز به کسر {wallet_deduction:,} تومان). "
                            f"مبلغ {paid_gateway_amount:,} تومان پرداختی درگاه به کیف‌پول کاربر اضافه شد."
                        ),
                    )
                    return False

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
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT value FROM settings WHERE key = 'Channel_Report'") as cursor:
                        channel_row = await cursor.fetchone()

                    if channel_row and channel_row['value']:
                        async with db.execute("SELECT username FROM users WHERE id = ?", (user_id,)) as cur:
                            u = await cur.fetchone()
                        username = html.escape(u['username']) if u and u['username'] else "Unknown"
                        admin_text = (
                            f"✅ <b>گزارش پرداخت موفق</b>\n"
                            f"- نام کاربری: @{username}\n"
                            f"- آیدی عددی: <code>{user_id}</code>\n"
                            f"- مبلغ: {paid_amount:,} تومان\n"
                            f"- روش پرداخت: {html.escape(str(method))}"
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
                            f"شماره فاکتور: <code>{html.escape(str(invoice_id))}</code>\n"
                            f"مبلغ: <b>{paid_amount:,} تومان</b>\n"
                            f"روش پرداخت: <b>{html.escape(str(method))}</b>"
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
    # PRIVATE: _parse_panel_inbound_ids
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_panel_inbound_ids(panel: dict) -> list[int]:
        """Extracts and validates inbound_ids from a panel dict. Raises RuntimeError if empty."""
        inbound_ids_str = str(panel.get("inbound_ids") or "")
        inbound_ids = [int(x.strip()) for x in inbound_ids_str.split(",") if x.strip().isdigit()]
        if not inbound_ids:
            raise RuntimeError(
                f"هیچ اینباند معتبری (inbound_ids) برای پنل شماره {panel.get('id')} ({panel.get('name') or panel.get('url')}) تنظیم نشده است."
            )
        return inbound_ids

    # ------------------------------------------------------------------
    # PRIVATE: _provision_and_deliver (Fixes BUG-08)
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
            import math
            from bot.services.xui_client import (
                provision_license,
                renew_license,
                build_client_email,
            )
            from bot.services.sub_stats import fetch_sub_stats

            full_invoice_row = await db_manager.get_invoice_by_id(invoice_id)
            full_invoice = dict(full_invoice_row) if full_invoice_row else dict(invoice)

            renew_lic_id = full_invoice.get('renew_license_id')
            is_renewal = bool(renew_lic_id)

            if is_renewal:
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT * FROM xui_licenses WHERE id = ?", (renew_lic_id,)) as cur:
                        old_lic = await cur.fetchone()

                if not old_lic:
                    raise RuntimeError("اشتراک قبلی جهت تمدید در دیتابیس یافت نشد.")

                old_lic_dict = dict(old_lic)
                preserved_sub_id = str(old_lic_dict['sub_id']).strip()
                old_note = old_lic_dict.get('license_note') or full_invoice.get('license_note') or ""
                old_panel_id = old_lic_dict.get('panel_id')
                old_invoice_id = old_lic_dict.get('invoice_id')

                inv_days = int(full_invoice.get('days') or 0)
                inv_gb = float(full_invoice.get('gb') or 0.0)

                # Fix BUG-08: Read `renew_mode` column first (where 'change_plan' / 'keep_plan' is stored)
                renew_mode = str(
                    full_invoice.get('renew_mode')
                    or full_invoice.get('transfer_method')
                    or ''
                ).strip().lower()

                is_change_plan = renew_mode in ('change_plan', 'new_plan', 'switch_plan')

                if is_change_plan:
                    # Mode 2 (Change Plan on expired license):
                    # Preserve ONLY the sub_id identity; provision on the new plan's panel with exact invoice days & gb.
                    inbound_ids = self._parse_panel_inbound_ids(panel)
                    new_email = build_client_email(old_note, user_id, invoice_id)

                    if old_panel_id:
                        old_panel = await db_manager.get_xui_panel(old_panel_id)
                        if old_panel:
                            try:
                                old_email = build_client_email(old_note, old_lic_dict['user_id'], old_invoice_id)
                                await self._safe_delete_xui_client(old_panel, old_email, sub_id=preserved_sub_id)
                            except Exception as del_err:
                                logging.debug(f"Best-effort cleanup on old panel before change_plan renewal: {del_err}")

                    await self._safe_provision_xui_client(
                        panel=panel,
                        inbound_ids=inbound_ids,
                        email=new_email,
                        sub_id=preserved_sub_id,
                        total_gb=inv_gb if inv_gb > 0 else 0.0,
                        days=inv_days if inv_days > 0 else 0,
                        user_id=user_id,
                        comment=old_note,
                        group="Customers",
                    )
                    sub_id = preserved_sub_id

                else:
                    # Mode 1 (Unexpired renewal OR Expired "keep_plan" renewal):
                    email = build_client_email(old_note, old_lic_dict['user_id'], old_invoice_id)
                    renewed_in_place = False

                    if old_panel_id == panel['id']:
                        try:
                            sub_id = await renew_license(
                                panel,
                                email,
                                inv_days,
                                inv_gb,
                                sub_id=preserved_sub_id,
                            )
                            renewed_in_place = True
                        except Exception as renew_err:
                            logging.warning(
                                f"In-place renew_license failed for {invoice_id} (email={email}): {renew_err}. "
                                f"Falling back to recreation with preserved sub_id={preserved_sub_id}."
                            )
                            renewed_in_place = False

                    if not renewed_in_place:
                        inbound_ids = self._parse_panel_inbound_ids(panel)

                        rem_gb = 0.0
                        rem_days = 0
                        prev_unlim_traffic = False
                        prev_unlim_time = False
                        was_expired = True

                        old_panel = await db_manager.get_xui_panel(old_panel_id) if old_panel_id else None
                        sub_link_url = (old_panel.get('sub_link') if old_panel else None) or panel.get('sub_link')

                        if sub_link_url and preserved_sub_id:
                            try:
                                stats = await asyncio.wait_for(
                                    fetch_sub_stats(sub_link_url, preserved_sub_id),
                                    timeout=5.0
                                )
                                if stats:
                                    was_expired = bool(stats.get('is_expired', False))
                                    prev_unlim_traffic = bool(stats.get('is_unlimited_traffic', False))
                                    prev_unlim_time = bool(stats.get('is_unlimited_time', False))
                                    if not prev_unlim_traffic and float(stats.get('remaining_gb') or 0) > 0:
                                        rem_gb = float(stats['remaining_gb'])
                                    if not prev_unlim_time and float(stats.get('days_left') or 0) > 0:
                                        rem_days = math.ceil(float(stats['days_left']))
                            except Exception as st_err:
                                logging.debug(f"Could not fetch sub_stats during panel migration for {invoice_id}: {st_err}")

                        # Fallback to DB invoice history if sub_link stats weren't reachable
                        if rem_gb == 0.0 and rem_days == 0 and not prev_unlim_traffic and not prev_unlim_time:
                            old_inv = await db_manager.get_invoice_by_id(old_invoice_id) if old_invoice_id else None
                            if old_inv:
                                old_inv_dict = dict(old_inv)
                                old_days = int(old_inv_dict.get('days') or 0)
                                old_gb = float(old_inv_dict.get('gb') or 0.0)
                                if old_gb <= 0:
                                    prev_unlim_traffic = True
                                if old_days <= 0:
                                    prev_unlim_time = True
                                try:
                                    from datetime import datetime
                                    created_str = str(old_lic_dict.get('created_at') or old_inv_dict.get('created_at') or '')
                                    if created_str and old_days > 0:
                                        dt = datetime.strptime(created_str[:19], '%Y-%m-%d %H:%M:%S')
                                        exp_ts = dt.timestamp() + (old_days * 86400)
                                        left_sec = exp_ts - time.time()
                                        if left_sec > 0:
                                            rem_days = math.ceil(left_sec / 86400.0)
                                            was_expired = False
                                except Exception:
                                    pass

                        if inv_gb <= 0 or (not was_expired and prev_unlim_traffic):
                            new_tot_gb = 0.0
                        else:
                            new_tot_gb = round(max(0.0, rem_gb) + inv_gb, 4)

                        if inv_days <= 0 or (not was_expired and prev_unlim_time):
                            new_tot_days = 0
                        else:
                            new_tot_days = max(0, rem_days) + inv_days

                        if old_panel and old_panel['id'] != panel['id']:
                            try:
                                await self._safe_delete_xui_client(old_panel, email, sub_id=preserved_sub_id)
                            except Exception:
                                pass

                        new_email = build_client_email(old_note, user_id, invoice_id)
                        await self._safe_provision_xui_client(
                            panel=panel,
                            inbound_ids=inbound_ids,
                            email=new_email,
                            sub_id=preserved_sub_id,
                            total_gb=new_tot_gb,
                            days=new_tot_days,
                            user_id=user_id,
                            comment=old_note,
                            group="Customers",
                        )
                        sub_id = preserved_sub_id

                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    await db.execute(
                        "UPDATE xui_licenses SET invoice_id = ?, panel_id = ?, license_note = COALESCE(NULLIF(?, ''), license_note), alert_sent = 0 WHERE id = ?",
                        (invoice_id, panel['id'], old_note, renew_lic_id)
                    )
                    await db.commit()
                license_note = old_note
            else:
                self._parse_panel_inbound_ids(panel)
                xui_group = "Trial" if is_free_test else "Customers"
                sub_id = await provision_license(panel, full_invoice, user_id, group=xui_group)
                license_note = full_invoice.get('license_note') or ""
                await db_manager.create_xui_license(
                    invoice_id=invoice_id,
                    user_id=user_id,
                    panel_id=panel['id'],
                    sub_id=sub_id,
                    license_note=license_note
                )

        except Exception as e:
            error_text = str(e)[:600]
            logging.error(f"XUI provisioning failed for invoice {invoice_id}: {error_text}", exc_info=True)
            await db_manager.mark_invoice_issue(invoice_id, error_text)
            await self._notify_provisioning_failure(
                user_id,
                invoice_id,
                (
                    f"⚠️ <b>پرداخت شما با موفقیت ثبت شد، اما در ساخت یا تمدید خودکار اشتراک خطایی رخ داد.</b>\n"
                    f"🧾 شماره فاکتور: <code>{html.escape(str(invoice_id))}</code>\n\n"
                    f"گزارش خطا برای مدیریت ارسال شد و سرویس شما به زودی بررسی و فعال خواهد شد."
                ),
                notify_admins=True,
                admin_error=error_text
            )
            return

        await db_manager.mark_invoice_approved(invoice_id)
        await self._deliver_license(user_id, sub_id, license_note, invoice_id)

    # ------------------------------------------------------------------
    # PRIVATE: _deliver_license
    # ------------------------------------------------------------------
    async def _deliver_license(self, user_id: int, sub_id: str, license_note: str, invoice_id: str) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram import types as tg_types

        safe_note = html.escape(str(license_note)) if license_note else ""
        note_line = f"\n📝 نام لایسنس: <b>{safe_note}</b>" if safe_note else ""
        caption = (
            f"✅ <b>اشتراک شما با موفقیت فعال شد!</b>\n\n"
            f"🧾 شماره فاکتور: <code>{html.escape(str(invoice_id))}</code>"
            f"{note_line}\n\n"
            "از طریق دکمه زیر می‌توانید سرویس خود را مشاهده و مدیریت کنید:"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            tg_types.InlineKeyboardButton(
                text="📱 لایسنس‌های من",
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
                from bot.config import ADMIN_IDS
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                from aiogram import types as tg_types

                safe_admin_error = html.escape(str(admin_error)[:800])
                error_text = (
                    f"🚨 <b>خطا در صدور/تمدید اشتراک</b>\n\n"
                    f"👤 کاربر: <code>{user_id}</code>\n"
                    f"🧾 فاکتور: <code>{html.escape(str(invoice_id))}</code>\n\n"
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
        lock = get_invoice_lock(invoice_id)
        async with lock:
            try:
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                        invoice = await cursor.fetchone()

                    if not invoice or invoice['status'] != 'pending':
                        return False

                    cur = await db.execute(
                        "UPDATE invoices SET status = 'failed' WHERE id = ? AND status = 'pending'",
                        (invoice_id,)
                    )
                    if cur.rowcount == 0:
                        return False
                    await db.commit()

                    price_fmt = f"{invoice['final_amount']:,}"
                    safe_reason = html.escape(str(reason))
                    text = (
                        f"❌ <b>پرداخت تایید نشد</b>\n\n"
                        f"🧾 شماره فاکتور: <code>{html.escape(str(invoice_id))}</code>\n"
                        f"💰 مبلغ: <b>{price_fmt}</b> تومان\n"
                        f"📝 علت: {safe_reason}\n\n"
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
        lock = get_invoice_lock(invoice_id)
        async with lock:
            try:
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cursor:
                        invoice = await cursor.fetchone()

                    if not invoice or invoice['status'] != 'pending':
                        return False

                    cur = await db.execute(
                        "UPDATE invoices SET status = 'expired' WHERE id = ? AND status = 'pending'",
                        (invoice_id,)
                    )
                    if cur.rowcount == 0:
                        return False
                    await db.commit()

                    price_fmt = f"{invoice['final_amount']:,}"
                    text = (
                        f"⏳ <b>انقضای فاکتور</b>\n\n"
                        f"🧾 شماره فاکتور: <code>{html.escape(str(invoice_id))}</code>\n"
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