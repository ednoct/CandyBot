"""
This module corresponds to the 'bot/routers/admin_finance.py' branch in the candy_architecture.md map.
Manages the Telegram Admin Finance menu, including gateway toggles and crypto wallet settings.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_finance_router = Router()

from aiogram.fsm.state import State, StatesGroup

class FinanceStates(StatesGroup):
    """Class representing FinanceStates."""
    waiting_for_crypto_setting = State()

# === ROUTER: FINANCE MENU ===
@admin_finance_router.callback_query(F.data == "admin_finance")
async def finance_menu(callback: types.CallbackQuery):
    """Handles finance menu."""
    if not is_admin(callback.message): return
    
    from database.db_manager import DB_PATH
    import aiosqlite
    
    async with aiosqlite.connect(DB_PATH) as db:
        async def get_status(code):
            """Handles get status."""
            key = f"{code}_status" if code in ['tetra', 'usdt', 'gram'] else f"gateway_status_{code}"
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return (row and row[0] == '1') or (not row and code in ['cart', 'zarinpal'])
                
        status_cart = "✅" if await get_status('cart') else "❌"
        status_tetra = "✅" if await get_status('tetra') else "❌"
        status_usdt = "✅" if await get_status('usdt') else "❌"
        status_gram = "✅" if await get_status('gram') else "❌"
    
    builder = InlineKeyboardBuilder()
    
    # Gateways (Parity with finance.php)
    builder.button(text="کارت به کارت:", callback_data="none")
    builder.button(text=status_cart, callback_data="toggle_fin_cart")
    
    builder.button(text="Tetra:", callback_data="none")
    builder.button(text=status_tetra, callback_data="toggle_fin_tetra")
    
    builder.button(text="USDT:", callback_data="none")
    builder.button(text=status_usdt, callback_data="toggle_fin_usdt")
    
    builder.button(text="GRAM:", callback_data="none")
    builder.button(text=status_gram, callback_data="toggle_fin_gram")
    
    # Settings
    builder.button(text="💳 تنظیم شماره کارت", callback_data="fin_set_card")
    builder.button(text="🪙 آدرس کیف پول‌ها", callback_data="fin_crypto_wallets")
    builder.button(text="🚫 استثناء تایید خودکار", callback_data="fin_auto_confirm_exceptions")
    
    # New Options
    builder.button(text="🤖 تایید رسید بدون بررسی", callback_data="toggle_auto_confirm_global")
    builder.button(text="💵 رسید های تایید نشده", callback_data="fin_pending_receipts")
    builder.button(text="📈 محدودیت‌های واریز", callback_data="fin_limits_menu")
    
    # Back
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 2, 2, 1, 1, 1, 1, 1)
    
    await callback.message.edit_text("💎 **مدیریت مالی و درگاه‌ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data == "fin_set_card")
async def set_card_number_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set card number prompt."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_card_number)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو و بازگشت", callback_data="admin_finance")
    await callback.message.edit_text("لطفا شماره کارت جدید (۱۶ رقمی) را ارسال کنید:", reply_markup=builder.as_markup())

@admin_finance_router.message(AdminStates.waiting_for_card_number)
async def set_card_number_process(message: types.Message, state: FSMContext):
    """Handles set card number process."""
    if not is_admin(message): return
    
    card_number = message.text.strip()
    if not card_number.isdigit() or len(card_number) != 16:
        return await message.answer("❌ شماره کارت نامعتبر است. باید دقیقا ۱۶ رقم باشد.")
        
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('card_number', card_number))
        await db.commit()
        
    await state.set_state(None)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    await message.answer(f"✅ شماره کارت با موفقیت به `{card_number}` تغییر یافت.", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.startswith("toggle_fin_"))
async def handle_finance_toggles(callback: types.CallbackQuery):
    """Handles handle finance toggles."""
    if not is_admin(callback.message): return
    
    code = callback.data.split('_')[2]
    from database.db_manager import DB_PATH
    import aiosqlite
    
    async with aiosqlite.connect(DB_PATH) as db:
        key_name = f"{code}_status" if code in ['tetra', 'usdt', 'gram'] else f"gateway_status_{code}"
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key_name,)) as cursor:
            row = await cursor.fetchone()
            
        current_status = row[0] if row else ('1' if code in ['cart', 'zarinpal'] else '0')
        new_status = '0' if current_status == '1' else '1'
        
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key_name, new_status))
        await db.commit()
        
    await callback.answer(f"💎 وضعیت درگاه تغییر کرد.", show_alert=True)
    await finance_menu(callback)

# === ROUTER: CRYPTO WALLETS ===
@admin_finance_router.callback_query(F.data == "fin_crypto_wallets")
async def crypto_wallets_menu(callback: types.CallbackQuery):
    """Handles crypto wallets menu."""
    if not is_admin(callback.message): return
    builder = InlineKeyboardBuilder()
    builder.button(text="تغییر آدرس USDT", callback_data="set_wallet_usdt")
    builder.button(text="تغییر آدرس GRAM", callback_data="set_wallet_gram")
    builder.button(text="تغییر کامنت GRAM", callback_data="set_memo_gram")
    builder.button(text="تغییر لینک صرافی", callback_data="set_exchanger_gram")
    builder.button(text="تنظیم API تترا", callback_data="set_tetra_api_key")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(1)
    await callback.message.edit_text("🪙 **مدیریت آدرس‌های کریپتو**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.in_(["set_wallet_usdt", "set_wallet_gram", "set_memo_gram", "set_exchanger_gram", "set_tetra_api_key"]))
async def set_crypto_wallet_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set crypto wallet prompt."""
    if not is_admin(callback.message): return
    key_name = callback.data.replace('set_', '')
    await state.update_data(setting_key=key_name)
    await state.set_state(FinanceStates.waiting_for_crypto_setting)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="fin_crypto_wallets")
    await callback.message.edit_text(f"لطفا مقدار جدید برای `{key_name}` را ارسال کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.message(FinanceStates.waiting_for_crypto_setting)
async def set_crypto_wallet_process(message: types.Message, state: FSMContext):
    """Handles set crypto wallet process."""
    if not is_admin(message): return
    data = await state.get_data()
    key_name = data.get('setting_key')
    new_value = message.text.strip()
    
    from database.db_manager import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key_name, new_value))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="fin_crypto_wallets")
    await message.answer(f"✅ تنظیمات با موفقیت ذخیره شد.", reply_markup=builder.as_markup())

