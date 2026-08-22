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
            key = f"{code}_status" if code in ['frenzyex', 'usdt', 'gram'] else f"gateway_status_{code}"
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return (row and row[0] == '1')
                
    # Gateways (Parity with finance.php)
    
    builder.button(text="FrenzyEx:", callback_data="none")
    builder.button(text=status_frenzyex, callback_data="toggle_fin_frenzyex")
    
    builder.button(text="USDT:", callback_data="none")
    builder.button(text=status_usdt, callback_data="toggle_fin_usdt")
    
    builder.button(text="GRAM:", callback_data="none")
    builder.button(text=status_gram, callback_data="toggle_fin_gram")
    
    # Settings
    builder.button(text="🪙 تنظیم متغیرها", callback_data="fin_crypto_wallets")
    
    # New Options
    builder.button(text="🎁 مدیریت تخفیف و هدیه", callback_data="admin_discounts")
    builder.button(text="💵 رسید های تایید نشده", callback_data="fin_pending_receipts")
    builder.button(text="📈 محدودیت‌های شارژ کیف پول", callback_data="fin_limits_menu")
    
    # Back
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 1, 1, 1, 1)
    
    await callback.message.edit_text("💎 **مدیریت مالی و درگاه‌ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")



@admin_finance_router.callback_query(F.data.startswith("toggle_fin_"))
async def handle_finance_toggles(callback: types.CallbackQuery):
    """Handles handle finance toggles."""
    if not is_admin(callback.message): return
    
    code = callback.data.split('_')[2]
    from database.db_manager import DB_PATH
    import aiosqlite
    
    async with aiosqlite.connect(DB_PATH) as db:
        key_name = f"{code}_status" if code in ['frenzyex', 'usdt', 'gram'] else f"gateway_status_{code}"
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key_name,)) as cursor:
            row = await cursor.fetchone()
            
        current_status = row[0] if row else '0'
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
    builder.button(text="تنظیم API Key FrenzyEx", callback_data="set_frenzyex_api_key")
    builder.button(text="تنظیم Base URL FrenzyEx", callback_data="set_frenzyex_base_url")
    builder.button(text="تنظیم Webhook Secret FrenzyEx", callback_data="set_frenzyex_callback_secret")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(1)
    await callback.message.edit_text("🪙 **مدیریت متغیر درگاه ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.in_(["set_wallet_usdt", "set_wallet_gram", "set_memo_gram", "set_exchanger_gram", "set_frenzyex_api_key", "set_frenzyex_base_url", "set_frenzyex_callback_secret"]))
async def set_crypto_wallet_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set crypto wallet prompt."""
    if not is_admin(callback.message): return
    key_name = callback.data.replace('set_', '')
    await state.update_data(setting_key=key_name)
    await state.set_state(FinanceStates.waiting_for_crypto_setting)
    from database.db_manager import DB_PATH
    import aiosqlite
    
    current_val_text = ""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key_name,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                val = row[0]
                if key_name == 'frenzyex_callback_secret':
                    if len(val) > 8:
                        val = f"{val[:4]}{'*' * (len(val) - 8)}{val[-4:]}"
                    else:
                        val = "****"
                current_val_text = f"\nمقدار فعلی: `{val}`\n"
                
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="fin_crypto_wallets")
    await callback.message.edit_text(f"لطفا مقدار جدید برای `{key_name}` را ارسال کنید:{current_val_text}", reply_markup=builder.as_markup(), parse_mode="Markdown")

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
    
    gateways = [('شارژ کیف پول', 'wallet')]
    for name, code in gateways:
        builder.button(text=f"⬇️ حداقل {name}", callback_data=f"lim_min_{code}")
        builder.button(text=f"⬆️ حداکثر {name}", callback_data=f"lim_max_{code}")
        
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(2)
    
    await callback.message.edit_text("📈 **تنظیم محدودیت‌های شارژ کیف پول**", reply_markup=builder.as_markup(), parse_mode="Markdown")

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


