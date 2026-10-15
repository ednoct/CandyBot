"""
admin_agent.py
--------------
Admin router for managing the Commission Agency system (تنظیمات نمایندگان).
Handles agency settings, unsettled settlement orders, and settlement activation requests.
"""

import logging
import math
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.routers.admin import is_admin
from bot.states import AdminAgentStates
from bot.config import ADMIN_IDS
from database import db_manager

logger = logging.getLogger(__name__)

admin_agent_router = Router()


# === ROUTER: MAIN ADMIN AGENT MENU ===
@admin_agent_router.callback_query(F.data == "admin_agent")
async def admin_agent_menu(callback: types.CallbackQuery, state: FSMContext):
    """Displays the main Agent Settings menu with live pending badges."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await state.clear()
    await callback.answer()

    # Live counters for badges
    try:
        counts = await db_manager.get_admin_dashboard_counts()
    except Exception:
        counts = {}

    pending_settlements = counts.get('pending_settlements', 0)
    pending_activations = counts.get('pending_activations', 0)

    def _badge(label, n):
        return f"{label} ({n} 🔴)" if n > 0 else label

    text = (
        "🏬 <b>تنظیمات و مدیریت نمایندگان</b>\n\n"
        "از گزینه‌های زیر جهت پیکربندی سیستم نمایندگی، رسیدگی به تسویه‌ها و فعالسازی حساب‌ها استفاده فرمایید:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📝 تنظیم متن پیشفرض", callback_data="agent_admin_text"),
        types.InlineKeyboardButton(text="📊 تنظیم درصد کمیسیون", callback_data="agent_admin_percent")
    )
    builder.row(
        types.InlineKeyboardButton(
            text=_badge("⏳ تسویه نشده‌ها", pending_settlements),
            callback_data="agent_unsettled_page_0"
        ),
        types.InlineKeyboardButton(
            text=_badge("📩 فعالسازی تسویه", pending_activations),
            callback_data="agent_act_page_0"
        )
    )
    builder.row(
        types.InlineKeyboardButton(text="🎯 تنظیم حداقل موجودی تسویه", callback_data="agent_admin_min_settle")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_panel_start", style="danger")
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise


# === SETTING 1: DEFAULT TEXT ===
@admin_agent_router.callback_query(F.data == "agent_admin_text")
async def set_default_text_start(callback: types.CallbackQuery, state: FSMContext):
    """Starts default agency text configuration."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    current_text = await db_manager.get_setting("agent_default_text", "تنظیم نشده")

    text = (
        "📝 <b>تنظیم متن پیشفرض نمایندگی</b>\n\n"
        f"<b>متن فعلی:</b>\n{current_text}\n\n"
        "لطفاً متن پیشفرض جدید را ارسال نمایید:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="admin_agent", style="danger"))

    await state.set_state(AdminAgentStates.waiting_for_default_text)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.message(AdminAgentStates.waiting_for_default_text)
async def process_default_text(message: types.Message, state: FSMContext):
    """Saves the new default agency text."""
    if message.from_user.id not in ADMIN_IDS:
        return

    new_text = (message.text or "").strip()
    if not new_text:
        return await message.answer("❌ متن نمی‌تواند خالی باشد. لطفاً مجدداً ارسال کنید.")

    await db_manager.set_setting("agent_default_text", new_text)
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))

    await message.answer("✅ متن پیشفرض نمایندگی با موفقیت به‌روزرسانی شد.", reply_markup=builder.as_markup())