# === ROUTER: AUTO CONFIRM EXCEPTIONS ===
@admin_finance_router.callback_query(F.data == "fin_auto_confirm_exceptions")
async def auto_confirm_exceptions_menu(callback: types.CallbackQuery):
    """Handles auto confirm exceptions menu."""
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ اضافه کردن کاربر", callback_data="add_exception")
    builder.button(text="❌ حذف از لیست", callback_data="del_exception")
    builder.button(text="👁 مشاهده لیست", callback_data="view_exceptions")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(2, 1, 1)
    
    await callback.message.edit_text("🚫 **استثناء کردن کاربر از تایید خودکار**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data == "add_exception")
async def add_exception_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add exception start."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_exclude_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="fin_auto_confirm_exceptions")
    await callback.message.edit_text("📌 آیدی عددی کاربر (User ID) را ارسال کنید:", reply_markup=builder.as_markup())

@admin_finance_router.message(AdminStates.waiting_for_exclude_id)
async def add_exception_process(message: types.Message, state: FSMContext):
    """Handles add exception process."""
    if not is_admin(message): return
    
    try:
        user_id = int(message.text)
    except ValueError:
        return await message.answer("❌ لطفا فقط آیدی عددی وارد کنید.")
        
    from database.db_manager import DB_PATH
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'auto_confirm_exceptions'") as cursor:
            row = await cursor.fetchone()
            
        exceptions = json.loads(row[0]) if row else []
        
        if user_id in exceptions:
            return await message.answer("❌ کاربر در لیست استثناء وجود دارد.")
            
        exceptions.append(user_id)
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_confirm_exceptions', ?)", (json.dumps(exceptions),))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت استثناها", callback_data="fin_auto_confirm_exceptions")
    await message.answer("✅ کاربر با موفقیت به لیست اضافه گردید.", reply_markup=builder.as_markup())

@admin_finance_router.callback_query(F.data == "del_exception")
async def del_exception_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles del exception start."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_remove_exclude_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="fin_auto_confirm_exceptions")
    await callback.message.edit_text("📌 آیدی عددی کاربر را جهت حذف از لیست ارسال کنید:", reply_markup=builder.as_markup())

@admin_finance_router.message(AdminStates.waiting_for_remove_exclude_id)
async def del_exception_process(message: types.Message, state: FSMContext):
    """Handles del exception process."""
    if not is_admin(message): return
    
    try:
        user_id = int(message.text)
    except ValueError:
        return await message.answer("❌ لطفا فقط آیدی عددی وارد کنید.")
        
    from database.db_manager import DB_PATH
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'auto_confirm_exceptions'") as cursor:
            row = await cursor.fetchone()
            
        exceptions = json.loads(row[0]) if row else []
        
        if user_id not in exceptions:
            return await message.answer("❌ کاربر در لیست استثناء وجود ندارد.")
            
        exceptions.remove(user_id)
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_confirm_exceptions', ?)", (json.dumps(exceptions),))
        await db.commit()
        
    await state.set_state(None)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت استثناها", callback_data="fin_auto_confirm_exceptions")
    await message.answer("✅ کاربر با موفقیت از لیست حذف گردید.", reply_markup=builder.as_markup())

@admin_finance_router.callback_query(F.data == "view_exceptions")
async def view_exceptions_process(callback: types.CallbackQuery):
    """Handles view exceptions process."""
    if not is_admin(callback.message): return
    
    from database.db_manager import DB_PATH
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'auto_confirm_exceptions'") as cursor:
            row = await cursor.fetchone()
            
    exceptions = json.loads(row[0]) if row else []
    
    if not exceptions:
        return await callback.answer("❌ کاربری در لیست وجود ندارد", show_alert=True)
        
    text = "لیست افراد استثناء:\n\n" + "\n".join([f"`{u}`" for u in exceptions])
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="fin_auto_confirm_exceptions")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: GLOBAL AUTO CONFIRM ===
@admin_finance_router.callback_query(F.data == 'toggle_auto_confirm_global')
async def toggle_auto_confirm(callback: types.CallbackQuery):
    """Handles toggle auto confirm."""
    if not is_admin(callback.message): return
    from database.db_manager import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'global_auto_confirm'") as cursor:
            row = await cursor.fetchone()
        
        current_status = row[0] if row else 'off'
        new_status = 'on' if current_status == 'off' else 'off'
        
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_auto_confirm', ?)", (new_status,))
        await db.commit()
        
    status_text = 'فعال (✅)' if new_status == 'on' else 'غیرفعال (❌)'
    await callback.answer(f"تایید خودکار کارت به کارت: {status_text}", show_alert=True)

