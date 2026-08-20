"""
admin_reports.py
----------------
Module containing functionalities for admin_reports.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import aiosqlite
import csv
import io
from .admin import is_admin
from database import db_manager

admin_reports_router = Router()

# === ROUTER: REPORTS MENU ===
@admin_reports_router.callback_query(F.data == "admin_reports")
async def reports_menu(callback: types.CallbackQuery):
    """Handles reports menu."""
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 آمار کلی ربات", callback_data="stats_all")
    builder.button(text="🕐 آمار روز فعلی", callback_data="stats_today")
    builder.button(text="🕐 آمار روز گذشته", callback_data="stats_yesterday")
    builder.button(text="🕐 آمار ماه فعلی", callback_data="stats_month")
    
    # Exports
    builder.button(text="📑 خروجی کاربران", callback_data="export_users")
    builder.button(text="📑 خروجی سفارشات", callback_data="export_orders")
    builder.button(text="📑 خروجی تراکنش‌ها", callback_data="export_payments")
    
    # CRM
    builder.button(text="👥 پیگیری تست (CRM)", callback_data="crm_trial_followup")
    
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1, 2, 1, 1, 3, 1, 1)
    
    await callback.message.edit_text("📈 **آمار و گزارشات کندی**\n\nلطفا بازه زمانی مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: FETCH STATS ===
@admin_reports_router.callback_query(F.data.startswith("stats_"))
async def fetch_stats(callback: types.CallbackQuery):
    """Handles fetch stats."""
    if not is_admin(callback.message): return
    action = callback.data.split("_")[1]
    
    clause = ""
    params = ()
    title = "📊 آمار کلی ربات"
    
    now = datetime.now()
    
    if action == "today":
        start = now.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at >= ?"
        params = (start,)
        title = "🕐 آمار روز فعلی"
    elif action == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        end = yesterday.replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at BETWEEN ? AND ?"
        params = (start, end)
        title = "🕐 آمار روز گذشته"
    elif action == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at >= ?"
        params = (start,)
        title = "🕐 آمار ماه فعلی"
        
    stats = await db_manager.get_bot_stats(clause, params)
    
    text = f"**{title}**\n━━━━━━━━━━━━━━━━━━\n"
    text += f"👥 **تعداد کاربران:** {stats['users']} نفر\n"
    text += f"🛍 **تعداد سفارشات:** {stats['orders']} عدد\n"
    text += f"🔑 **اکانت‌های تست:** {stats['tests']} عدد\n"
    text += f"💸 **جمع مبلغ سفارشات:** {stats['sales']} تومان\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_reports")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: EXPORT DATA ===
@admin_reports_router.callback_query(F.data.startswith("export_"))
async def export_data(callback: types.CallbackQuery):
    """Handles export data."""
    if not is_admin(callback.message): return
    action = callback.data.split("_")[1]
    
    table_map = {
        "users": "users",
        "orders": "orders",
        "payments": "payments"
    }
    
    table = table_map.get(action)
    if not table:
        return await callback.answer("❌ جدول نامعتبر", show_alert=True)
        
    await callback.answer("در حال ساخت فایل خروجی...", show_alert=False)
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if table exists
        async with db.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'") as cursor:
            if not await cursor.fetchone():
                return await callback.message.answer(f"❌ دیتایی برای خروجی {action} یافت نشد (جدول وجود ندارد).")
                
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT * FROM {table}") as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return await callback.message.answer(f"❌ دیتایی برای خروجی {action} یافت نشد.")
                
            headers = rows[0].keys()
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            
            for row in rows:
                writer.writerow([row[col] for col in headers])
                
            output.seek(0)
            
            from aiogram.types import BufferedInputFile
            date_str = datetime.now().strftime("%Y-%m-%d")
            file = BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename=f"{table}_{date_str}.csv")
            
            await callback.message.answer_document(file, caption=f"🪪 خروجی دیتای {table}")

# === ROUTER: CRM TRIAL FOLLOW-UP ===
@admin_reports_router.callback_query(F.data == "crm_trial_followup")
async def crm_trial_followup(callback: types.CallbackQuery):
    """Handles crm trial followup."""
    if not is_admin(callback.message): return
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Find users who have a 'free_test' record in payment_reports OR invoices with plan_id denoting test
        # but do NOT have a successful paid invoice/payment_report.
        # Since CandyBot's schema is a mix of legacy and new, we'll check both.
        query = """
        SELECT DISTINCT u.id, u.username
        FROM users u
        JOIN payment_reports pr ON pr.user_id = u.id OR pr.id_user = u.id
        WHERE pr.payment_method = 'free_test'
        AND u.id NOT IN (
            SELECT user_id FROM invoices WHERE status IN ('paid', 'approved')
        )
        LIMIT 20
        """
        try:
            async with db.execute(query) as cur:
                users = await cur.fetchall()
        except Exception:
            users = []
            
    if not users:
        await callback.answer("کاربری که فقط تست دریافت کرده باشد یافت نشد.", show_alert=True)
        return
        
    text = "👥 **گزارش پیگیری (CRM) - کاربرانی که تست گرفتند اما خرید نکردند:**\n\n"
    for idx, u in enumerate(users, 1):
        un = f"@{u['username']}" if u['username'] else "بدون نام کاربری"
        text += f"{idx}. <code>{u['id']}</code> - {un}\n"
        
    if len(users) == 20:
        text += "\n*فقط ۲۰ مورد اول نمایش داده شد.*"
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_reports")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
