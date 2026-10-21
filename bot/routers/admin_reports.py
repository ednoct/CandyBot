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
from utils.ui_helpers import safe_edit_message
from utils.date_formatter import (
    get_current_jalali,
    get_jalali_date,
    gregorian_to_jalali,
    jalali_to_gregorian,
    get_days_in_jalali_month,
    get_persian_weekday_index,
    get_persian_weekday_name,
    parse_custom_date_input,
    JALALI_MONTH_NAMES,
    PERSIAN_WEEKDAYS_SHORT,
    PERSIAN_WEEKDAYS_FULL
)

admin_reports_router = Router()

class AdminReportStates(StatesGroup):
    waiting_for_report_group_id = State()
    waiting_for_custom_date = State()

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
async def reports_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles reports menu."""
    if not is_admin(callback): return
    if state:
        await state.clear()
    
    # We will just redirect to the advanced stats default view (all time)
    # The user wanted to replace the "Overall Bot Statistics" section.
    # To keep the export buttons accessible, we will show the main menu with the advanced stats entry.
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📊 آمار پیشرفته ربات", callback_data="stats_all"),
        types.InlineKeyboardButton(text="📣 تنظیمات گروه گزارشات", callback_data="report_group_setup")
    )
    
    # Exports
    builder.row(
        types.InlineKeyboardButton(text="📑 خروجی کاربران", callback_data="export_users"),
        types.InlineKeyboardButton(text="📑 خروجی سفارشات", callback_data="export_orders")
    )
    builder.row(
        types.InlineKeyboardButton(text="📑 خروجی تراکنش‌ها", callback_data="export_payments"),
        types.InlineKeyboardButton(text="📑 خروجی تسویه‌های نمایندگی", callback_data="export_agent_settlements")
    )
    
    # CRM
    builder.button(text="👥 پیگیری تست (CRM)", callback_data="crm_trial_followup")
    
    builder.button(text="🔙 بازگشت", callback_data="admin_back", style="danger")
    builder.adjust(1, 1, 2, 2, 1, 1)
    
    await safe_edit_message(callback, "📈 **آمار و گزارشات کندی**\n\nلطفا بخش مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")


# === ROUTER: REPORTS SETUP (TOPICS) ===
@admin_reports_router.callback_query(F.data == "report_group_setup")
async def report_setup_start_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handles report setup start via callback."""
    if not is_admin(callback): return
    
    text = (
        "آموزش تنظیم گروه :\n"
        "1 - ابتدا یک گروه  بسازید\n"
        "2 - ربات  @myidbot را عضو گروه کنید و دستور /getgroupid@myidbot داخل گروه ارسال کنید\n"
        "3 - حالت تاپیک یا انجمن گروه را از تنظیمات گروه روشن کنید\n"
        "4 - ربات خودتان را ادمین گروه کنید (مجوز مدیریت تاپیک‌ها فعال باشد)\n"
        "5 - آیدی عددی ارسال شده را در ربات ارسال کنید."
    )
    
    await state.set_state(AdminReportStates.waiting_for_report_group_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف و بازگشت", callback_data="admin_reports", style="danger")
    await safe_edit_message(callback, text, reply_markup=builder.as_markup())

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
async def fetch_stats(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles fetch stats."""
    if not is_admin(callback): return
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
        first_day_curr = now.replace(day=1, hour=0, minute=0, second=0)
        last_day_prev = first_day_curr - timedelta(seconds=1)
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
        if state:
            await state.clear()
        return await stats_custom_menu(callback, state)
        
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
    text += f"🔸 جمع کل فروش از طریق درگاه FrenzyEx: `{stats['frenzyex_sales_amount']:,}` تومان\n"
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
    # Row 3: [امروز] | [دیروز]
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
    builder.row(InlineKeyboardButton(text="❌ بستن", callback_data="admin_reports", style="danger"))
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception as e:
        pass
    
    await callback.answer()


# ============================================================
# === CUSTOM DATE & CALENDAR SYSTEM (حرفه‌ای و تعاملی) ===
# ============================================================

def build_jalali_calendar_keyboard(jy: int, jm: int) -> InlineKeyboardBuilder:
    """Creates a full 7-column interactive Jalali calendar inline keyboard."""
    builder = InlineKeyboardBuilder()
    
    # Month navigation
    if jm == 1:
        prev_y, prev_m = jy - 1, 12
    else:
        prev_y, prev_m = jy, jm - 1
        
    if jm == 12:
        next_y, next_m = jy + 1, 1
    else:
        next_y, next_m = jy, jm + 1
        
    m_name = JALALI_MONTH_NAMES[jm] if 1 <= jm <= 12 else str(jm)
    
    builder.row(
        types.InlineKeyboardButton(text="◀️ ماه قبل", callback_data=f"cal_nav:{prev_y}:{prev_m}"),
        types.InlineKeyboardButton(text=f"📅 {m_name} {jy}", callback_data="none"),
        types.InlineKeyboardButton(text="ماه بعد ▶️", callback_data=f"cal_nav:{next_y}:{next_m}")
    )
    
    # Weekday headers (شنبه تا جمعه)
    headers = [
        types.InlineKeyboardButton(text=lbl, callback_data="none")
        for lbl in PERSIAN_WEEKDAYS_SHORT
    ]
    builder.row(*headers)
    
    # Calculate days in month & starting weekday
    days_in_month = get_days_in_jalali_month(jy, jm)
    gy, gm, gd = jalali_to_gregorian(jy, jm, 1)
    start_weekday = get_persian_weekday_index(gy, gm, gd)  # 0=Saturday, 6=Friday
    
    now = datetime.now()
    cur_jy, cur_jm, cur_jd = gregorian_to_jalali(now.year, now.month, now.day)
    
    current_row = []
    # Spacers before the first day of the month
    for _ in range(start_weekday):
        current_row.append(types.InlineKeyboardButton(text="·", callback_data="none"))
        
    for day in range(1, days_in_month + 1):
        is_today = (jy == cur_jy and jm == cur_jm and day == cur_jd)
        day_text = f"🌟{day}" if is_today else str(day)
        
        current_row.append(
            types.InlineKeyboardButton(
                text=day_text,
                callback_data=f"cal_pick:{jy}:{jm}:{day}"
            )
        )
        
        if len(current_row) == 7:
            builder.row(*current_row)
            current_row = []
            
    if current_row:
        while len(current_row) < 7:
            current_row.append(types.InlineKeyboardButton(text="·", callback_data="none"))
        builder.row(*current_row)
        
    # Quick action row
    builder.row(
        types.InlineKeyboardButton(text="⚡ امروز", callback_data=f"cal_pick:{cur_jy}:{cur_jm}:{cur_jd}"),
        types.InlineKeyboardButton(text="✍️ ورود دستی تاریخ", callback_data="custom_date_manual")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به گزینه‌های تاریخ", callback_data="stats_custom", style="danger")
    )
    
    return builder


async def render_custom_stats_view(
    callback_or_message,
    start_str: str,
    end_str: str,
    title: str,
    is_message: bool = False
):
    """Fetches and renders statistics for the given datetime range."""
    stats = await db_manager.get_advanced_bot_stats(
        "WHERE created_at BETWEEN ? AND ?",
        (start_str, end_str)
    )

    text = (
        f"🗓 **{title}**\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **بخش کاربران:**\n"
        f"🔹 کاربران جدید این بازه: `{stats['total_users']}` نفر\n"
        f"🔹 کاربران دارای خرید: `{stats['users_with_purchase']}` نفر\n"
        f"🔹 اکانت‌های تست صادر شده: `{stats['test_accounts']}` مورد\n"
        f"🔹 موجودی کل کاربران: `{stats['total_balance']:,}` تومان\n"
        f"🔹 نظرسنجی‌ها: `{stats['poll_count']}` مورد (میانگین `{stats['avg_poll_rating']}` ⭐)\n\n"
        f"💰 **بخش مالی و سفارشات:**\n"
        f"🔸 تعداد کل فروش موفق: `{stats['total_sales_count']}` سفارش\n"
        f"🔸 جمع کل فروش: `{stats['total_sales_amount']:,}` تومان\n"
        f"🔸 جمع کل فروش از طریق درگاه FrenzyEx: `{stats['frenzyex_sales_amount']:,}` تومان\n"
        f"🔸 جمع کل تمدیدها: `{stats['total_renewal_amount']:,}` تومان\n"
        f"🔸 میانگین خرید هر مشتری: `{stats['avg_purchase']:,}` تومان\n"
        f"🔸 درصد تمدید از فروش: `{stats['renewal_percentage']}%`\n"
        f"🔸 نرخ تبدیل به مشتری: `{stats['conversion_rate']}%`\n"
    )

    # Encode start/end dates for CSV export callback (short format: YYYY-MM-DD)
    s_tag = start_str[:10]
    e_tag = end_str[:10]

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🗓 انتخاب تاریخ دیگر", callback_data="stats_custom"),
        types.InlineKeyboardButton(text="📑 خروجی سفارشات (CSV)", callback_data=f"exp_dt:{s_tag}:{e_tag}")
    )
    builder.row(
        types.InlineKeyboardButton(text="⏱ بازگشت به آمار کل", callback_data="stats_all", style="danger")
    )

    if is_message:
        await callback_or_message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        try:
            await callback_or_message.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        except Exception:
            pass
        await callback_or_message.answer()


@admin_reports_router.callback_query(F.data == "stats_custom")
async def stats_custom_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Interactive Custom Date & Range Dashboard."""
    if not is_admin(callback): return
    if state:
        await state.clear()
        
    now = datetime.now()
    cur_jy, cur_jm, cur_jd = gregorian_to_jalali(now.year, now.month, now.day)
    m_name = JALALI_MONTH_NAMES[cur_jm]
    w_name = get_persian_weekday_name(now.year, now.month, now.day)
    today_jalali_str = f"{w_name} {cur_jd} {m_name} {cur_jy}"
    
    text = (
        "🗓 **مشاهده آمار در تاریخ و بازه مشخص**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📅 امروز: **{today_jalali_str}**\n\n"
        "یکی از بازه‌های آماده را انتخاب کنید، با تقویم هوشمند روز دقیق را تعیین نمایید، یا تاریخ دلخواهتان را تایپ کنید:"
    )
    
    builder = InlineKeyboardBuilder()
    
    # Row 1: Quick range presets
    builder.row(
        types.InlineKeyboardButton(text="⚡ ۷ روز اخیر", callback_data="stats_quick:7d"),
        types.InlineKeyboardButton(text="⚡ ۳۰ روز اخیر", callback_data="stats_quick:30d")
    )
    # Row 2: Week and Jalali Month presets
    builder.row(
        types.InlineKeyboardButton(text="⚡ این هفته (از شنبه)", callback_data="stats_quick:this_week"),
        types.InlineKeyboardButton(text="⚡ این ماه شمسی", callback_data="stats_quick:this_month")
    )
    # Row 3: Previous Jalali month
    builder.row(
        types.InlineKeyboardButton(text="⚡ ماه قبل شمسی", callback_data="stats_quick:prev_month")
    )
    # Row 4: Interactive Jalali Calendar
    builder.row(
        types.InlineKeyboardButton(text="🗓 تقویم شمسی هوشمند (انتخاب روز)", callback_data=f"cal_nav:{cur_jy}:{cur_jm}")
    )
    # Row 5: Manual text input
    builder.row(
        types.InlineKeyboardButton(text="✍️ ورود دستی تاریخ یا بازه", callback_data="custom_date_manual")
    )
    # Row 6: Back
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به آمار کل", callback_data="stats_all", style="danger")
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()


@admin_reports_router.callback_query(F.data.startswith("stats_quick:"))
async def stats_quick_handler(callback: types.CallbackQuery):
    """Handles quick preset date ranges."""
    if not is_admin(callback): return
    range_type = callback.data.split(":")[1]
    now = datetime.now()
    cur_jy, cur_jm, cur_jd = gregorian_to_jalali(now.year, now.month, now.day)
    
    if range_type == "7d":
        start_dt = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0)
        start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
        end_str = now.strftime('%Y-%m-%d 23:59:59')
        title = "آمار ۷ روز اخیر"
    elif range_type == "30d":
        start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0)
        start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
        end_str = now.strftime('%Y-%m-%d 23:59:59')
        title = "آمار ۳۰ روز اخیر"
    elif range_type == "this_week":
        w_idx = get_persian_weekday_index(now.year, now.month, now.day)
        sat_dt = (now - timedelta(days=w_idx)).replace(hour=0, minute=0, second=0)
        start_str = sat_dt.strftime('%Y-%m-%d 00:00:00')
        end_str = now.strftime('%Y-%m-%d 23:59:59')
        title = "آمار هفته جاری (از شنبه تا کنون)"
    elif range_type == "this_month":
        gy, gm, gd = jalali_to_gregorian(cur_jy, cur_jm, 1)
        start_str = f"{gy:04d}-{gm:02d}-{gd:02d} 00:00:00"
        end_str = now.strftime('%Y-%m-%d 23:59:59')
        m_name = JALALI_MONTH_NAMES[cur_jm]
        title = f"آمار ماه جاری ({m_name} {cur_jy})"
    elif range_type == "prev_month":
        if cur_jm == 1:
            p_jy, p_jm = cur_jy - 1, 12
        else:
            p_jy, p_jm = cur_jy, cur_jm - 1
        days_in_p = get_days_in_jalali_month(p_jy, p_jm)
        gy_s, gm_s, gd_s = jalali_to_gregorian(p_jy, p_jm, 1)
        gy_e, gm_e, gd_e = jalali_to_gregorian(p_jy, p_jm, days_in_p)
        start_str = f"{gy_s:04d}-{gm_s:02d}-{gd_s:02d} 00:00:00"
        end_str = f"{gy_e:04d}-{gm_e:02d}-{gd_e:02d} 23:59:59"
        m_name = JALALI_MONTH_NAMES[p_jm]
        title = f"آمار ماه قبل ({m_name} {p_jy})"
    else:
        return await callback.answer("بازه نامعتبر", show_alert=True)
        
    await render_custom_stats_view(callback, start_str, end_str, title)