# === SETTING 2: COMMISSION PERCENT ===
@admin_agent_router.callback_query(F.data == "agent_admin_percent")
async def set_commission_percent_start(callback: types.CallbackQuery, state: FSMContext):
    """Starts commission percentage configuration."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    current_pct = await db_manager.get_setting("agent_commission_percent", "15")

    text = (
        "📊 <b>تنظیم درصد کمیسیون نمایندگان</b>\n\n"
        f"درصد کمیسیون فعلی: <b>{current_pct}٪</b>\n\n"
        "لطفاً درصد جدید را به صورت عدد وارد فرمایید (مثلاً 15 یا 20):"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="admin_agent", style="danger"))

    await state.set_state(AdminAgentStates.waiting_for_commission_percent)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.message(AdminAgentStates.waiting_for_commission_percent)
async def process_commission_percent(message: types.Message, state: FSMContext):
    """Saves the new commission percent."""
    if message.from_user.id not in ADMIN_IDS:
        return

    raw = (message.text or "").strip().replace("%", "").replace("٪", "")
    try:
        pct = float(raw)
        if pct < 0 or pct > 100:
            raise ValueError
    except ValueError:
        return await message.answer("❌ لطفاً یک عدد معتبر بین 0 تا 100 وارد کنید.")

    # Format cleanly (int if integer)
    pct_str = str(int(pct)) if pct.is_integer() else str(pct)
    await db_manager.set_setting("agent_commission_percent", pct_str)
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))

    await message.answer(f"✅ درصد کمیسیون نمایندگان با موفقیت روی <b>{pct_str}٪</b> تنظیم شد.", reply_markup=builder.as_markup(), parse_mode="HTML")


# === SETTING 3: MINIMUM SETTLEMENT AMOUNT ===
@admin_agent_router.callback_query(F.data == "agent_admin_min_settle")
async def set_min_settlement_start(callback: types.CallbackQuery, state: FSMContext):
    """Starts minimum settlement amount configuration."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    current_min = await db_manager.get_setting("agent_min_settlement_amount", "1000000")
    try:
        current_min_int = int(current_min)
    except ValueError:
        current_min_int = 1000000

    text = (
        "🎯 <b>تنظیم حداقل موجودی برای ثبت درخواست تسویه</b>\n\n"
        f"حداقل موجودی فعلی: <b>{current_min_int:,} تومان</b>\n\n"
        "لطفاً مبلغ جدید را به <b>تومان</b> ارسال فرمایید (به صورت عدد انگلیسی):"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="admin_agent", style="danger"))

    await state.set_state(AdminAgentStates.waiting_for_min_settlement)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.message(AdminAgentStates.waiting_for_min_settlement)
async def process_min_settlement(message: types.Message, state: FSMContext):
    """Saves the new minimum settlement amount."""
    if message.from_user.id not in ADMIN_IDS:
        return

    raw = (message.text or "").strip().replace(",", "").replace("،", "")
    if not raw.isdigit() or int(raw) <= 0:
        return await message.answer("❌ لطفاً یک مبلغ معتبر به تومان وارد نمایید.")

    val = int(raw)
    await db_manager.set_setting("agent_min_settlement_amount", str(val))
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))

    await message.answer(f"✅ حداقل موجودی جهت ثبت درخواست تسویه روی <b>{val:,} تومان</b> تنظیم شد.", reply_markup=builder.as_markup(), parse_mode="HTML")


