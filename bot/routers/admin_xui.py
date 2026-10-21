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
from utils.ui_helpers import safe_edit_message

admin_xui_router = Router()


# ============================================================
# === ROUTER: مدیریت ثنا (XUI Panel Management) MAIN MENU ===
# ============================================================

@admin_xui_router.callback_query(F.data == "admin_xui")
async def admin_xui_menu(callback: types.CallbackQuery, state: FSMContext):
    """Handles admin xui menu."""
    if not is_admin(callback):
        return
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
    builder.button(text="📋 لیست پنل های تعریف شده", callback_data="xui_list_panels")
    builder.button(text="🔙 بازگشت", callback_data="admin_back", style="danger")
    builder.adjust(1)

    await safe_edit_message(callback, 
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
    if not is_admin(callback):
        return
    await state.set_state(AdminStates.waiting_for_panel_name)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await safe_edit_message(callback, 
        "🖥 <b>مرحله ۱/۶ — نام پنل</b>\n\n"
        "یک نام دلخواه برای این پنل وارد کنید.\n"
        "<i>مثال: پنل آلمان 1</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_name)
async def add_panel_name(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    await state.update_data(panel_name=message.text.strip())
    await state.set_state(AdminStates.waiting_for_panel_url)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await message.answer(
        "🌐 <b>مرحله ۲/۶ — آدرس پنل</b>\n\n"
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

    clean_url = url.rstrip("/")
    for suffix in ("/panel/inbounds", "/panel/setting", "/panel/settings", "/panel"):
        if clean_url.endswith(suffix):
            clean_url = clean_url[:-len(suffix)].rstrip("/")

    await state.update_data(panel_url=clean_url)
    await state.set_state(AdminStates.waiting_for_panel_sub_link)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await message.answer(
        "🔗 <b>مرحله ۳/۶ — آدرس ساب لینک</b>\n\n"
        "آدرس ساب لینک پنل ثنا خود را برای دریافت حجم مصرفی لایسنس وارد کنید.\n"
        "<i>مثال: https://sub.example.com/sub/</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_panel_sub_link)
async def add_panel_sub_link(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    sub_link = message.text.strip()
    if not sub_link.startswith(("http://", "https://")):
        return await message.answer("❌ آدرس نامعتبر. باید با http یا https شروع شود.")
        
    await state.update_data(panel_sub_link=sub_link)
    await state.set_state(AdminStates.waiting_for_panel_token)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await message.answer(
        "🔑 <b>مرحله ۴/۶ — توکن ورود (Bearer Token)</b>\n\n"
        "توکن API پنل ثنا یا فرمت <code>username:password</code> را وارد کنید.\n"
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
    if len(token) < 4:
        return await message.answer("❌ توکن خیلی کوتاه است. لطفاً توکن یا نام کاربری و رمز معتبر وارد کنید.")

    await state.update_data(panel_token=token)
    await state.set_state(AdminStates.waiting_for_panel_inbound_ids)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await message.answer(
        "📡 <b>مرحله ۵/۶ — آیدی اینباند(ها)</b>\n\n"
        "آیدی اینباند یا اینباندهایی که لایسنس‌های خریداری شده روی آن‌ها ساخته خواهند شد را وارد کنید.\n\n"
        "⚠️ <b>نکته مهم:</b> آیدی اینباند یک عدد ترتیبی کوچک (مثل <code>1</code> یا <code>2</code>) است که در ستون <b>ID</b> جدول اینباندهای پنل نمایش داده می‌شود؛ <b>پورت</b> (مثل 2083 یا 443) را به عنوان آیدی وارد نکنید!\n\n"
        "<i>(برای یک آیدی، فقط عدد را وارد کنید. برای چند آیدی، اعداد را با ویرگول از هم جدا کنید. مثال: <code>1,2</code>)</i>",
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
    builder.button(text="❌ انصراف", callback_data="admin_xui", style="danger")
    await message.answer(
        "👥 <b>مرحله ۶/۶ — محدودیت IP (IP Limit)</b>\n\n"
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
        name=data.get("panel_name", "بدون نام"),
        url=data["panel_url"],
        sub_link=data.get("panel_sub_link", ""),
        bearer_token=data["panel_token"],
        inbound_ids=data["panel_inbound_ids"],
        ip_limit=ip_limit,
        label=None  # label derived from URL for display
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 مشاهده لیست پنل‌ها", callback_data="xui_list_panels")
    builder.button(text="🔙 بازگشت به ثنا", callback_data="admin_xui", style="danger")
    builder.adjust(1)

    url_display = data["panel_url"]
    await message.answer(
        f"✅ <b>پنل با موفقیت اضافه شد</b>\n\n"
        f"🆔 شناسه پنل: <code>{panel_id}</code>\n"
        f"📛 نام: <code>{data.get('panel_name', 'بدون نام')}</code>\n"
        f"🌐 آدرس: <code>{url_display}</code>\n"
        f"🔗 ساب لینک: <code>{data.get('panel_sub_link', '')}</code>\n"
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
    if not is_admin(callback):
        return

    panels = await db_manager.get_xui_panels()

    if not panels:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
        builder.button(text="🔙 بازگشت", callback_data="admin_xui", style="danger")
        builder.adjust(1)
        return await safe_edit_message(
            callback,
            "📋 <b>لیست پنل‌های ثنا</b>\n\n"
            "هنوز هیچ پنلی تعریف نشده است.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    builder = InlineKeyboardBuilder()
    for p in panels:
        p_dict = dict(p) if not isinstance(p, dict) else p
        short_url = p_dict["url"].replace("https://", "").replace("http://", "")[:35]
        display_name = p_dict.get("name") or short_url
        builder.button(
            text=f"🖥 پنل #{p_dict['id']} — {display_name}",
            callback_data=f"xui_panel_{p_dict['id']}"
        )

    builder.button(text="➕ اضافه کردن پنل", callback_data="xui_add_panel")
    builder.button(text="🔙 بازگشت", callback_data="admin_xui", style="danger")
    builder.adjust(1)

    await safe_edit_message(callback, 
        f"📋 <b>لیست پنل‌های ثنا ({len(panels)} پنل)</b>\n\n"
        "برای مشاهده جزئیات، روی هر پنل کلیک کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: PANEL DETAIL VIEW ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_panel_"))
async def panel_detail(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles panel detail."""
    if not is_admin(callback):
        return
    if state:
        await state.clear()

    panel_id = int(callback.data.split("_")[2])
    panel = await db_manager.get_xui_panel(panel_id)

    if not panel:
        return await callback.answer("❌ پنل پیدا نشد.", show_alert=True)

    if not isinstance(panel, dict):
        panel = dict(panel)

    # Mask the bearer token in display
    token = panel.get("bearer_token") or ""
    masked_token = token[:6] + "..." + token[-4:] if len(token) > 10 else "****"

    panel_name = panel.get("name") or "ثبت نشده"
    sub_link = panel.get("sub_link") or "ثبت نشده"

    text = (
        f"🖥 <b>جزئیات پنل #{panel['id']}</b>\n\n"
        f"📛 <b>نام پنل:</b> <code>{panel_name}</code>\n\n"
        f"🌐 <b>آدرس پنل:</b>\n<code>{panel['url']}</code>\n\n"
        f"🔗 <b>ساب لینک:</b>\n<code>{sub_link}</code>\n\n"
        f"🔑 <b>توکن ورود:</b>\n<code>{masked_token}</code>\n\n"
        f"📡 <b>آیدی اینباندها:</b>\n<code>{panel.get('inbound_ids', '')}</code>\n\n"
        f"👥 <b>IP Limit:</b> <code>{panel.get('ip_limit', 1)}</code>\n\n"
        f"📅 <b>تاریخ ثبت:</b> {panel.get('created_at', '')}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ ویرایش مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="🔌 تست اتصال", callback_data=f"xui_test_conn_{panel_id}")
    builder.button(text="🗑 حذف این پنل", callback_data=f"xui_del_panel_{panel_id}")
    builder.button(text="🔙 بازگشت به لیست", callback_data="xui_list_panels", style="danger")
    builder.adjust(2, 1, 1)

    await safe_edit_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============================================================
# === ROUTER: EDIT PANEL MENU ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_edit_menu_"))
async def edit_panel_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Shows the edit panel fields menu."""
    if not is_admin(callback):
        return
    if state:
        await state.clear()

    panel_id = int(callback.data.split("_")[3])
    panel = await db_manager.get_xui_panel(panel_id)

    if not panel:
        return await callback.answer("❌ پنل پیدا نشد.", show_alert=True)

    if not isinstance(panel, dict):
        panel = dict(panel)

    panel_name = panel.get("name") or f"پنل #{panel_id}"

    text = (
        f"⚙️ <b>ویرایش مشخصات پنل #{panel_id} ({panel_name})</b>\n\n"
        f"کدام یک از مشخصات زیر را می‌خواهید ویرایش کنید؟"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📛 نام پنل", callback_data=f"xui_edfield_{panel_id}_name")
    builder.button(text="🌐 آدرس پنل", callback_data=f"xui_edfield_{panel_id}_url")
    builder.button(text="🔗 ساب لینک", callback_data=f"xui_edfield_{panel_id}_sub")
    builder.button(text="🔑 توکن ورود", callback_data=f"xui_edfield_{panel_id}_token")
    builder.button(text="📡 آیدی اینباندها", callback_data=f"xui_edfield_{panel_id}_inbounds")
    builder.button(text="👥 محدودیت IP", callback_data=f"xui_edfield_{panel_id}_iplimit")
    builder.button(text="🔙 بازگشت به جزئیات پنل", callback_data=f"xui_panel_{panel_id}", style="danger")
    builder.adjust(2, 2, 2, 1)

    await safe_edit_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============================================================
# === ROUTER: EDIT PANEL FIELDS START ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_edfield_"))
async def edit_panel_field_start(callback: types.CallbackQuery, state: FSMContext):
    """Initiates field editing by asking for user input."""
    if not is_admin(callback):
        return

    parts = callback.data.split("_")
    panel_id = int(parts[2])
    field = parts[3]

    panel = await db_manager.get_xui_panel(panel_id)
    if not panel:
        return await callback.answer("❌ پنل پیدا نشد.", show_alert=True)

    if not isinstance(panel, dict):
        panel = dict(panel)

    await state.update_data(edit_panel_id=panel_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data=f"xui_edit_menu_{panel_id}", style="danger")

    if field == "name":
        await state.set_state(AdminStates.waiting_for_edit_panel_name)
        curr = panel.get("name") or "ثبت نشده"
        await safe_edit_message(
            callback,
            f"📛 <b>ویرایش نام پنل #{panel_id}</b>\n\n"
            f"نام فعلی: <code>{curr}</code>\n\n"
            f"لطفاً نام جدید دلخواه برای این پنل را وارد کنید:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif field == "url":
        await state.set_state(AdminStates.waiting_for_edit_panel_url)
        curr = panel.get("url") or ""
        await safe_edit_message(
            callback,
            f"🌐 <b>ویرایش آدرس پنل #{panel_id}</b>\n\n"
            f"آدرس فعلی:\n<code>{curr}</code>\n\n"
            f"لطفاً آدرس جدید پنل را وارد کنید (شروع با <code>http://</code> یا <code>https://</code>):\n"
            f"<i>مثال: https://panel.example.com:2053</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif field == "sub":
        await state.set_state(AdminStates.waiting_for_edit_panel_sub_link)
        curr = panel.get("sub_link") or "ثبت نشده"
        await safe_edit_message(
            callback,
            f"🔗 <b>ویرایش ساب لینک پنل #{panel_id}</b>\n\n"
            f"ساب لینک فعلی:\n<code>{curr}</code>\n\n"
            f"لطفاً آدرس ساب لینک جدید را وارد کنید:\n"
            f"<i>مثال: https://sub.example.com/sub/</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif field == "token":
        await state.set_state(AdminStates.waiting_for_edit_panel_token)
        tok = panel.get("bearer_token") or ""
        masked = tok[:6] + "..." + tok[-4:] if len(tok) > 10 else "****"
        await safe_edit_message(
            callback,
            f"🔑 <b>ویرایش توکن ورود پنل #{panel_id}</b>\n\n"
            f"توکن فعلی: <code>{masked}</code>\n\n"
            f"توکن API جدید پنل را وارد کنید:\n"
            f"<i>این مقدار را از بخش Settings → Security → API Token پنل کپی کنید.</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif field == "inbounds":
        await state.set_state(AdminStates.waiting_for_edit_panel_inbound_ids)
        curr = panel.get("inbound_ids") or "ثبت نشده"
        await safe_edit_message(
            callback,
            f"📡 <b>ویرایش آیدی اینباندهای پنل #{panel_id}</b>\n\n"
            f"اینباندهای فعلی: <code>{curr}</code>\n\n"
            f"آیدی اینباند یا اینباندهای جدید را وارد کنید:\n"
            f"<i>(برای یک آیدی فقط عدد، برای چند آیدی با ویرگول جدا کنید. مثال: <code>1,3,5</code>)</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    elif field == "iplimit":
        await state.set_state(AdminStates.waiting_for_edit_panel_ip_limit)
        curr = panel.get("ip_limit", 1)
        await safe_edit_message(
            callback,
            f"👥 <b>ویرایش محدودیت IP پنل #{panel_id}</b>\n\n"
            f"محدودیت IP فعلی: <code>{curr}</code>\n\n"
            f"حداکثر تعداد کاربران همزمان جدید را وارد کنید:\n"
            f"<i>مثال: <code>2</code></i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )


# ============================================================
# === ROUTER: EDIT PANEL MESSAGE HANDLERS ===
# ============================================================

@admin_xui_router.message(AdminStates.waiting_for_edit_panel_name)
async def save_edited_panel_name(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    val = message.text.strip()
    if not val:
        return await message.answer("❌ نام پنل نمی‌تواند خالی باشد.")

    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    await db_manager.update_xui_panel(panel_id, name=val)

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>نام پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"📛 نام جدید: <code>{val}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_edit_panel_url)
async def save_edited_panel_url(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        return await message.answer(
            "❌ آدرس نامعتبر. آدرس باید با <code>http://</code> یا <code>https://</code> شروع شود.",
            parse_mode="HTML"
        )

    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    clean_url = url.rstrip("/")
    for suffix in ("/panel/inbounds", "/panel/setting", "/panel/settings", "/panel"):
        if clean_url.endswith(suffix):
            clean_url = clean_url[:-len(suffix)].rstrip("/")
    await db_manager.update_xui_panel(panel_id, url=clean_url)

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>آدرس پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"🌐 آدرس جدید:\n<code>{clean_url}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_edit_panel_sub_link)
async def save_edited_panel_sub_link(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    sub_link = message.text.strip()
    if not sub_link.startswith(("http://", "https://")):
        return await message.answer(
            "❌ آدرس نامعتبر. آدرس باید با <code>http://</code> یا <code>https://</code> شروع شود.",
            parse_mode="HTML"
        )

    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    await db_manager.update_xui_panel(panel_id, sub_link=sub_link)

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>ساب لینک پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"🔗 ساب لینک جدید:\n<code>{sub_link}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_edit_panel_token)
async def save_edited_panel_token(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    token = message.text.strip()
    if len(token) < 4:
        return await message.answer("❌ توکن خیلی کوتاه است. لطفاً توکن معتبر را وارد کنید.")

    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    await db_manager.update_xui_panel(panel_id, bearer_token=token)

    masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "****"

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>توکن ورود پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"🔑 توکن جدید: <code>{masked}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_edit_panel_inbound_ids)
async def save_edited_panel_inbounds(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    raw = message.text.strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or not all(p.isdigit() for p in parts):
        return await message.answer(
            "❌ فرمت نامعتبر. لطفاً آیدی‌ها را به صورت عدد یا اعداد جداشده با ویرگول وارد کنید.\n"
            "<i>مثال: <code>1</code> یا <code>1,3,5</code></i>",
            parse_mode="HTML"
        )

    inbound_ids_str = ",".join(parts)
    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    await db_manager.update_xui_panel(panel_id, inbound_ids=inbound_ids_str)

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>اینباندهای پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"📡 اینباندهای جدید: <code>{inbound_ids_str}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_xui_router.message(AdminStates.waiting_for_edit_panel_ip_limit)
async def save_edited_panel_ip_limit(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) < 1:
        return await message.answer("❌ لطفاً یک عدد صحیح مثبت وارد کنید. مثال: <code>2</code>", parse_mode="HTML")

    ip_limit = int(raw)
    data = await state.get_data()
    panel_id = data.get("edit_panel_id")
    await state.clear()

    await db_manager.update_xui_panel(panel_id, ip_limit=ip_limit)

    builder = InlineKeyboardBuilder()
    builder.button(text="🖥 مشاهده جزئیات پنل", callback_data=f"xui_panel_{panel_id}")
    builder.button(text="✏️ ویرایش سایر مشخصات", callback_data=f"xui_edit_menu_{panel_id}")
    builder.button(text="📋 لیست پنل‌ها", callback_data="xui_list_panels")
    builder.adjust(1)

    await message.answer(
        f"✅ <b>محدودیت IP پنل #{panel_id} با موفقیت ویرایش شد.</b>\n\n"
        f"👥 محدودیت IP جدید: <code>{ip_limit}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: TEST CONNECTION ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_test_conn_"))
async def test_panel_connection(callback: types.CallbackQuery):
    """Tests connection to an XUI panel."""
    if not is_admin(callback):
        return

    panel_id = int(callback.data.split("_")[3])
    panel = await db_manager.get_xui_panel(panel_id)

    if not panel:
        return await callback.answer("❌ پنل پیدا نشد.", show_alert=True)

    if not isinstance(panel, dict):
        panel = dict(panel)

    await callback.answer("⏳ در حال بررسی اتصال به پنل...", show_alert=False)

    from bot.services.xui_client import XUIClient
    try:
        async with XUIClient(base_url=panel["url"], bearer_token=panel["bearer_token"]) as client:
            ok, msg = await client.test_connection()
        prefix = "✅ اتصال موفق:" if ok else "❌ خطا در برقراری ارتباط:"
        await callback.answer(f"{prefix}\n{msg}"[:200], show_alert=True)
    except Exception as exc:
        await callback.answer(f"❌ خطای اتصال:\n{exc}"[:200], show_alert=True)


# ============================================================
# === ROUTER: DELETE PANEL ===
# ============================================================

@admin_xui_router.callback_query(F.data.startswith("xui_del_panel_"))
async def delete_panel(callback: types.CallbackQuery):
    """Handles delete panel."""
    if not is_admin(callback):
        return

    panel_id = int(callback.data.split("_")[3])
    await db_manager.delete_xui_panel(panel_id)
    await callback.answer("✅ پنل با موفقیت حذف شد.", show_alert=True)

    # Redirect to list
    await list_panels(callback)
