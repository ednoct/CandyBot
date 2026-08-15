# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db_manager

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
    from bot.config import ADMIN_IDS
    if message.from_user.id in ADMIN_IDS:
        builder.row(types.InlineKeyboardButton(text="⚙️ ورود به مدیریت", callback_data="admin_panel_start"))
        
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
    from bot.config import ADMIN_IDS
    if callback.from_user.id in ADMIN_IDS:
        builder.row(types.InlineKeyboardButton(text="⚙️ ورود به مدیریت", callback_data="admin_panel_start"))
        
    await callback.message.edit_text(welcome_text, reply_markup=builder.as_markup())
from aiogram.fsm.context import FSMContext
from ..states import UserStates
import aiosqlite

# === NEW HANDLERS FOR USER ROUTER ===
@user_router.callback_query(F.data == "my_services")
async def my_services(callback: types.CallbackQuery):
    from database.db_manager import DB_PATH
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
    # We create a FSMContext directly for payment.py since this is a pseudo invoice
    await state.update_data(
        final_amount=amount,
        base_price=amount,
        plan_id=0,
        days=0,
        gb=0,
        wallet_deduction=0,
        discount_code=None,
        discount_amount=0,
        gift_code=None,
        gift_amount=0
    )
    
    builder = InlineKeyboardBuilder()
    
    # Show gateways directly
    from database.db_manager import DB_PATH
    import aiosqlite
    available_gateways = [
        ('کارت به کارت', 'cart', 'pay_card'),
        ('گرام (TON)', 'gram', 'pay_gram'),
        ('تتر (BSC)', 'usdt', 'pay_usdt'),
        ('کارت به کارت هوشمند', 'tetra', 'pay_tetra')
    ]
    
    async with aiosqlite.connect(DB_PATH) as db:
        for name, code, cb_data in available_gateways:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (f"gateway_status_{code}",)) as cursor:
                row = await cursor.fetchone()
                # By default make cart active
                is_active = (row and row[0] == '1') or (not row and code in ['cart'])
                if is_active:
                    builder.row(types.InlineKeyboardButton(text=f"💳 {name}", callback_data=cb_data))
                    
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="my_profile"))
    
    from bot.config import ADMIN_IDS
    if message.from_user.id in ADMIN_IDS:
        builder.row(types.InlineKeyboardButton(text="⚙️ ورود به مدیریت", callback_data="admin_panel_start"))
    
    await message.answer(f"💰 مبلغ {amount:,} تومان جهت شارژ تایید شد.\nلطفاً یک روش پرداخت انتخاب کنید:", reply_markup=builder.as_markup())
