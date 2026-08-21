"""
user_free_trial.py
------------------
Router for user free trial flow.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiosqlite
from database import db_manager
import uuid
import time
import logging

user_free_trial_router = Router()

@user_free_trial_router.callback_query(F.data == "free_test")
async def request_free_trial(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # 1. Check if free trial is enabled
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        async def get_s(k, default=""):
            async with db.execute("SELECT value FROM settings WHERE key=?", (k,)) as c:
                r = await c.fetchone()
                return r[0] if r else default
                
        enabled = await get_s("free_test_enabled", "0")
        if enabled != "1":
            return await callback.answer("❌ سرویس تست رایگان در حال حاضر غیرفعال است.", show_alert=True)
            
        # 2. Check if user already used free trial
        async with db.execute("SELECT 1 FROM free_trial_usage WHERE user_id = ?", (user_id,)) as c:
            used = await c.fetchone()
            if used:
                return await callback.answer("❌ شما قبلا از سرویس تست رایگان استفاده کرده‌اید.", show_alert=True)
                
        # 3. Check daily limit
        limit = int(await get_s("free_test_daily_limit", "50"))
        async with db.execute("SELECT COUNT(*) FROM free_trial_usage WHERE date(created_at) = date('now')") as c:
            count = (await c.fetchone())[0]
            if count >= limit:
                return await callback.answer("❌ ظرفیت سرویس تست رایگان برای امروز تکمیل شده است. فردا مراجعه کنید.", show_alert=True)
                
        panel_id = int(await get_s("free_test_panel_id", "0"))
        if panel_id == 0:
            return await callback.answer("❌ پنل تست رایگان توسط مدیریت تنظیم نشده است.", show_alert=True)
            
        gb = int(await get_s("free_test_gb", "1"))
        days = int(await get_s("free_test_days", "1"))
        
        # All checks passed, let's provision!
        await callback.message.edit_text("⏳ در حال ساخت اکانت تست... لطفا شکیبا باشید.")
        
        # Create a dummy invoice for tracking
        invoice_id = str(uuid.uuid4().hex)[:8].upper()
        
        from payment.confirm import PaymentConfirmationManager
        
        # Register usage
        await db.execute("INSERT INTO free_trial_usage (user_id) VALUES (?)", (user_id,))
        
        # Save dummy invoice
        await db.execute(
            "INSERT INTO invoices (id, user_id, plan_id, days, gb, base_price, final_amount, status, panel_id, license_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (invoice_id, user_id, 0, days, gb, 0, 0, 'processing', panel_id, 'Free_Trial')
        )
        await db.commit()
        
    # Provision
    pcm = PaymentConfirmationManager(callback.bot)
    try:
        dummy_invoice = {
            'id': invoice_id,
            'user_id': user_id,
            'days': days,
            'gb': gb,
            'license_note': 'Free_Trial',
            'panel_id': panel_id,
            'renew_license_id': None
        }
        await pcm._provision_and_deliver(invoice_id, user_id, dummy_invoice, is_free_test=True)
    except Exception as e:
        logging.error(f"Free trial provision error: {e}")
        await callback.message.answer("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