# === FEATURE 1: UNSETTLED SETTLEMENTS LIST ===
@admin_agent_router.callback_query(F.data.startswith("agent_unsettled_page_"))
async def list_unsettled_settlements(callback: types.CallbackQuery):
    """
    Displays unsettled (pending/waiting) settlement requests sorted by amount descending,
    with pagination, refresh button, and item navigation.
    """
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    page = int(callback.data.split("_")[3])
    page_size = 5

    total_count = await db_manager.count_unsettled_settlements()
    total_pages = max(1, math.ceil(total_count / page_size))
    if page >= total_pages:
        page = max(0, total_pages - 1)

    offset = page * page_size
    items = await db_manager.get_unsettled_settlements(limit=page_size, offset=offset)

    builder = InlineKeyboardBuilder()

    if not items:
        text = "✅ در حال حاضر هیچ درخواست تسویه نشده یا منتظر مانده‌ای وجود ندارد."
        builder.row(types.InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="agent_unsettled_page_0"))
        builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))
        try:
            return await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            if "not modified" not in str(e).lower():
                raise
            return

    text = (
        "⏳ <b>لیست تسویه‌های منتظر مانده (تسویه نشده‌ها)</b>\n\n"
        "<i>مرتب‌سازی: از بیشترین به کمترین مبلغ</i>\n"
        f"تعداد کل: <b>{total_count} عدد</b>\n\n"
        "جهت مشاهده فاکتور کامل و تسویه، روی هر ردیف کلیک کنید:"
    )

    for s in items:
        status_icon = "⏳" if s['status'] == 'waiting' else "🆕"
        builder.row(
            types.InlineKeyboardButton(
                text=f"{status_icon} #{s['id']} | {s['amount_irt']:,} ت | {s['amount_gram']} GRAM",
                callback_data=f"agent_stl_view_{s['id']}"
            )
        )

    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ قبل", callback_data=f"agent_unsettled_page_{page - 1}"))
    nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page + 1} از {total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="بعدی ▶️", callback_data=f"agent_unsettled_page_{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    # Refresh + Back
    builder.row(types.InlineKeyboardButton(text="🔄 بروزرسانی آنی", callback_data=f"agent_unsettled_page_{page}"))
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise


@admin_agent_router.callback_query(F.data.startswith("agent_stl_view_"))
async def view_settlement_item(callback: types.CallbackQuery):
    """
    Displays the full settlement invoice with exact format matching the agent notification,
    including Copy Wallet Address, Settle, and Wait buttons.
    """
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    settlement_id = int(callback.data.split("_")[3])
    s = await db_manager.get_agent_settlement(settlement_id)

    if not s:
        return await callback.answer("❌ این درخواست تسویه یافت نشد.", show_alert=True)

    agent_id = s['agent_id']
    username = s['username'] or 'ندارد'
    stats = await db_manager.get_agent_stats(agent_id)
    invites_count = stats['invited']

    status_persian = {
        'pending': 'در انتظار بررسی اولیه',
        'waiting': 'منتظر مانده',
        'settled': 'تسویه شده ✅',
        'rejected': 'رد شده ❌'
    }.get(s['status'], s['status'])

    text = (
        "📋 <b>فاکتور کامل درخواست تسویه</b>\n\n"
        f"🆔 <b>شماره تسویه:</b> #{s['id']}\n"
        f"👤 <b>نماینده:</b> <code>{agent_id}</code>\n"
        f"🔗 <b>نام کاربری:</b> @{username}\n"
        f"👥 <b>تعداد دعوت‌ها:</b> {invites_count} نفر\n\n"
        f"💵 <b>مبلغ تومانی تسویه:</b> {s['amount_irt']:,} تومان\n"
        f"💎 <b>معادل گرامی مبلغ تسویه:</b> <code>{s['amount_gram']}</code> گرام\n"
        f"💵 <b>نرخ هر گرام:</b> {s['gram_price']:,} تومان\n\n"
        f"👛 <b>آدرس کیف پول TON:</b>\n"
        f"<code>{s['wallet_address']}</code>\n\n"
        f"📅 <b>تاریخ ثبت:</b> {s['created_at']}\n"
        f"📌 <b>وضعیت فعلی:</b> {status_persian}"
    )

    builder = InlineKeyboardBuilder()

    # Row 1: Copy Wallet Address
    builder.row(
        types.InlineKeyboardButton(
            text="📋 کپی آدرس کیف پول",
            copy_text=types.CopyTextButton(text=s['wallet_address'])
        )
    )

    # Row 2: Settled and Wait (if not already settled)
    if s['status'] != 'settled':
        builder.row(
            types.InlineKeyboardButton(text="✅ تسویه شد", callback_data=f"agent_stl_done_{s['id']}"),
            types.InlineKeyboardButton(text="⏳ منتظر بماند", callback_data=f"agent_stl_wait_{s['id']}")
        )

    # Row 3: Back to unsettled list
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به لیست تسویه نشده‌ها", callback_data="agent_unsettled_page_0", style="danger")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.callback_query(F.data.startswith("agent_stl_wait_"))
async def mark_settlement_waiting(callback: types.CallbackQuery):
    """Marks a settlement request as waiting (منتظر بماند)."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    settlement_id = int(callback.data.split("_")[3])
    await db_manager.set_settlement_waiting(settlement_id)

    await callback.answer("⏳ وضعیت درخواست به «منتظر مانده» تغییر یافت.", show_alert=True)
    # Refresh view
    await view_settlement_item(callback)


@admin_agent_router.callback_query(F.data.startswith("agent_stl_done_"))
async def mark_settlement_done_start(callback: types.CallbackQuery, state: FSMContext):
    """Starts the settlement finalization flow by requesting the transaction hash link."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    settlement_id = int(callback.data.split("_")[3])
    s = await db_manager.get_agent_settlement(settlement_id)

    if not s:
        return await callback.answer("❌ تسویه یافت نشد.", show_alert=True)

    if s['status'] == 'settled':
        return await callback.answer("⚠️ این درخواست قبلاً تسویه شده است.", show_alert=True)

    await state.set_state(AdminAgentStates.waiting_for_settlement_tx_hash)
    await state.update_data(settlement_id=settlement_id)

    text = (
        f"🔗 <b>ثبت واریز تسویه #{s['id']}</b>\n\n"
        f"💰 مبلغ تومانی: {s['amount_irt']:,} تومان\n"
        f"💎 معادل ارزی: <code>{s['amount_gram']}</code> گرام\n"
        f"👛 آدرس کیف پول: <code>{s['wallet_address']}</code>\n\n"
        "لطفاً <b>لینک هش تراکنش (TxHash)</b> واریزی را ارسال نمایید:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_unsettled_page_0", style="danger"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.message(AdminAgentStates.waiting_for_settlement_tx_hash)
async def process_settlement_tx_hash(message: types.Message, state: FSMContext):
    """Processes tx hash from admin, marks settlement settled, and notifies agent."""
    if message.from_user.id not in ADMIN_IDS:
        return

    tx_hash = (message.text or "").strip()
    if not tx_hash:
        return await message.answer("❌ هش تراکنش نمی‌تواند خالی باشد. لطفاً لینک یا هش معتبر را ارسال نمایید.")

    data = await state.get_data()
    settlement_id = data.get("settlement_id")
    if not settlement_id:
        await state.clear()
        return

    updated_s = await db_manager.set_settlement_done(settlement_id, tx_hash)
    await state.clear()

    if not updated_s:
        return await message.answer("❌ خطا در ثبت تسویه حساب.")

    # Notify the agent
    agent_id = updated_s['agent_id']
    agent_notif_text = (
        "🎉 <b>تسویه حساب نمایندگی انجام شد!</b>\n\n"
        f"درخواست تسویه شماره <b>#{settlement_id}</b> با موفقیت توسط مدیریت واریز و تسویه گردید.\n\n"
        f"💰 <b>مبلغ تومانی:</b> {updated_s['amount_irt']:,} تومان\n"
        f"💎 <b>مقدار واریز شده:</b> <code>{updated_s['amount_gram']}</code> گرام (تون)\n"
        f"👛 <b>آدرس کیف پول شما:</b> <code>{updated_s['wallet_address']}</code>\n\n"
        f"🔗 <b>لینک پیگیری تراکنش (هش):</b>\n{tx_hash}\n\n"
        "با سپاس از همکاری و همراهی ارزشمند شما با مجموعه کندی کانکت 💎"
    )

    try:
        await message.bot.send_message(chat_id=agent_id, text=agent_notif_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send settlement notification to agent {agent_id}: {e}")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به لیست تسویه نشده‌ها", callback_data="agent_unsettled_page_0", style="danger")
    )

    confirm_admin = (
        f"✅ <b>تسویه حساب #{settlement_id} با موفقیت انجام شد!</b>\n\n"
        "این مورد از لیست تسویه نشده‌ها خارج شد و پیام تایید به همراه لینک هش برای نماینده ارسال گردید."
    )
    await message.answer(confirm_admin, reply_markup=builder.as_markup(), parse_mode="HTML")


# === FEATURE 2: ACTIVATION REQUESTS LIST ===
@admin_agent_router.callback_query(F.data.startswith("agent_act_page_"))
async def list_activation_requests(callback: types.CallbackQuery):
    """
    Displays pending activation requests sorted by commission balance descending,
    with pagination and navigation.
    """
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    page = int(callback.data.split("_")[3])
    page_size = 5

    total_count = await db_manager.count_pending_activation_requests()
    total_pages = max(1, math.ceil(total_count / page_size))
    if page >= total_pages:
        page = max(0, total_pages - 1)

    offset = page * page_size
    items = await db_manager.get_pending_activation_requests(limit=page_size, offset=offset)

    builder = InlineKeyboardBuilder()

    if not items:
        text = "✅ در حال حاضر هیچ درخواست فعالسازی برداشت در انتظار بررسی وجود ندارد."
        builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger"))
        return await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    text = (
        "📩 <b>درخواست‌های فعالسازی تسویه نمایندگی</b>\n\n"
        "<i>مرتب‌سازی: از بیشترین موجودی کمیسیون به کمترین</i>\n"
        f"تعداد کل در انتظار: <b>{total_count} عدد</b>\n\n"
        "جهت بررسی و تایید/رد، روی هر ردیف کلیک فرمایید:"
    )

    for req in items:
        un = f"@{req['username']}" if req['username'] else str(req['user_id'])
        builder.row(
            types.InlineKeyboardButton(
                text=f"👤 {un} | 💰 {req['commission_balance']:,} ت | 👥 {req['sub_users_count']} نفر",
                callback_data=f"agent_act_view_{req['id']}"
            )
        )

    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ قبل", callback_data=f"agent_act_page_{page - 1}"))
    nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page + 1} از {total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="بعدی ▶️", callback_data=f"agent_act_page_{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    # Refresh + Back row
    builder.row(
        types.InlineKeyboardButton(text="🔄 بروزرسانی لیست", callback_data=f"agent_act_page_{page}")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به تنظیمات نمایندگان", callback_data="admin_agent", style="danger")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.callback_query(F.data.startswith("agent_act_view_"))
async def view_activation_request(callback: types.CallbackQuery):
    """Displays full details of an activation request with approve and reject buttons."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    req_id = int(callback.data.split("_")[3])
    req = await db_manager.get_agent_activation_request(req_id)

    if not req:
        return await callback.answer("❌ این درخواست یافت نشد.", show_alert=True)

    un = f"@{req['username']}" if req['username'] else "ندارد"
    text = (
        "📩 <b>جزئیات درخواست فعالسازی برداشت تسویه نماینده</b>\n\n"
        f"🆔 <b>شماره درخواست:</b> #{req['id']}\n"
        f"👤 <b>شناسه عددی نماینده:</b> <code>{req['user_id']}</code>\n"
        f"🔗 <b>نام کاربری:</b> {un}\n\n"
        f"💰 <b>موجودی کمیسیون:</b> <b>{req['commission_balance']:,} تومان</b>\n"
        f"👥 <b>تعداد دعوت‌ها:</b> {req['sub_users_count']} نفر\n"
        f"📅 <b>تاریخ ثبت:</b> {req['created_at']}\n"
        f"📌 <b>وضعیت:</b> {req['status']}"
    )

    builder = InlineKeyboardBuilder()
    if req['status'] == 'pending':
        builder.row(
            types.InlineKeyboardButton(text="✅ تایید", callback_data=f"agent_act_approve_{req['id']}"),
            types.InlineKeyboardButton(text="❌ رد کردن", callback_data=f"agent_act_reject_{req['id']}")
        )
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به لیست درخواست‌ها", callback_data="agent_act_page_0", style="danger")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.callback_query(F.data.startswith("agent_act_approve_"))
async def approve_activation_request(callback: types.CallbackQuery):
    """
    Approves activation request, permanently activating settlement button for this agent,
    and sends notification to the agent.
    """
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    req_id = int(callback.data.split("_")[3])
    req = await db_manager.approve_agent_activation_request(req_id)

    if not req:
        return await callback.answer("❌ درخواست یافت نشد یا قبلاً بررسی شده است.", show_alert=True)

    user_id = req['user_id']

    # Send notification to the agent
    agent_msg = (
        "🎉 <b>تبریک! دکمه درخواست تسویه برای شما فعال شد.</b>\n\n"
        "نماینده گرامی، حساب نمایندگی شما توسط مدیریت تایید گردید و دکمه «درخواست تسویه» برای همیشه برای شما فعال شد.\n\n"
        "زین پس هر زمان موجودی کمیسیون شما به حداقل موجودی برداشت رسید، می‌توانید درخواست تسویه خود را در تب نمایندگی ثبت فرمایید."
    )
    try:
        await callback.bot.send_message(chat_id=user_id, text=agent_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify agent {user_id} of settlement approval: {e}")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به لیست درخواست‌ها", callback_data="agent_act_page_0", style="danger")
    )

    await callback.message.edit_text(
        f"✅ <b>درخواست فعالسازی برداشت تایید شد!</b>\n\nدکمه درخواست تسویه برای نماینده (<code>{user_id}</code>) برای همیشه فعال گردید و پیام اطلاع‌رسانی برای ایشان ارسال شد.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_agent_router.callback_query(F.data.startswith("agent_act_reject_"))
async def reject_activation_request_start(callback: types.CallbackQuery, state: FSMContext):
    """Prompts the admin for the rejection reason."""
    if not is_admin(callback.message):
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)

    await callback.answer()
    req_id = int(callback.data.split("_")[3])
    req = await db_manager.get_agent_activation_request(req_id)

    if not req:
        return await callback.answer("❌ درخواست یافت نشد.", show_alert=True)

    await state.set_state(AdminAgentStates.waiting_for_reject_reason)
    await state.update_data(req_id=req_id, user_id=req['user_id'])

    text = (
        f"✍️ <b>رد درخواست فعالسازی برداشت #{req_id}</b>\n"
        f"نماینده: <code>{req['user_id']}</code>\n\n"
        "لطفاً دلیل رد درخواست را وارد فرمایید تا به صورت نوتیفیکیشن برای نماینده ارسال گردد:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_act_page_0", style="danger"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_agent_router.message(AdminAgentStates.waiting_for_reject_reason)
async def process_activation_reject_reason(message: types.Message, state: FSMContext):
    """Saves rejection reason, updates request status, and sends reason to agent."""
    if message.from_user.id not in ADMIN_IDS:
        return

    reason = (message.text or "").strip()
    if not reason:
        return await message.answer("❌ دلیل رد نمی‌تواند خالی باشد. لطفاً متنی وارد نمایید.")

    data = await state.get_data()
    req_id = data.get("req_id")
    user_id = data.get("user_id")

    if not req_id or not user_id:
        await state.clear()
        return

    await db_manager.reject_agent_activation_request(req_id, reason)
    await state.clear()

    # Notify agent
    agent_msg = (
        "❌ <b>درخواست فعالسازی برداشت دکمه تسویه شما رد شد.</b>\n\n"
        f"📋 <b>علت رد درخواست توسط مدیریت:</b>\n{reason}\n\n"
        "<i>در صورت نیاز می‌توانید با پشتیبانی در ارتباط باشید.</i>"
    )
    try:
        await message.bot.send_message(chat_id=user_id, text=agent_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send rejection reason to agent {user_id}: {e}")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به لیست درخواست‌ها", callback_data="agent_act_page_0", style="danger")
    )

    await message.answer(
        f"✅ درخواست فعالسازی برداشت #{req_id} رد شد و دلیل برای نماینده ارسال گردید.",
        reply_markup=builder.as_markup()
    )


# === NEUTRAL BUTTONS HANDLER (PREVENTS "QUERY IS TOO OLD") ===
@admin_agent_router.callback_query(F.data.in_(["noop", "none"]))
async def handle_noop(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
