"""
admin_settings.py
-----------------
Module containing functionalities for admin_settings.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_settings_router = Router()

# === ROUTER: SETTINGS MENU ===
@admin_settings_router.callback_query(F.data == "admin_settings")
async def settings_menu(callback: types.CallbackQuery):
    """Handles settings menu."""
    if not is_admin(callback.message): return
    
    op_mode = await db_manager.get_operating_mode()
    fb_enabled = await db_manager.get_setting('feedback_enabled', '1')
    acq_enabled = await db_manager.get_setting('acquisition_survey_enabled', '0')
    
    status_on = "✅"
    status_off = "❌"
    
    op_mode_text = {
        "NORMAL": "🟢 عادی",
        "SALES_PAUSED": "🟡 توقف فروش",
        "MAINTENANCE": "🔴 تعمیرات"
    }.get(op_mode, "🟢 عادی")
    
    builder = InlineKeyboardBuilder()
    
    # Operating Mode
    builder.button(text="وضعیت ربات:", callback_data="none")
    builder.button(text=op_mode_text, callback_data="toggle_op_mode")
    
    # Feedback
    builder.button(text="نظرسنجی خرید:", callback_data="none")
    builder.button(text=status_on if fb_enabled == '1' else status_off, callback_data="toggle_feedback")
    
    # Acquisition Survey
    builder.button(text="نظرسنجی آشنایی:", callback_data="none")
    builder.button(text=status_on if acq_enabled == '1' else status_off, callback_data="toggle_acquisition")
    
    # Channels & Admins
    builder.button(text="📯 مدیریت کانال‌ها", callback_data="admin_manage_channels")
    builder.button(text="👨‍💻 مدیریت ادمین‌ها", callback_data="admin_manage_admins")
    
    # New Utilities
    qr_bg_enabled = await db_manager.get_setting('qr_bg_enabled', '0')
    builder.button(text="🖼 پس زمینه کیوآرکد:", callback_data="none")
    builder.button(text=status_on if qr_bg_enabled == '1' else status_off, callback_data="toggle_qr_bg")
    builder.button(text="آپلود عکس پس زمینه", callback_data="admin_manage_qr")
    
    # Free Trial
    builder.button(text="🎁 تنظیمات تست رایگان", callback_data="admin_free_trial")
    
    # Referral
    builder.button(text="🤝 تنظیمات زیرمجموعه‌گیری", callback_data="admin_referral")
    
    # Back
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 2, 2, 1, 1, 1, 1)
    
    await callback.message.edit_text("⚙️ **تنظیمات عمومی ربات**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data.in_({"toggle_op_mode", "toggle_feedback", "toggle_acquisition", "toggle_qr_bg"}))
async def handle_toggles(callback: types.CallbackQuery):
    """Handles handle toggles."""
    if not is_admin(callback.message): return
    
    if callback.data == "toggle_op_mode":
        current = await db_manager.get_operating_mode()
        next_mode = {"NORMAL": "SALES_PAUSED", "SALES_PAUSED": "MAINTENANCE", "MAINTENANCE": "NORMAL"}[current]
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('operating_mode', ?)", (next_mode,))
            await db.commit()
            
    elif callback.data == "toggle_feedback":
        current = await db_manager.get_setting('feedback_enabled', '1')
        next_val = '0' if current == '1' else '1'
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('feedback_enabled', ?)", (next_val,))
            await db.commit()
            
    elif callback.data == "toggle_acquisition":
        current = await db_manager.get_setting('acquisition_survey_enabled', '0')
        next_val = '0' if current == '1' else '1'
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('acquisition_survey_enabled', ?)", (next_val,))
            await db.commit()
    elif callback.data == "toggle_qr_bg":
        current = await db_manager.get_setting('qr_bg_enabled', '0')
        next_val = '0' if current == '1' else '1'
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('qr_bg_enabled', ?)", (next_val,))
            await db.commit()
            
    await settings_menu(callback)

# === ROUTER: CHANNELS MANAGEMENT ===
@admin_settings_router.callback_query(F.data == "admin_manage_channels")
async def manage_channels(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles manage channels menu."""
    if not is_admin(callback.message): return
    if state:
        await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن کانال", callback_data="add_channel")
    builder.button(text="❌ حذف کانال", callback_data="del_channel")
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(2, 1)
    
    await callback.message.edit_text("📯 <b>مدیریت کانال‌های جوین اجباری</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_settings_router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add channel start."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_channel_remark)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو و بازگشت", callback_data="admin_manage_channels")
    
    await callback.message.edit_text(
        "📌 <b>یک نام برای دکمه عضویت کانال انتخاب نمایید:</b>\n"
        "(مثلاً: <code>به جمع ما بپیوند</code>)",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_settings_router.message(AdminStates.waiting_for_channel_remark)
async def add_channel_remark(message: types.Message, state: FSMContext):
    """Handles add channel remark."""
    if not is_admin(message): return
    remark = message.text.strip() if message.text else ""
    if not remark:
        return await message.answer("❌ نام نمی‌تواند خالی باشد. لطفاً یک نام معتبر ارسال کنید:")

    await state.update_data(channel_remark=remark)
    await state.set_state(AdminStates.waiting_for_channel_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو و بازگشت", callback_data="admin_manage_channels")

    await message.answer(
        "📌 <b>یوزرنیم یا آیدی عددی کانال را وارد کنید:</b>\n\n"
        "• برای کانال‌های عمومی: یوزرنیم با @ مانند <code>@CandyConnect</code>\n"
        "• برای کانال‌های خصوصی: آیدی عددی کانال که با <code>-100</code> شروع می‌شود\n\n"
        "⚠️ <i>توجه: ربات باید در کانال عضو یا ادمین باشد تا بتواند عضویت کاربر را بررسی کند.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_settings_router.message(AdminStates.waiting_for_channel_id)
async def add_channel_id(message: types.Message, state: FSMContext):
    """Handles add channel identifier."""
    if not is_admin(message): return
    raw_input = (message.text or "").strip()
    
    from bot.services.channel_service import extract_chat_id
    parsed_id = extract_chat_id(raw_input)
    if not parsed_id:
        parsed_id = raw_input

    await state.update_data(channel_id=str(parsed_id))
    await state.set_state(AdminStates.waiting_for_channel_url)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو و بازگشت", callback_data="admin_manage_channels")

    suggested_link = f"https://t.me/{str(parsed_id).replace('@', '')}" if str(parsed_id).startswith("@") else ""
    help_text = f"\n(پیشنهادی: <code>{suggested_link}</code>)" if suggested_link else ""

    await message.answer(
        f"📌 <b>لینک جوین کانال را ارسال کنید:</b>{help_text}\n\n"
        "این لینک بر روی دکمه قرار می‌گیرد و کاربر برای عضویت به آن هدایت می‌شود (باید با https:// شروع شود):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_settings_router.message(AdminStates.waiting_for_channel_url)
async def add_channel_url(message: types.Message, state: FSMContext):
    """Handles add channel url."""
    if not is_admin(message): return
    url = (message.text or "").strip()
    if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("t.me/"):
        return await message.answer("❌ لینک نامعتبر است. باید با https:// شروع شود:")

    if url.startswith("t.me/"):
        url = "https://" + url

    data = await state.get_data()
    remark = data.get('channel_remark', 'کانال')
    channel_id = data.get('channel_id', url)

    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO channels (remark, link, linkjoin) VALUES (?, ?, ?)",
            (remark, channel_id, url)
        )
        await db.commit()

    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به مدیریت کانال‌ها", callback_data="admin_manage_channels")
    await message.answer(
        f"✅ <b>کانال جوین اجباری با موفقیت ثبت گردید.</b>\n\n"
        f"🏷 نام دکمه: <b>{remark}</b>\n"
        f"🆔 شناسه چنل: <code>{channel_id}</code>\n"
        f"🔗 لینک عضویت: {url}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_settings_router.callback_query(F.data == "del_channel")
async def del_channel_list(callback: types.CallbackQuery, state: FSMContext = None):
    """Shows the list of force join channels to delete."""
    if not is_admin(callback.message): return
    if state:
        await state.clear()

    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels ORDER BY id DESC") as cur:
            channels = await cur.fetchall()

    builder = InlineKeyboardBuilder()

    if not channels:
        builder.button(text="🔙 بازگشت", callback_data="admin_manage_channels")
        return await callback.message.edit_text(
            "❌ <b>هیچ کانال جوین اجباری ثبت نشده است.</b>", 
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    for ch in channels:
        name = ch['remark'] or "کانال"
        ident = ch['link'] or ch['linkjoin'] or ""
        builder.button(text=f"🗑 {name} ({ident})", callback_data=f"del_chan_{ch['id']}")

    builder.button(text="🔙 بازگشت", callback_data="admin_manage_channels")
    builder.adjust(1)

    await callback.message.edit_text(
        "🗑 <b>حذف کانال‌های جوین اجباری</b>\n\n"
        "جهت حذف هر کانال، روی دکمه آن کلیک کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_settings_router.callback_query(F.data.startswith("del_chan_"))
async def del_channel_exec(callback: types.CallbackQuery):
    """Deletes a selected force join channel."""
    if not is_admin(callback.message): return
    
    chan_id = int(callback.data.split("_")[2])
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (chan_id,))
        await db.commit()

    await callback.answer("✅ کانال با موفقیت حذف شد.", show_alert=True)
    await del_channel_list(callback)


# === ROUTER: ADMIN MANAGEMENT ===
@admin_settings_router.callback_query(F.data == "admin_manage_admins")
async def manage_admins(callback: types.CallbackQuery, state: FSMContext):
    """Handles manage admins."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_admin_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    await callback.message.edit_text("👨‍💻 **مدیریت ادمین‌ها**\n\nبرای افزودن ادمین جدید، لطفا آیدی عددی (User ID) تلگرام او را بفرستید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.message(AdminStates.waiting_for_admin_id)
async def add_admin_save(message: types.Message, state: FSMContext):
    """Handles add admin save."""
    if not is_admin(message): return
    try:
        new_admin_id = int(message.text)
    except:
        return await message.answer("❌ لطفا فقط عدد وارد کنید.")
        
    # Ideally this would add to `admins` table. The DB schema provided has an `admins` table with username, password, role.
    # The legacy code saved 'id_admin' in an 'admin' table, but our new DB uses 'admins'.
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO admins (id, role) VALUES (?, 'admin')", (new_admin_id,))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به تنظیمات", callback_data="admin_settings")
    await message.answer(f"✅ کاربر {new_admin_id} با موفقیت به عنوان ادمین اضافه شد.", reply_markup=builder.as_markup())



# === ROUTER: QR BACKGROUND ===
@admin_settings_router.callback_query(F.data == "admin_manage_qr")
async def manage_qr_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles manage qr prompt."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_qr_background)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="admin_settings")
    await callback.message.edit_text("🖼 **پس زمینه کیوآرکد**\nتصویر خود را برای پس زمینه ارسال کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.message(AdminStates.waiting_for_qr_background)
async def manage_qr_process(message: types.Message, state: FSMContext):
    """Handles manage qr process."""
    if not is_admin(message): return
    if not message.photo:
        return await message.answer("❌ لطفاً یک تصویر ارسال کنید.")
        
    photo_id = message.photo[-1].file_id
    file = await message.bot.get_file(photo_id)
    file_path = file.file_path
    
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    utils_dir = os.path.join(project_root, 'utils')
    if not os.path.exists(utils_dir):
        os.makedirs(utils_dir)
        
    bg_jpg = os.path.join(utils_dir, 'qr-background.jpg')
    
    await message.bot.download_file(file_path, bg_jpg)
    
    await state.set_state(None)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 تنظیمات", callback_data="admin_settings")
    await message.answer("🖼 پس زمینه با موفقیت تنظیم گردید.", reply_markup=builder.as_markup())

# === ROUTER: REFERRAL SYSTEM ===
@admin_settings_router.callback_query(F.data == "admin_referral")
async def referral_settings_menu(callback: types.CallbackQuery):
    """Handles referral settings menu."""
    if not is_admin(callback.message): return
    
    status = await db_manager.get_setting('referral_status', '0')
    r_type = await db_manager.get_setting('referral_reward_type', 'percent')
    val = await db_manager.get_setting('referral_reward_amount', '0')
    
    status_text = "✅ روشن" if status == '1' else "❌ خاموش"
    type_text = "مبلغ ثابت" if r_type == 'fixed' else "درصد از خرید"
    val_text = f"{val} تومان" if r_type == 'fixed' else f"{val} درصد"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="وضعیت سیستم:", callback_data="none")
    builder.button(text=status_text, callback_data="toggle_ref_status")
    
    builder.button(text="نوع پاداش:", callback_data="none")
    builder.button(text=type_text, callback_data="toggle_ref_type")
    
    builder.button(text="مقدار پاداش:", callback_data="none")
    builder.button(text=val_text, callback_data="set_ref_value")
    
    builder.button(text="🔙 بازگشت به تنظیمات", callback_data="admin_settings")
    
    builder.adjust(2, 2, 2, 1)
    
    await callback.message.edit_text(
        "🤝 **تنظیمات زیرمجموعه گیری**\n\n"
        "در این بخش می‌توانید سیستم معرفی دوستان را مدیریت کنید.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@admin_settings_router.callback_query(F.data.in_({"toggle_ref_status", "toggle_ref_type"}))
async def handle_referral_toggles(callback: types.CallbackQuery):
    """Handles referral toggles."""
    if not is_admin(callback.message): return
    
    if callback.data == "toggle_ref_status":
        current = await db_manager.get_setting('referral_status', '0')
        next_val = '0' if current == '1' else '1'
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('referral_status', ?)", (next_val,))
            await db.commit()
    elif callback.data == "toggle_ref_type":
        current = await db_manager.get_setting('referral_reward_type', 'percent')
        next_val = 'percent' if current == 'fixed' else 'fixed'
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('referral_reward_type', ?)", (next_val,))
            await db.commit()
            
    await referral_settings_menu(callback)

@admin_settings_router.callback_query(F.data == "set_ref_value")
async def set_referral_value_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set referral value prompt."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_referral_value)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="admin_referral")
    await callback.message.edit_text(
        "💰 **تنظیم مقدار پاداش**\n"
        "لطفاً مقدار جدید را به صورت عددی ارسال کنید (بدون کاما):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@admin_settings_router.message(AdminStates.waiting_for_referral_value)
async def set_referral_value_process(message: types.Message, state: FSMContext):
    """Handles set referral value process."""
    if not is_admin(message): return
    try:
        val = float(message.text.strip())
        if val < 0: raise ValueError
    except:
        return await message.answer("❌ لطفاً یک عدد معتبر و مثبت وارد کنید.")
        
    val_str = str(int(val)) if val.is_integer() else str(val)
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('referral_reward_amount', ?)", (val_str,))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 تنظیمات زیرمجموعه‌گیری", callback_data="admin_referral")
    await message.answer("✅ مقدار پاداش با موفقیت ثبت شد.", reply_markup=builder.as_markup())
