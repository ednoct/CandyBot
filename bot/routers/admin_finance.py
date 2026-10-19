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
from utils.ui_helpers import safe_edit_message
import aiosqlite

admin_finance_router = Router()

from aiogram.fsm.state import State, StatesGroup

class FinanceStates(StatesGroup):
    """Class representing FinanceStates."""
    waiting_for_crypto_setting = State()

# === ROUTER: FINANCE MENU ===
@admin_finance_router.callback_query(F.data == "admin_finance")
async def finance_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles finance menu."""
    if not is_admin(callback): return
    if state:
        await state.clear()
    
    from database.db_manager import DB_PATH
    import aiosqlite
    
    async with aiosqlite.connect(DB_PATH) as db:
        async def get_status(code):
            """Handles get status."""
            key = f"{code}_status" if code in ['frenzyex', 'usdt', 'gram'] else f"gateway_status_{code}"
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return (row and row[0] == '1')
                
        is_frenzyex = await get_status('frenzyex')
        is_usdt = await get_status('usdt')
        is_gram = await get_status('gram')
                
    status_frenzyex = "✅" if is_frenzyex else "❌"
    status_usdt = "✅" if is_usdt else "❌"
    status_gram = "✅" if is_gram else "❌"
    
    builder = InlineKeyboardBuilder()
                
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
    builder.button(text="🔙 بازگشت", callback_data="admin_back", style="danger")
    
    builder.adjust(2, 2, 2, 1, 1, 1, 1)
    
    await safe_edit_message(callback, "💎 **مدیریت مالی و درگاه‌ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")



@admin_finance_router.callback_query(F.data.startswith("toggle_fin_"))
async def handle_finance_toggles(callback: types.CallbackQuery):
    """Handles handle finance toggles."""
    if not is_admin(callback): return
    
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
async def crypto_wallets_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles crypto wallets menu."""
    if not is_admin(callback): return
    if state:
        await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="تغییر آدرس USDT", callback_data="set_wallet_usdt")
    builder.button(text="تغییر آدرس GRAM", callback_data="set_wallet_gram")
    builder.button(text="تغییر کامنت GRAM", callback_data="set_memo_gram")
    builder.button(text="تغییر لینک صرافی", callback_data="set_exchanger_gram")
    builder.button(text="تنظیم API Key FrenzyEx", callback_data="set_frenzyex_api_key")
    builder.button(text="تنظیم Base URL FrenzyEx", callback_data="set_frenzyex_base_url")
    builder.button(text="تنظیم Webhook Secret FrenzyEx", callback_data="set_frenzyex_callback_secret")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance", style="danger")
    builder.adjust(1)
    await safe_edit_message(callback, "🪙 **مدیریت متغیر درگاه ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.in_(["set_wallet_usdt", "set_wallet_gram", "set_memo_gram", "set_exchanger_gram", "set_frenzyex_api_key", "set_frenzyex_base_url", "set_frenzyex_callback_secret"]))
async def set_crypto_wallet_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set crypto wallet prompt."""
    if not is_admin(callback): return
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
    builder.button(text="🔙 لغو", callback_data="fin_crypto_wallets", style="danger")
    await safe_edit_message(callback, f"لطفا مقدار جدید برای `{key_name}` را ارسال کنید:{current_val_text}", reply_markup=builder.as_markup(), parse_mode="Markdown")

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
        
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="fin_crypto_wallets", style="danger")
    await message.answer(f"✅ تنظیمات با موفقیت ذخیره شد.", reply_markup=builder.as_markup())



import logging

# === ROUTER: PENDING RECEIPTS ===
@admin_finance_router.callback_query((F.data == 'fin_pending_receipts') | (F.data.startswith('fin_pending_page_')))
async def pending_receipts_menu(callback: types.CallbackQuery):
    """Handles pending receipts menu with pagination (max 10 receipts per page)."""
    if not is_admin(callback): return
    
    page = 0
    if callback.data.startswith("fin_pending_page_"):
        try:
            page = int(callback.data.replace("fin_pending_page_", "").strip())
        except ValueError:
            page = 0
    
    from database.db_manager import DB_PATH
    import aiosqlite
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram import types
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM payment_reports 
            WHERE status IN ('pending', 'pending_receipt')
            ORDER BY created_at ASC, id ASC
        """) as cursor:
            pending = await cursor.fetchall()
            
    builder = InlineKeyboardBuilder()
    
    if not pending:
        builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به مدیریت مالی", callback_data="admin_finance", style="danger"))
        empty_text = "💵 <b>رسیدهای تایید نشده</b>\n\nدر حال حاضر رسید تایید نشده‌ای وجود ندارد."
        if callback.message.photo:
            try:
                await callback.message.delete()
            except Exception:
                pass
            return await callback.message.answer(empty_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return await safe_edit_message(callback, empty_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
    PAGE_SIZE = 10
    total_items = len(pending)
    total_pages = (total_items - 1) // PAGE_SIZE + 1
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
        
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_items)
    page_items = pending[start_idx:end_idx]
    
    for p in page_items:
        builder.row(types.InlineKeyboardButton(text=f"🧾 فاکتور: {p['invoice_id']}", callback_data=f"view_receipt_{p['invoice_id']}_{page}"))
        
    # Navigation row if more than 1 page
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"fin_pending_page_{page - 1}"))
            
        nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page + 1} از {total_pages}", callback_data="fin_noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="بعدی ➡️", callback_data=f"fin_pending_page_{page + 1}"))
            
        builder.row(*nav_buttons)
        
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به مدیریت مالی", callback_data="admin_finance", style="danger"))
    
    list_text = (
        f"💵 <b>رسیدهای تایید نشده ({total_items} مورد)</b>\n"
        f"📄 صفحه {page + 1} از {total_pages}\n\n"
        f"<i>(مرتب‌شده از قدیمی‌ترین به جدیدترین)</i>\n"
        f"برای مشاهده مشخصات کامل هر رسید و تایید یا رد آن، روی شماره فاکتور کلیک کنید:"
    )
    
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await callback.message.answer(list_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await safe_edit_message(callback, list_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@admin_finance_router.callback_query(F.data == "fin_noop")
async def fin_noop_handler(callback: types.CallbackQuery):
    """Prevents loading spinner on noop/counter buttons."""
    try:
        await callback.answer()
    except Exception:
        pass


@admin_finance_router.callback_query(F.data.startswith("view_receipt_"))
async def view_pending_receipt_detail(callback: types.CallbackQuery):
    """Shows full receipt details exactly like the initial payment notification, with back button."""
    if not is_admin(callback): return
    
    raw_data = callback.data.replace("view_receipt_", "").strip()
    if "_" in raw_data:
        invoice_id, page_str = raw_data.rsplit("_", 1)
        try:
            page = int(page_str)
        except ValueError:
            invoice_id = raw_data
            page = 0
    else:
        invoice_id = raw_data
        page = 0
        
    from bot.routers.payment import build_receipt_notification_content
    
    caption_text, reply_markup, has_photo, stored_value = await build_receipt_notification_content(
        invoice_id=invoice_id,
        with_back_button=f"fin_pending_page_{page}"
    )
    
    if has_photo and stored_value:
        try:
            await callback.message.delete()
        except Exception:
            pass
        try:
            return await callback.message.answer_photo(
                photo=stored_value,
                caption=caption_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Could not send receipt photo: {e}. Falling back to text.")
            
    # Text fallback or non-photo receipt
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await callback.message.answer(
            text=caption_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
    await safe_edit_message(
        callback,
        caption_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

# === ROUTER: LIMITS MENU ===
@admin_finance_router.callback_query(F.data == 'fin_limits_menu')
async def limits_menu(callback: types.CallbackQuery, state: FSMContext = None):
    """Handles limits menu."""
    if not is_admin(callback): return
    if state:
        await state.clear()
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    gateways = [('شارژ کیف پول', 'wallet')]
    for name, code in gateways:
        builder.button(text=f"⬇️ حداقل {name}", callback_data=f"lim_min_{code}")
        builder.button(text=f"⬆️ حداکثر {name}", callback_data=f"lim_max_{code}")
        
    builder.button(text="🔙 بازگشت", callback_data="admin_finance", style="danger")
    builder.adjust(2)
    
    await safe_edit_message(callback, "📈 **تنظیم محدودیت‌های شارژ کیف پول**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_finance_router.callback_query(F.data.startswith('lim_'))
async def set_limit_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Handles set limit prompt."""
    if not is_admin(callback): return
    limit_type = callback.data.split('_')[1] # min or max
    gateway = callback.data.split('_')[2]
    
    await state.update_data(limit_type=limit_type, gateway=gateway)
    await state.set_state(AdminStates.waiting_for_min_max_limit)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="fin_limits_menu", style="danger")
    typ_str = "حداقل" if limit_type == 'min' else "حداکثر"
    await safe_edit_message(callback, f"📌 مبلغ {typ_str} برای درگاه {gateway} را ارسال کنید:", reply_markup=builder.as_markup())

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
        
    await state.clear()
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت محدودیت‌ها", callback_data="fin_limits_menu", style="danger")
    await message.answer("✅ محدودیت با موفقیت تنظیم شد.", reply_markup=builder.as_markup())


# === NEUTRAL BUTTONS HANDLER (PREVENTS "QUERY IS TOO OLD") ===
@admin_finance_router.callback_query(F.data.in_(["noop", "none"]))
async def handle_noop(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