@admin_reports_router.callback_query(F.data.startswith("cal_nav:"))
async def cal_nav_handler(callback: types.CallbackQuery):
    """Navigates through Jalali calendar months."""
    if not is_admin(callback): return
    _, jy_str, jm_str = callback.data.split(":")
    jy, jm = int(jy_str), int(jm_str)
    
    builder = build_jalali_calendar_keyboard(jy, jm)
    m_name = JALALI_MONTH_NAMES[jm] if 1 <= jm <= 12 else str(jm)
    
    text = (
        f"🗓 **تقویم هوشمند شمسی — {m_name} {jy}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "برای مشاهده آمار فروش و کاربران، روی روز مورد نظر کلیک کنید:"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()


@admin_reports_router.callback_query(F.data.startswith("cal_pick:"))
async def cal_pick_handler(callback: types.CallbackQuery):
    """Picks a specific Jalali day and shows its stats."""
    if not is_admin(callback): return
    _, jy_str, jm_str, jd_str = callback.data.split(":")
    jy, jm, jd = int(jy_str), int(jm_str), int(jd_str)
    
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    start_str = f"{gy:04d}-{gm:02d}-{gd:02d} 00:00:00"
    end_str = f"{gy:04d}-{gm:02d}-{gd:02d} 23:59:59"
    
    w_name = get_persian_weekday_name(gy, gm, gd)
    m_name = JALALI_MONTH_NAMES[jm] if 1 <= jm <= 12 else str(jm)
    title = f"آمار روز {w_name} {jd} {m_name} {jy} ({gy:04d}-{gm:02d}-{gd:02d})"
    
    await render_custom_stats_view(callback, start_str, end_str, title)


@admin_reports_router.callback_query(F.data == "custom_date_manual")
async def custom_date_manual_start(callback: types.CallbackQuery, state: FSMContext):
    """Prompts admin to enter date or range as text."""
    if not is_admin(callback): return
    await state.set_state(AdminReportStates.waiting_for_custom_date)
    
    text = (
        "✍️ **ورود دستی تاریخ یا بازه زمانی**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "لطفاً تاریخ یا بازه مورد نظرتان را به یکی از فرمت‌های زیر ارسال کنید:\n\n"
        "📌 **یک روز مشخص:**\n"
        "• `1403/07/24` یا `1403-07-24`\n"
        "• `2024-10-15`\n\n"
        "📌 **بازه زمانی دلخواه:**\n"
        "• `1403/07/01 تا 1403/07/24`\n"
        "• `1403/07/01 - 1403/07/24`\n"
        "• `2024-10-01 to 2024-10-15`\n\n"
        "*(ارقام فارسی یا انگلیسی قابل قبول هستند)*"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data="stats_custom"))
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()


