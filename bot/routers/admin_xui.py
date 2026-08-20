"""
admin_xui.py
------------
Module containing functionalities for admin_xui.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager

admin_xui_router = Router()


# ============================================================
# === ROUTER: مدیریت ثنا (XUI Panel Management) MAIN MENU ===
# ============================================================

@admin_xui_router.callback_query(F.data == "admin_xui")
async def admin_xui_menu(callback: types.CallbackQuery, state: FSMContext):
    """Handles admin xui menu."""
    if not is_admin(callback.message):
        return
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
    builder.button(text="📋 لیست پنل های تعریف شده", callback_data="xui_list_panels")
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "🖥 <b>مدیریت ثنا (پنل‌های 3x-UI)</b>\n\n"
        "از اینجا می‌توانید پنل‌های ثنا را تعریف و مدیریت کنید.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === FSM: ADD PANEL — 4 STEP FLOW ===
# ============================================================

@admin_xui_router.callback_query(F.data == "xui_add_panel")
async def add_panel_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add panel start."""
    if not is_admin(callback.message):
        return
    await state.set_state(AdminStates.waiting_for_panel_url)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui")
    await callback.message.edit_text(
        "🖥 <b>مرحله ۱/۴ — آدرس پنل</b>\n\n"
        "آدرس کامل پنل ثنا خود را وارد کنید.\n"
        "<i>مثال: https://panel.example.com:2053</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_url)
async def add_panel_url(message: types.Message, state: FSMContext):
    """Handles add panel url."""
    if not is_admin(message):
        return

    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        return await message.answer(
            "❌ آدرس نامعتبر. آدرس باید با <code>http://</code> یا <code>https://</code> شروع شود.",
            parse_mode="HTML"
        )

    await state.update_data(panel_url=url.rstrip("/"))
    await state.set_state(AdminStates.waiting_for_panel_token)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui")
    await message.answer(
        "🔑 <b>مرحله ۲/۴ — توکن ورود (Bearer Token)</b>\n\n"
        "توکن API پنل ثنا را وارد کنید.\n"
        "<i>این مقدار را از بخش Settings → Security → API Token پنل کپی کنید.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_token)
async def add_panel_token(message: types.Message, state: FSMContext):
    """Handles add panel token."""
    if not is_admin(message):
        return

    token = message.text.strip()
    if len(token) < 8:
        return await message.answer("❌ توکن خیلی کوتاه است. لطفاً توکن کامل را وارد کنید.")

    await state.update_data(panel_token=token)
    await state.set_state(AdminStates.waiting_for_panel_inbound_ids)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui")
    await message.answer(
        "📡 <b>مرحله ۳/۴ — آیدی اینباند(ها)</b>\n\n"
        "آیدی اینباند یا اینباندهایی که لایسنس‌های خریداری شده روی آن‌ها ساخته خواهند شد را وارد کنید.\n\n"
        "<i>(برای یک آیدی، فقط عدد را وارد کنید. "
        "برای چند آیدی، اعداد را با ویرگول از هم جدا کنید. "
        "مثال: <code>1,3,5</code>)</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_inbound_ids)
async def add_panel_inbound_ids(message: types.Message, state: FSMContext):
    """Handles add panel inbound ids."""
    if not is_admin(message):
        return

    raw = message.text.strip()
    # Validate: must be comma-separated integers
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or not all(p.isdigit() for p in parts):
        return await message.answer(
            "❌ فرمت نامعتبر. لطفاً آیدی‌ها را به صورت عدد یا اعداد جداشده با ویرگول وارد کنید.\n"
            "<i>مثال: <code>1</code> یا <code>1,3,5</code></i>",
            parse_mode="HTML"
        )

    inbound_ids_str = ",".join(parts)  # normalize
    await state.update_data(panel_inbound_ids=inbound_ids_str)
    await state.set_state(AdminStates.waiting_for_panel_ip_limit)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui")
    await message.answer(
        "👥 <b>مرحله ۴/۴ — محدودیت IP (IP Limit)</b>\n\n"
        "حداکثر تعداد کاربران همزمان برای اشتراک‌هایی که روی این پنل ساخته می‌شوند را وارد کنید.\n"
        "<i>مثال: <code>2</code></i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_ip_limit)
async def add_panel_ip_limit(message: types.Message, state: FSMContext):
    """Handles add panel ip limit."""
    if not is_admin(message):
        return

    if not message.text.strip().isdigit() or int(message.text.strip()) < 1:
        return await message.answer("❌ لطفاً یک عدد صحیح مثبت وارد کنید. مثال: <code>2</code>", parse_mode="HTML")

    ip_limit = int(message.text.strip())
    data = await state.get_data()
    await state.clear()

    # Persist to DB
    panel_id = await db_manager.add_xui_panel(
        url=data["panel_url"],
        bearer_token=data["panel_token"],
        inbound_ids=data["panel_inbound_ids"],
        ip_limit=ip_limit,
        label=None  # label derived from URL for display
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 مشاهده لیست پنل‌ها", callback_data="xui_list_panels")
    builder.button(text="🔙 بازگشت به ثنا", callback_data="admin_xui")
    builder.adjust(1)

    url_display = data["panel_url"]
    await message.answer(
        f"✅ <b>پنل با موفقیت اضافه شد</b>\n\n"
        f"🆔 شناسه پنل: <code>{panel_id}</code>\n"
        f"🌐 آدرس: <code>{url_display}</code>\n"
        f"📡 اینباندها: <code>{data['panel_inbound_ids']}</code>\n"
        f"👥 IP Limit: <code>{ip_limit}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: LIST ALL PANELS ===
# ============================================================

@admin_xui_router.callback_query(F.data == "xui_list_panels")
async def list_panels(callback: types.CallbackQuery):
    """Handles list panels."""
    if not is_admin(callback.message):
        return

    panels = await db_manager.get_xui_panels()

    if not panels:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
        builder.button(text="🔙 بازگشت", callback_data="admin_xui")
        builder.adjust(1)
        return await callback.message.edit_text(
            "📋 <b>لیست پنل‌های ثنا</b>\n\n"
            "هنوز هیچ پنلی تعریف نشده است.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    builder = InlineKeyboardBuilder()
    for p in panels:
        # Display: panel ID + truncated URL
        short_url = p["url"].replace("https://", "").replace("http://", "")[:35]
        builder.button(
            text=f"🖥 پنل #{p['id']} — {short_url}",
            callback_data=f"xui_panel_{p['id']}"
        )

    builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
    builder.button(text="🔙 بازگشت", callback_data="admin_xui")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📋 <b>لیست پنل‌های ثنا ({len(panels)} پنل)</b>\n\n"
        "برای مشاهده جزئیات، روی هر پنل کلیک کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: PANEL DETAIL VIEW ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_panel_"))
async def panel_detail(callback: types.CallbackQuery):
    """Handles panel detail."""
    if not is_admin(callback.message):
        return

    panel_id = int(callback.data.split("_")[2])
    panel = await db_manager.get_xui_panel(panel_id)

    if not panel:
        return await callback.answer("❌ پنل پیدا نشد.", show_alert=True)

    # Mask the bearer token in display
    token = panel["bearer_token"] or ""
    masked_token = token[:6] + "..." + token[-4:] if len(token) > 10 else "****"

    text = (
        f"🖥 <b>جزئیات پنل #{panel['id']}</b>\n\n"
        f"🌐 <b>آدرس پنل:</b>\n<code>{panel['url']}</code>\n\n"
        f"🔑 <b>توکن ورود:</b>\n<code>{masked_token}</code>\n\n"
        f"📡 <b>آیدی اینباندها:</b>\n<code>{panel['inbound_ids']}</code>\n\n"
        f"👥 <b>IP Limit:</b> <code>{panel['ip_limit']}</code>\n\n"
        f"📅 <b>تاریخ ثبت:</b> {panel['created_at']}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 حذف این پنل", callback_data=f"xui_del_panel_{panel_id}")
    builder.button(text="🔙 بازگشت به لیست", callback_data="xui_list_panels")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============================================================
# === ROUTER: DELETE PANEL ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_del_panel_"))
async def delete_panel(callback: types.CallbackQuery):
    """Handles delete panel."""
    if not is_admin(callback.message):
        return

    panel_id = int(callback.data.split("_")[3])
    await db_manager.delete_xui_panel(panel_id)
    await callback.answer("✅ پنل با موفقیت حذف شد.", show_alert=True)

    # Redirect to list
    callback.data = "xui_list_panels"
    await list_panels(callback)
