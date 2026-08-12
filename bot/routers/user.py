# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ...database import db_manager

user_router = Router()

# === ROUTER: START COMMAND ===
@user_router.message(CommandStart())
async def cmd_start(message: types.Message):
    await db_manager.create_user(message.from_user.id, message.from_user.username)
    
    # Fetch dynamic settings
    welcome_text = await db_manager.get_setting('bot_text_welcome', "به ربات کندی کانکت خوش آمدید!\nجهت تهیه لایسنس یکبار مصرف از منوی زیر استفاده کنید.")
    keyboard_layout_str = await db_manager.get_setting('keyboard_layout')
    
    builder = InlineKeyboardBuilder()
    if keyboard_layout_str:
        import json
        try:
            layout = json.loads(keyboard_layout_str)
            for row in layout:
                for btn in row:
                    builder.button(text=btn['text'], callback_data=btn['callback_data'])
            builder.adjust(*[len(r) for r in layout])
        except Exception:
            # Fallback
            builder.button(text="🛒 خرید اشتراک", callback_data="buy_subscription")
            builder.button(text="📦 سرویس های من", callback_data="my_services")
            builder.button(text="🎁 تست رایگان", callback_data="free_test")
            builder.button(text="👤 پروفایل من (کیف پول)", callback_data="my_profile")
            builder.button(text="👥 زیرمجموعه گیری", callback_data="affiliate")
            builder.button(text="📱 دانلود اپلیکیشن", callback_data="app_download")
            builder.button(text="☎️ پشتیبانی", callback_data="support")
            builder.adjust(2, 2, 2, 1)
    else:
        builder.button(text="🛒 خرید اشتراک", callback_data="buy_subscription")
        builder.button(text="📦 سرویس های من", callback_data="my_services")
        builder.button(text="🎁 تست رایگان", callback_data="free_test")
        builder.button(text="👤 پروفایل من (کیف پول)", callback_data="my_profile")
        builder.button(text="👥 زیرمجموعه گیری", callback_data="affiliate")
        builder.button(text="📱 دانلود اپلیکیشن", callback_data="app_download")
        builder.button(text="☎️ پشتیبانی", callback_data="support")
        builder.adjust(2, 2, 2, 1)
    
    await message.answer(welcome_text, reply_markup=builder.as_markup())

# === ROUTER: BUY SUBSCRIPTION ===
@user_router.callback_query(F.data == "buy_subscription")
async def show_plans(callback: types.CallbackQuery):
    plans = await db_manager.get_plans()
    if not plans:
        return await callback.answer("فعلا پلنی برای خرید موجود نیست.", show_alert=True)
        
    builder = InlineKeyboardBuilder()
    for p in plans:
        builder.button(text=p['name'], callback_data=f"checkout_plan_{p['id']}")
    builder.button(text="🔙 برگشت", callback_data="main_menu")
    builder.adjust(1)
    
    await callback.message.edit_text("لطفاً نوع اشتراک را انتخاب کنید:", reply_markup=builder.as_markup())

# === ROUTER: USER PROFILE ===
@user_router.callback_query(F.data == "my_profile")
async def my_profile(callback: types.CallbackQuery):
    user = await db_manager.get_user(callback.from_user.id)
    text = f"👤 پروفایل کاربری\n\nآیدی: {user['id']}\nموجودی کیف پول: {user['balance']} تومان\nامتیاز: {user['score']}"
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 شارژ حساب", callback_data="wallet_charge")
    builder.button(text="🔙 برگشت", callback_data="main_menu")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# === ROUTER: MAIN MENU ===