@admin_reports_router.message(AdminReportStates.waiting_for_custom_date)
async def custom_date_process(message: types.Message, state: FSMContext):
    """Processes manual date input from the admin."""
    if not is_admin(message): return
    
    parsed = parse_custom_date_input(message.text)
    if not parsed:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data="stats_custom"))
        return await message.answer(
            "❌ **فرمت تاریخ وارد شده نامعتبر است!**\n\n"
            "لطفاً تاریخ را به صورت سال/ماه/روز ارسال کنید.\n"
            "• مثال یک روز: `1403/07/24`\n"
            "• مثال بازه زمانی: `1403/07/01 تا 1403/07/24`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
    await state.clear()
    start_str, end_str, title = parsed
    await render_custom_stats_view(message, start_str, end_str, title, is_message=True)


@admin_reports_router.callback_query(F.data.startswith("exp_dt:"))
async def export_custom_date_orders(callback: types.CallbackQuery):
    """Exports orders in the custom date range to a CSV file."""
    if not is_admin(callback): return
    _, s_tag, e_tag = callback.data.split(":")
    start_str = f"{s_tag} 00:00:00"
    end_str = f"{e_tag} 23:59:59"
    
    await callback.answer("در حال ساخت فایل اکسل سفارشات...", show_alert=False)
    
    rows = await db_manager.get_orders_in_timeframe(start_str, end_str)
    if not rows:
        return await callback.message.answer(f"❌ هیچ سفارشی با وضعیت موفق در بازه {s_tag} تا {e_tag} یافت نشد.")
        
    headers = [
        "شناسه فاکتور",
        "آیدی کاربر",
        "نام کاربری",
        "پلن",
        "مدت (روز)",
        "حجم (گیگابایت)",
        "مبلغ پرداختی (تومان)",
        "وضعیت",
        "نوع سفارش",
        "تاریخ و زمان ثبت"
    ]
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    
    for r in rows:
        order_type = "تمدید سرویس" if r['renew_license_id'] else "خرید جدید"
        writer.writerow([
            r['id'],
            r['user_id'],
            r['username'] or '',
            r['plan_name'] or str(r['plan_id'] or ''),
            r['days'] or 0,
            r['gb'] or 0,
            r['final_amount'] or 0,
            r['status'],
            order_type,
            r['created_at']
        ])
        
    output.seek(0)
    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(
        output.getvalue().encode('utf-8-sig'),
        filename=f"orders_{s_tag}_to_{e_tag}.csv"
    )
    
    await callback.message.answer_document(
        file,
        caption=f"📑 **خروجی سفارشات بازه {s_tag} تا {e_tag}**\nتعداد کل سفارشات موفق: `{len(rows)}` مورد",
        parse_mode="Markdown"
    )

# === ROUTER: EXPORT DATA ===
@admin_reports_router.callback_query(F.data.startswith("export_"))
async def export_data(callback: types.CallbackQuery):
    """Handles export data."""
    if not is_admin(callback): return
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

# === ROUTER: EXPORT AGENT SETTLEMENTS (IMMUNE TO CLEANUPS) ===
@admin_reports_router.callback_query(F.data == "export_agent_settlements")
async def export_agent_settlements_handler(callback: types.CallbackQuery):
    """Exports all settled agent payouts from day 1 with full details."""
    if not is_admin(callback):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer("در حال ساخت فایل خروجی تسویه‌های نمایندگی...", show_alert=False)

    rows = await db_manager.get_all_settled_settlements()
    if not rows:
        return await callback.message.answer("❌ هیچ تسویه حسابی با وضعیت «تسویه شده» در دیتابیس ثبت نشده است.")

    headers = [
        "شناسه تسویه",
        "آیدی عددی نماینده",
        "نام کاربری",
        "مبلغ تومانی",
        "مقدار گرام (TON)",
        "نرخ هر گرام (تومان)",
        "آدرس کیف پول TON",
        "لینک هش تراکنش (TxHash)",
        "تاریخ ثبت درخواست",
        "تاریخ و زمان تسویه"
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in rows:
        writer.writerow([
            r['id'],
            r['agent_id'],
            r['username'] or '',
            r['amount_irt'],
            r['amount_gram'],
            r['gram_price'],
            r['wallet_address'],
            r['tx_hash'] or '',
            r['created_at'],
            r['settled_at'] or ''
        ])

    output.seek(0)
    from aiogram.types import BufferedInputFile
    date_str = datetime.now().strftime("%Y-%m-%d")
    file = BufferedInputFile(
        output.getvalue().encode('utf-8-sig'),
        filename=f"agent_settlements_{date_str}.csv"
    )

    await callback.message.answer_document(
        file,
        caption="📑 <b>خروجی کامل تسویه‌های انجام‌شده نمایندگی (از روز اول)</b>\n\nاین رکوردها در دیتابیس محفوظ بوده و از پاکسازی‌های دوره‌ای مصون می‌باشند.",
        parse_mode="HTML"
    )

# === FIX BUG-03: CRM TRIAL FOLLOW-UP HANDLER ===
@admin_reports_router.callback_query(F.data == "crm_trial_followup")
async def crm_trial_followup(callback: types.CallbackQuery):
    if not is_admin(callback):
        return

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT DISTINCT u.id, u.username, u.created_at
            FROM users u
            LEFT JOIN free_trial_usage ftu ON ftu.user_id = u.id
            LEFT JOIN payment_reports pr ON pr.user_id = u.id AND pr.payment_method = 'free_test'
            LEFT JOIN invoices inv_test ON inv_test.user_id = u.id AND inv_test.base_price = 0
            WHERE (ftu.user_id IS NOT NULL OR pr.id IS NOT NULL OR inv_test.id IS NOT NULL)
              AND u.id NOT IN (
                  SELECT DISTINCT user_id FROM invoices
                  WHERE base_price > 0 AND status IN ('paid', 'approved', 'completed')
              )
            ORDER BY u.created_at DESC
            LIMIT 50
        """
        async with db.execute(query) as cursor:
            trial_only_users = await cursor.fetchall()

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_reports", style="danger")

    if not trial_only_users:
        return await safe_edit_message(
            callback,
            "✅ هیچ کاربری که صرفاً تست رایگان گرفته و خریدی نکرده باشد یافت نشد.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    lines = ["📊 <b>لیست کاربران تست رایگان بدون خرید (۵۰ نفر اخیر):</b>\n"]
    for idx, u in enumerate(trial_only_users, start=1):
        uname = f"@{u['username']}" if u['username'] else "بدون نام کاربری"
        lines.append(f"{idx}. <code>{u['id']}</code> ({uname})")

    await safe_edit_message(
        callback,
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# === NEUTRAL BUTTONS HANDLER (PREVENTS "QUERY IS TOO OLD") ===
@admin_reports_router.callback_query(F.data.in_(["noop", "none"]))
async def handle_noop(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
