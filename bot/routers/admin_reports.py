"""
admin_reports.py
----------------
Module containing functionalities for admin_reports.
"""
# === IMPORTS ===
from aiogram import Router, F, types, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import aiosqlite
import csv
import io
from .admin import is_admin
from database import db_manager

admin_reports_router = Router()

class AdminReportStates(StatesGroup):
    waiting_for_report_group_id = State()

TOPICS = {
    "buy_report": "🛍 گزارش های خرید",
    "service_report": "📌 گزارش خرید خدمات",
    "test_report": "🔑 گزارش اکانت تست",
    "other_report": "⚙️ سایر گزارشات",
    "error_report": "❌ گزارش خطا ها",
    "finance_report": "💰 گزارش مالی",
    "commission_report": "🎁 گزارش پورسانت ها",
    "nightly_report": "🌙 گزارش شبانه",
    "announcement_report": "📝 گزارش اطلاع رسانی ها"
}


# === ROUTER: REPORTS MENU ===
@admin_reports_router.callback_query(F.data == "admin_reports")
async def reports_menu(callback: types.CallbackQuery):
    """Handles reports menu."""
    if not is_admin(callback.message): return
    
    # We will just redirect to the advanced stats default view (all time)
    # The user wanted to replace the "Overall Bot Statistics" section.
    # To keep the export buttons accessible, we will show the main menu with the advanced stats entry.
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 آمار پیشرفته ربات", callback_data="stats_all")
    
    # Reports Settings
    builder.button(text="📣 تنظیمات گروه گزارشات", callback_data="report_group_setup")
    
    # Exports
    builder.button(text="📑 خروجی کاربران", callback_data="export_users")
    builder.button(text="📑 خروجی سفارشات", callback_data="export_orders")
    builder.button(text="📑 خروجی تراکنش‌ها", callback_data="export_payments")
    
    # CRM
    builder.button(text="👥 پیگیری تست (CRM)", callback_data="crm_trial_followup")
    
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1, 1, 3, 1, 1)
    
    await callback.message.edit_text("📈 **آمار و گزارشات کندی**\n\nلطفا بخش مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")