# === ROUTER: PENDING RECEIPTS ===
@admin_finance_router.callback_query(F.data == 'fin_pending_receipts')
async def pending_receipts_menu(callback: types.CallbackQuery):
    """Handles pending receipts menu."""
    if not is_admin(callback.message): return
    
    from database.db_manager import DB_PATH
    import aiosqlite
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payment_reports WHERE status = 'pending'") as cursor:
            pending = await cursor.fetchall()
            
    builder = InlineKeyboardBuilder()
    
    if not pending:
        builder.button(text="🔙 بازگشت", callback_data="admin_finance")
        return await callback.message.edit_text("💵 **رسیدهای تایید نشده**\n\nدر حال حاضر رسید تایید نشده‌ای وجود ندارد.", reply_markup=builder.as_markup(), parse_mode="Markdown")
        
    for p in pending:
        builder.button(text=f"💳 {p['user_id']} - {p['amount']}T", callback_data=f"none")
        builder.button(text="✅", callback_data=f"confirm_receipt_{p['id']}")
        builder.button(text="❌", callback_data=f"reject_receipt_{p['id']}")
        
    builder.button(text="❌ حذف همه رسیدها", callback_data="del_all_receipts")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(3, *([3]*len(pending)), 1, 1)
    
    await callback.message.edit_text(f"💵 **رسیدهای تایید نشده ({len(pending)} مورد)**\n\nلطفاً رسیدها را بررسی و تایید یا رد کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: LIMITS MENU ===
@admin_finance_router.callback_query(F.data == 'fin_limits_menu')
async def limits_menu(callback: types.CallbackQuery):
    """Handles limits menu."""
    if not is_admin(callback.message): return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    gateways = [('کارت به کارت', 'cart')]
    for name, code in gateways:
        builder.button(text=f"⬇️ حداقل {name}", callback_data=f"lim_min_{code}")
        builder.button(text=f"⬆️ حداکثر {name}", callback_data=f"lim_max_{code}")
        
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(2)
    
    await callback.message.edit_text("📈 **تنظیم محدودیت‌های واریز**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.startswith('lim_'))
async def set_limit_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set limit prompt."""
    if not is_admin(callback.message): return
    limit_type = callback.data.split('_')[1] # min or max
    gateway = callback.data.split('_')[2]
    
    await state.update_data(limit_type=limit_type, gateway=gateway)
    await state.set_state(AdminStates.waiting_for_min_max_limit)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="fin_limits_menu")
    typ_str = "حداقل" if limit_type == 'min' else "حداکثر"
    await callback.message.edit_text(f"📌 مبلغ {typ_str} برای درگاه {gateway} را ارسال کنید:", reply_markup=builder.as_markup())

@admin_finance_router.message(AdminStates.waiting_for_min_max_limit)
async def set_limit_process(message: types.Message, state: FSMContext):
    """Handles set limit process."""
    if not is_admin(message): return
    try:
        amount = int(message.text)
    except:
        return await message.answer("❌ لطفا فقط عدد وارد کنید.")
        
    data = await state.get_data()
    key = f"{data['limit_type']}_limit_{data['gateway']}"
    
    from database.db_manager import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(amount)))
        await db.commit()
        
    await state.set_state(None)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت محدودیت‌ها", callback_data="fin_limits_menu")
    await message.answer("✅ محدودیت با موفقیت تنظیم شد.", reply_markup=builder.as_markup())


