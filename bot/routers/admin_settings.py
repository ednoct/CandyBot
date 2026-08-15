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
    if not is_admin(callback.message): return
    
    # In a real app we'd fetch this from db_manager.get_settings()
    # Mocking standard toggles for parity
    status_on = "✅"
    status_off = "❌"
    
    builder = InlineKeyboardBuilder()
    
    # Bot Status
    builder.button(text="وضعیت ربات:", callback_data="none")
    builder.button(text=status_on, callback_data="toggle_bot_status")
    
    # Auth Mode
    builder.button(text="تایید شماره موبایل:", callback_data="none")
    builder.button(text=status_off, callback_data="toggle_phone_auth")
    
    # Test Accounts Limit
    builder.button(text="اکانت تست:", callback_data="none")
    builder.button(text=status_off, callback_data="toggle_test_acc")
    
    # Channels & Admins
    builder.button(text="📯 مدیریت کانال‌ها", callback_data="admin_manage_channels")
    builder.button(text="👨‍💻 مدیریت ادمین‌ها", callback_data="admin_manage_admins")
    
    # Apps Management
    builder.button(text="📱 مدیریت برنامه‌ها", callback_data="admin_manage_apps")
    
    # New Utilities
    builder.button(text="📚 مدیریت آموزش‌ها", callback_data="admin_manage_tutorials")
    builder.button(text="🎰 تنظیمات قرعه‌کشی", callback_data="admin_manage_lottery")
    builder.button(text="🖼 پس زمینه کیوآرکد", callback_data="admin_manage_qr")
    
    # Back
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1, 1)
    
    await callback.message.edit_text("⚙️ **تنظیمات عمومی ربات**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data.in_({"toggle_bot_status", "toggle_phone_auth", "toggle_test_acc"}))
async def handle_toggles(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    await callback.answer("⚙️ تنظیم تغییر کرد (Mock).", show_alert=True)
    await settings_menu(callback)

# === ROUTER: CHANNELS MANAGEMENT ===
@admin_settings_router.callback_query(F.data == "admin_manage_channels")
async def manage_channels(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن کانال", callback_data="add_channel")
    builder.button(text="❌ حذف کانال", callback_data="del_channel")
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(2, 1)
    
    await callback.message.edit_text("📯 **مدیریت کانال‌های جوین اجباری**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_channel_remark)
    await callback.message.edit_text("📌 یک نام برای دکمه عضویت چنل انتخاب نمایید (مثلا: کانال پشتیبانی):")

@admin_settings_router.message(AdminStates.waiting_for_channel_remark)
async def add_channel_remark(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    await state.update_data(channel_remark=message.text)
    await state.set_state(AdminStates.waiting_for_channel_url)
    await message.answer("📌 لینک جوین کانال را ارسال کنید (باید با https شروع شود):")

@admin_settings_router.message(AdminStates.waiting_for_channel_url)
async def add_channel_url(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    url = message.text
    if not url.startswith("http"):
        return await message.answer("❌ لینک نامعتبر است.")
        
    data = await state.get_data()
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO channels (remark, linkjoin, link) VALUES (?, ?, ?)", (data['channel_remark'], url, url))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_manage_channels")
    await message.answer("✅ کانال جوین اجباری با موفقیت ثبت گردید.", reply_markup=builder.as_markup())

# === ROUTER: ADMIN MANAGEMENT ===
@admin_settings_router.callback_query(F.data == "admin_manage_admins")
async def manage_admins(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_admin_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    await callback.message.edit_text("👨‍💻 **مدیریت ادمین‌ها**\n\nبرای افزودن ادمین جدید، لطفا آیدی عددی (User ID) تلگرام او را بفرستید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.message(AdminStates.waiting_for_admin_id)
async def add_admin_save(message: types.Message, state: FSMContext):
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

# === ROUTER: MANAGE APPS ===
@admin_settings_router.callback_query(F.data == "admin_manage_apps")
async def manage_apps(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن برنامه", callback_data="add_app")
    builder.button(text="❌ حذف برنامه", callback_data="del_app")
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(2, 1)
    
    await callback.message.edit_text("📱 **مدیریت لینک دانلود برنامه‌ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data == "add_app")
async def add_app_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_app_name)
    await callback.message.edit_text("📌 جهت اضافه کردن لینک دانلود برنامه نام اپ یا نام دکمه را ارسال نمایید (مثلا: دانلود Candy Connect):")

@admin_settings_router.message(AdminStates.waiting_for_app_name)
async def add_app_name(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if len(message.text) > 200:
        return await message.answer("📌 نام باید کمتر از ۲۰۰ کاراکتر باشد.")
        
    await state.update_data(app_name=message.text)
    await state.set_state(AdminStates.waiting_for_app_url)
    await message.answer("📌 لینک دانلود اپ را ارسال نمایید:")

@admin_settings_router.message(AdminStates.waiting_for_app_url)
async def add_app_url(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    url = message.text
    if not url.startswith("http"):
        return await message.answer("❌ لینک نامعتبر است.")
        
    data = await state.get_data()
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO app (name, link) VALUES (?, ?)", (data['app_name'], url))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت برنامه‌ها", callback_data="admin_manage_apps")
    await message.answer("✅ لینک اپ شما با موفقیت اضافه گردید.", reply_markup=builder.as_markup())

@admin_settings_router.callback_query(F.data == "del_app")
async def del_app_start(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name FROM app") as cursor:
            apps = await cursor.fetchall()
            
    if not apps:
        return await callback.answer("برنامه‌ای یافت نشد.", show_alert=True)
        
    builder = InlineKeyboardBuilder()
    for app in apps:
        builder.button(text=app['name'], callback_data=f"remove_app_{app['id']}")
    builder.button(text="🔙 بازگشت", callback_data="admin_manage_apps")
    builder.adjust(1)
    
    await callback.message.edit_text("📌 برای حذف برنامه از لیست زیر نام برنامه را انتخاب کنید:", reply_markup=builder.as_markup())

@admin_settings_router.callback_query(F.data.startswith("remove_app_"))
async def del_app_process(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    app_id = int(callback.data.split("_")[2])
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM app WHERE id = ?", (app_id,))
        await db.commit()
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت برنامه‌ها", callback_data="admin_manage_apps")
    await callback.message.edit_text("✅ برنامه با موفقیت حذف گردید.", reply_markup=builder.as_markup())
# === ROUTER: MANAGE TUTORIALS ===
@admin_settings_router.callback_query(F.data == "admin_manage_tutorials")
async def manage_tutorials_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    gateways = [
        ('کارت به کارت', 'cart'), 
        ('NowPayments', 'nowpayment'), 
        ('پرفکت‌مانی', 'perfectmony'), 
        ('Plisio', 'plisio'), 
        ('آقای پرداخت', 'aqayepardakht'), 
        ('زرین‌پال', 'zarinpal'), 
        ('آفلاین', 'offline')
    ]
    
    for name, code in gateways:
        builder.button(text=f"📚 {name}", callback_data=f"set_tut_{code}")
        
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(2)
    
    await callback.message.edit_text("📚 **مدیریت آموزش‌ها**\nدرگاه مورد نظر را جهت تنظیم آموزش (متن/عکس/ویدیو) انتخاب کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data.startswith("set_tut_"))
async def set_tutorial_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    gateway = callback.data.split('_')[2]
    
    await state.update_data(tut_gateway=gateway)
    await state.set_state(AdminStates.waiting_for_tutorial_content)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="admin_manage_tutorials")
    
    msg = f"📌 آموزش خود را برای درگاه {gateway} ارسال نمایید.\n- برای غیرفعال‌سازی عدد 2 را بفرستید.\n- می‌توانید متن، عکس، یا ویدیو ارسال کنید."
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

@admin_settings_router.message(AdminStates.waiting_for_tutorial_content)
async def set_tutorial_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    data = await state.get_data()
    gateway = data['tut_gateway']
    
    import json
    tut_data = {}
    
    if message.text:
        if message.text.strip() == '2':
            tut_data = "2"
        else:
            tut_data = json.dumps({"type": "text", "text": message.text})
    elif message.photo:
        tut_data = json.dumps({"type": "photo", "text": message.caption or "", "photoid": message.photo[-1].file_id})
    elif message.video:
        tut_data = json.dumps({"type": "video", "text": message.caption or "", "videoid": message.video.file_id})
    else:
        return await message.answer("❌ محتوای ارسال نامعتبر است.")
        
    from database.db_manager import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"help_{gateway}", tut_data))
        await db.commit()
        
    await state.set_state(None)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 آموزش‌ها", callback_data="admin_manage_tutorials")
    await message.answer("✅ آموزش با موفقیت ذخیره گردید.", reply_markup=builder.as_markup())

# === ROUTER: LOTTERY ===
@admin_settings_router.callback_query(F.data == "admin_manage_lottery")
async def manage_lottery_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ جایزه نفر اول", callback_data="set_lot_1")
    builder.button(text="2️⃣ جایزه نفر دوم", callback_data="set_lot_2")
    builder.button(text="3️⃣ جایزه نفر سوم", callback_data="set_lot_3")
    builder.button(text="🎲 مبلغ برنده شدن در گردونه", callback_data="set_lot_wheel")
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(1)
    
    await callback.message.edit_text("🎰 **تنظیمات قرعه‌کشی و گردونه شانس**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.callback_query(F.data.startswith("set_lot_"))
async def set_lottery_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    lot_type = callback.data.split('_')[2]
    
    await state.update_data(lot_type=lot_type)
    await state.set_state(AdminStates.waiting_for_lottery_prize)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="admin_manage_lottery")
    await callback.message.edit_text("📌 مقدار مبلغی که می‌خواهید حساب کاربر شارژ شود را ارسال نمایید:", reply_markup=builder.as_markup())

@admin_settings_router.message(AdminStates.waiting_for_lottery_prize)
async def set_lottery_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit():
        return await message.answer("❌ مبلغ نامعتبر است.")
        
    data = await state.get_data()
    lot_type = data['lot_type']
    
    from database.db_manager import DB_PATH
    import json
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        if lot_type == 'wheel':
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('wheel_luck_price', ?)", (message.text,))
        else:
            async with db.execute("SELECT value FROM settings WHERE key = 'Lottery_prize'") as cursor:
                row = await cursor.fetchone()
            prizes = json.loads(row[0]) if row else {}
            
            prizes[lot_type] = message.text
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('Lottery_prize', ?)", (json.dumps(prizes),))
            
        await db.commit()
        
    await state.set_state(None)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 قرعه‌کشی", callback_data="admin_manage_lottery")
    await message.answer("✅ مبلغ جایزه با موفقیت تنظیم شد.", reply_markup=builder.as_markup())

# === ROUTER: QR BACKGROUND ===
@admin_settings_router.callback_query(F.data == "admin_manage_qr")
async def manage_qr_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_qr_background)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="admin_settings")
    await callback.message.edit_text("🖼 **پس زمینه کیوآرکد**\nتصویر خود را برای پس زمینه ارسال کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_settings_router.message(AdminStates.waiting_for_qr_background)
async def manage_qr_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.photo:
        return await message.answer("❌ لطفاً یک تصویر ارسال کنید.")
        
    photo_id = message.photo[-1].file_id
    file = await message.bot.get_file(photo_id)
    file_path = file.file_path
    
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    custom_jpg = os.path.join(project_root, 'custom.jpg')
    images_jpg = os.path.join(project_root, 'images.jpg')
    
    await message.bot.download_file(file_path, custom_jpg)
    await message.bot.download_file(file_path, images_jpg)
    
    await state.set_state(None)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 تنظیمات", callback_data="admin_settings")
    await message.answer("🖼 پس زمینه با موفقیت تنظیم گردید.", reply_markup=builder.as_markup())