# === ROUTER: REPORTS SETUP (TOPICS) ===
@admin_reports_router.callback_query(F.data == "report_group_setup")
async def report_setup_start_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handles report setup start via callback."""
    if not is_admin(callback.message): return
    
    text = (
        "آموزش تنظیم گروه :\n"
        "1 - ابتدا یک گروه  بسازید\n"
        "2 - ربات  @myidbot را عضو گروه کنید و دستور /getgroupid@myidbot داخل گروه ارسال کنید\n"
        "3 - حالت تاپیک یا انجمن گروه را از تنظیمات گروه روشن کنید\n"
        "4 - ربات خودتان را ادمین گروه کنید (مجوز مدیریت تاپیک‌ها فعال باشد)\n"
        "5 - آیدی عددی ارسال شده را در ربات ارسال کنید."
    )
    
    await state.set_state(AdminReportStates.waiting_for_report_group_id)
    await callback.message.edit_text(text)
    await callback.answer()

@admin_reports_router.message(F.text == "📣 گزارشات ربات")
async def report_setup_start(message: types.Message, state: FSMContext):
    """Handles report setup start via message."""
    if not is_admin(message): return
    
    text = (
        "آموزش تنظیم گروه :\n"
        "1 - ابتدا یک گروه  بسازید\n"
        "2 - ربات  @myidbot را عضو گروه کنید و دستور /getgroupid@myidbot داخل گروه ارسال کنید\n"
        "3 - حالت تاپیک یا انجمن گروه را از تنظیمات گروه روشن کنید\n"
        "4 - ربات خودتان را ادمین گروه کنید (مجوز مدیریت تاپیک‌ها فعال باشد)\n"
        "5 - آیدی عددی ارسال شده را در ربات ارسال کنید."
    )
    
    await state.set_state(AdminReportStates.waiting_for_report_group_id)
    await message.answer(text)

@admin_reports_router.message(AdminReportStates.waiting_for_report_group_id)
async def report_setup_process(message: types.Message, state: FSMContext, bot: Bot):
    """Handles report setup process."""
    if not is_admin(message): return
    
    group_id_str = message.text.strip()
    
    try:
        chat = await bot.get_chat(group_id_str)
    except Exception as e:
        return await message.answer(f"❌ خطا در یافتن گروه (مطمئن شوید ربات ادمین گروه است): {e}")
        
    if not chat.is_forum:
        return await message.answer("❌ گروه انتخاب شده حالت 'انجمن' (Forum) ندارد. لطفا از تنظیمات گروه آن را فعال کنید.")
        
    wait_msg = await message.answer("در حال ساخت تاپیک‌ها... لطفا صبر کنید.")
    
    await db_manager.set_report_setting("report_group_id", str(chat.id))
    
    created_topics = 0
    for key, name in TOPICS.items():
        try:
            topic = await bot.create_forum_topic(chat.id, name)
            await db_manager.set_report_setting(key, str(topic.message_thread_id))
            created_topics += 1
        except Exception as e:
            await message.answer(f"❌ خطا در ساخت تاپیک '{name}': {e}")
            
    await state.set_state(None)
    await wait_msg.edit_text(f"✅ تنظیمات با موفقیت انجام شد و {created_topics} تاپیک ساخته شد.")

# === ROUTER: FETCH STATS ===
@admin_reports_router.callback_query(F.data.startswith("stats_"))
async def fetch_stats(callback: types.CallbackQuery):
    """Handles fetch stats."""
    if not is_admin(callback.message): return
    action = callback.data.split("_")[1]
    
    clause = ""
    params = ()
    title = "📊 آمار کلی ربات (تمام زمان‌ها)"
    
    now = datetime.now()
    
    if action == "today":
        start = now.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at >= ?"
        params = (start,)
        title = "🕐 آمار امروز"
    elif action == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        end = yesterday.replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at BETWEEN ? AND ?"
        params = (start, end)
        title = "🕐 آمار دیروز"
    elif action == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at >= ?"
        params = (start,)
        title = "🕐 آمار ماه فعلی"
    elif action == "prevmonth":
        # First day of current month
        first_day_curr = now.replace(day=1, hour=0, minute=0, second=0)
        # Last day of prev month
        last_day_prev = first_day_curr - timedelta(seconds=1)
        # First day of prev month
        first_day_prev = last_day_prev.replace(day=1, hour=0, minute=0, second=0)
        
        start = first_day_prev.strftime('%Y-%m-%d %H:%M:%S')
        end = last_day_prev.strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at BETWEEN ? AND ?"
        params = (start, end)
        title = "🕐 آمار ماه قبل"
    elif action == "hour":
        one_hour_ago = now - timedelta(hours=1)
        start = one_hour_ago.strftime('%Y-%m-%d %H:%M:%S')
        clause = "WHERE created_at >= ?"
        params = (start,)
        title = "🕐 آمار یک ساعت اخیر"
    elif action == "custom":
        await callback.answer("این بخش در آپدیت‌های بعدی اضافه خواهد شد.", show_alert=True)
        return
        
    stats = await db_manager.get_advanced_bot_stats(clause, params)
    
    text = f"**{title}**\n━━━━━━━━━━━━━━━━━━\n\n"
    text += "👤 **بخش کاربران:**\n"
    text += f"🔹 تعداد کل کاربران: `{stats['total_users']}`\n"
    text += f"🔹 کاربران دارای خرید: `{stats['users_with_purchase']}`\n"
    text += f"🔹 اکانت‌های تست دریافت شده: `{stats['test_accounts']}`\n"
    text += f"🔹 موجودی کل کاربران: `{stats['total_balance']:,}` تومان\n"
    text += f"🔹 نظرسنجی‌ها: `{stats['poll_count']}` مورد (میانگین `{stats['avg_poll_rating']}` ⭐)\n\n"
    
    text += "💰 **بخش مالی و فروش:**\n"
    text += f"🔸 تعداد کل فروش: `{stats['total_sales_count']}`\n"
    text += f"🔸 تعداد کل فروش سرویس‌های فعال: `{stats['active_services_sales_count']}`\n"
    text += f"🔸 جمع کل فروش: `{stats['total_sales_amount']:,}` تومان\n"
    text += f"🔸 جمع کل فروش سرویس‌های فعال: `{stats['active_services_sales_amount']:,}` تومان\n"
    text += f"🔸 جمع کل تمدید: `{stats['total_renewal_amount']:,}` تومان\n"
    text += f"🔸 نرخ تبدیل به مشتری: `{stats['conversion_rate']}%`\n"
    text += f"🔸 میانگین خرید هر مشتری: `{stats['avg_purchase']:,}` تومان\n"
    text += f"🔸 درآمد پیش‌بینی‌شده ماهانه: `{stats['estimated_monthly_revenue']:,}` تومان\n"
    text += f"🔸 درصد تمدید از فروش: `{stats['renewal_percentage']}%`\n"
    
    builder = InlineKeyboardBuilder()
    
    from aiogram.types import InlineKeyboardButton
    # Row 1
    builder.row(InlineKeyboardButton(text="⏱ آمار کل", callback_data="stats_all"))
    # Row 2
    builder.row(InlineKeyboardButton(text="⏱ یک ساعت اخیر", callback_data="stats_hour"))
    # Row 3: [امروز] | [دیروز] -> In code from right to left: Today | Yesterday
    builder.row(
        InlineKeyboardButton(text="امروز ☁️", callback_data="stats_today"),
        InlineKeyboardButton(text="دیروز ☀️", callback_data="stats_yesterday")
    )
    # Row 4: [ماه قبل] | [ماه فعلی]
    builder.row(
        InlineKeyboardButton(text="ماه قبل ☁️", callback_data="stats_prevmonth"),
        InlineKeyboardButton(text="ماه فعلی ☀️", callback_data="stats_month")
    )
    # Row 5
    builder.row(InlineKeyboardButton(text="🗓 مشاهده آمار در تاریخ مشخص", callback_data="stats_custom"))
    # Row 6
    builder.row(InlineKeyboardButton(text="❌ بستن", callback_data="admin_reports"))
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception as e:
        # Ignore message not modified error
        pass
    
    await callback.answer()

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