@user_router.callback_query(F.data == "main_menu")
async def return_main_menu(callback: types.CallbackQuery):
    # Fetch dynamic settings
    welcome_text = await db_manager.get_setting('bot_text_welcome', "به ربات کندی کانکت خوش آمدید!\nجهت تهیه لایسنس یکبار مصرف از منوی زیر استفاده کنید.")
    keyboard_layout_str = await db_manager.get_setting('keyboard_layout')
    
    builder = InlineKeyboardBuilder()
    if keyboard_layout_str:
        import json
        try:
            layout = json.loads(keyboard_layout_str)
            for row in layout:
                for btn in row:
                    builder.button(text=btn['text'], callback_data=btn['callback_data'])
            builder.adjust(*[len(r) for r in layout])
        except Exception:
            # Fallback
            builder.button(text="🛒 خرید اشتراک", callback_data="buy_subscription")
            builder.button(text="📦 سرویس های من", callback_data="my_services")
            builder.button(text="🎁 تست رایگان", callback_data="free_test")
            builder.button(text="👤 پروفایل من (کیف پول)", callback_data="my_profile")
            builder.button(text="👥 زیرمجموعه گیری", callback_data="affiliate")
            builder.button(text="📱 دانلود اپلیکیشن", callback_data="app_download")
            builder.button(text="☎️ پشتیبانی", callback_data="support")
            builder.adjust(2, 2, 2, 1)
    else:
        builder.button(text="🛒 خرید اشتراک", callback_data="buy_subscription")
        builder.button(text="📦 سرویس های من", callback_data="my_services")
        builder.button(text="🎁 تست رایگان", callback_data="free_test")
        builder.button(text="👤 پروفایل من (کیف پول)", callback_data="my_profile")
        builder.button(text="👥 زیرمجموعه گیری", callback_data="affiliate")
        builder.button(text="📱 دانلود اپلیکیشن", callback_data="app_download")
        builder.button(text="☎️ پشتیبانی", callback_data="support")
        builder.adjust(2, 2, 2, 1)
    
    await callback.message.edit_text(welcome_text, reply_markup=builder.as_markup())
from aiogram.fsm.context import FSMContext
from ..states import UserStates
import aiosqlite

# === NEW HANDLERS FOR USER ROUTER ===
@user_router.callback_query(F.data == "my_services")
async def my_services(callback: types.CallbackQuery):
    from ...database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE user_id = ? AND status = 'paid' ORDER BY created_at DESC LIMIT 10", (callback.from_user.id,)) as cursor:
            invoices = await cursor.fetchall()
            
    if not invoices:
        return await callback.answer("شما هیچ سرویس فعالی ندارید.", show_alert=True)
        
    text = "📦 **لیست 10 سرویس آخر شما:**\n\n"
    for inv in invoices:
        text += f"🔹 فاکتور: `{inv['id']}` | وضعیت: ✅ پرداخت شده\n"
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 برگشت", callback_data="main_menu")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@user_router.callback_query(F.data == "app_download")
async def app_download(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 دانلود اندروید", url="https://play.google.com")
    builder.button(text="📥 دانلود ویندوز", url="https://example.com")
    builder.button(text="🔙 برگشت", callback_data="main_menu")
    builder.adjust(1)
    await callback.message.edit_text("📱 **دانلود اپلیکیشن کندی کانکت:**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@user_router.callback_query(F.data == "affiliate")
async def affiliate_dashboard(callback: types.CallbackQuery):
    user = await db_manager.get_user(callback.from_user.id)
    bot_info = await callback.bot.me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    
    text = f"👥 **سیستم زیرمجموعه گیری (بازاریابی)**\n\n"
    text += f"تعداد زیرمجموعه‌های شما: {user.get('affiliatescount', 0)} نفر\n\n"
    text += f"🔗 لینک اختصاصی شما:\n`{ref_link}`"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 برگشت", callback_data="main_menu")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@user_router.callback_query(F.data == "wallet_charge")
async def wallet_charge_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_charge_amount)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="my_profile")
    await callback.message.edit_text("💰 لطفاً مبلغ مورد نظر برای شارژ کیف پول را به تومان وارد کنید (مثلاً 50000):", reply_markup=builder.as_markup())

@user_router.message(UserStates.waiting_for_charge_amount)
async def process_wallet_charge(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")
        
    amount = int(message.text)
    if amount < 10000:
        return await message.answer("❌ حداقل مبلغ شارژ 10,000 تومان است.")
        
    await state.set_state(None)
    
    # We create a pseudo-invoice for Wallet Charge and redirect to checkout
    from ...database.db_manager import DB_PATH
    import uuid
    inv_id = str(uuid.uuid4())[:8].upper()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO invoices 
            (id, user_id, plan_id, base_price, final_amount, status) 
            VALUES (?, ?, ?, ?, ?, ?)''', 
            (inv_id, message.from_user.id, 0, amount, amount, 'pending_charge'))
        await db.commit()
        
    builder = InlineKeyboardBuilder()
    # Route to standard checkout payment selection
    builder.button(text="💳 پرداخت", callback_data=f"pay_invoice_{inv_id}")
    builder.button(text="🔙 انصراف", callback_data="my_profile")
    
    await message.answer(f"🧾 فاکتور شارژ کیف پول ایجاد شد.\nمبلغ: {amount} تومان\nشماره فاکتور: {inv_id}", reply_markup=builder.as_markup())
