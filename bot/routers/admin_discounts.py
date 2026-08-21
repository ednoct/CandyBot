"""
admin_discounts.py
------------------
Admin router for managing discount codes and gift codes.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_discounts_router = Router()

# ============================================================
# === ROUTER: MAIN DISCOUNTS MENU ===
# ============================================================

@admin_discounts_router.callback_query(F.data == "admin_discounts")
async def discounts_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return

    builder = InlineKeyboardBuilder()
    builder.button(text="🎫 مدیریت کدهای تخفیف", callback_data="manage_discounts")
    builder.button(text="🎁 مدیریت کدهای هدیه", callback_data="manage_gifts")
    builder.button(text="🔙 بازگشت", callback_data="admin_finance")
    builder.adjust(1)

    await callback.message.edit_text(
        "🎁 <b>مدیریت تخفیف و هدیه</b>\n\nلطفا یک بخش را انتخاب کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ============================================================
# === DISCOUNTS MANAGEMENT ===
# ============================================================

@admin_discounts_router.callback_query(F.data == "manage_discounts")
async def manage_discounts(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM discount_codes ORDER BY id DESC LIMIT 20") as cursor:
            codes = await cursor.fetchall()
            
    builder = InlineKeyboardBuilder()
    for code in codes:
        builder.button(text=f"❌ حذف {code['code']}", callback_data=f"del_discount_{code['id']}")
        
    builder.button(text="➕ افزودن کد تخفیف", callback_data="add_discount_start")
    builder.button(text="🔙 بازگشت", callback_data="admin_discounts")
    builder.adjust(1)
    
    text = "🎫 <b>لیست کدهای تخفیف (۲۰ مورد آخر)</b>\n\nبرای حذف روی کد مورد نظر کلیک کنید:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_discounts_router.callback_query(F.data.startswith("del_discount_"))
async def del_discount(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    did = int(callback.data.split("_")[2])
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("DELETE FROM discount_codes WHERE id = ?", (did,))
        await db.commit()
    await callback.answer("✅ کد تخفیف حذف شد.", show_alert=True)
    await manage_discounts(callback)

@admin_discounts_router.callback_query(F.data == "add_discount_start")
async def add_discount_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_admin_discount_code)
    await callback.message.edit_text("لطفا کد تخفیف مورد نظر را وارد کنید (مثلا SPRING1403):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_discount_code)
async def add_discount_code(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    await state.update_data(d_code=message.text.strip())
    await state.set_state(AdminStates.waiting_for_admin_discount_type)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="درصدی (%)", callback_data="dt_percent")
    builder.button(text="مبلغ ثابت (تومان)", callback_data="dt_fixed")
    
    await message.answer("نوع تخفیف را انتخاب کنید:", reply_markup=builder.as_markup())

@admin_discounts_router.callback_query(F.data.in_({"dt_percent", "dt_fixed"}))
async def add_discount_type(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    dtype = "percent" if callback.data == "dt_percent" else "fixed"
    await state.update_data(d_type=dtype)
    await state.set_state(AdminStates.waiting_for_admin_discount_value)
    
    unit = "درصد" if dtype == "percent" else "تومان"
    await callback.message.edit_text(f"مقدار تخفیف را به {unit} وارد کنید (فقط عدد):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_discount_value)
async def add_discount_value(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    await state.update_data(d_value=int(message.text))
    await state.set_state(AdminStates.waiting_for_admin_discount_max_uses)
    await message.answer("تعداد مجاز استفاده را وارد کنید (برای نامحدود عدد 0 را ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_discount_max_uses)
async def add_discount_max_uses(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    max_uses = int(message.text)
    await state.update_data(d_max_uses=None if max_uses == 0 else max_uses)
    await state.set_state(AdminStates.waiting_for_admin_discount_expiry)
    await message.answer("تعداد روزهای اعتبار این کد را وارد کنید (برای نامحدود 0 ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_discount_expiry)
async def add_discount_expiry(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    days = int(message.text)
    
    expiry = None
    if days > 0:
        import datetime
        expiry = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
    await state.update_data(d_expiry=expiry)
    await state.set_state(AdminStates.waiting_for_admin_discount_user_id)
    await message.answer("اگر این تخفیف اختصاصی است آیدی عددی کاربر را وارد کنید (برای عمومی بودن 0 ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_discount_user_id)
async def add_discount_save(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    uid = message.text.strip()
    if not uid.isdigit(): return await message.answer("لطفا آیدی عددی معتبر یا 0 وارد کنید.")
    
    user_id = None if uid == "0" else int(uid)
    data = await state.get_data()
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute(
            "INSERT INTO discount_codes (code, discount_type, discount_value, max_uses, used_count, expiration_date, user_id_restriction) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (data['d_code'], data['d_type'], data['d_value'], data['d_max_uses'], data['d_expiry'], user_id)
        )
        await db.commit()
        
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به مدیریت", callback_data="manage_discounts")
    await message.answer(f"✅ کد تخفیف {data['d_code']} با موفقیت ذخیره شد.", reply_markup=builder.as_markup())


# ============================================================
# === GIFTS MANAGEMENT ===
# ============================================================

@admin_discounts_router.callback_query(F.data == "manage_gifts")
async def manage_gifts(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM gift_codes ORDER BY id DESC LIMIT 20") as cursor:
            codes = await cursor.fetchall()
            
    builder = InlineKeyboardBuilder()
    for code in codes:
        builder.button(text=f"❌ حذف {code['code']}", callback_data=f"del_gift_{code['id']}")
        
    builder.button(text="➕ افزودن کد هدیه", callback_data="add_gift_start")
    builder.button(text="🔙 بازگشت", callback_data="admin_discounts")
    builder.adjust(1)
    
    text = "🎁 <b>لیست کدهای هدیه کیف پول (۲۰ مورد آخر)</b>\n\nبرای حذف روی کد مورد نظر کلیک کنید:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_discounts_router.callback_query(F.data.startswith("del_gift_"))
async def del_gift(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    did = int(callback.data.split("_")[2])
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("DELETE FROM gift_codes WHERE id = ?", (did,))
        await db.commit()
    await callback.answer("✅ کد هدیه حذف شد.", show_alert=True)
    await manage_gifts(callback)

@admin_discounts_router.callback_query(F.data == "add_gift_start")
async def add_gift_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_admin_gift_code)
    await callback.message.edit_text("لطفا کد هدیه مورد نظر را وارد کنید (مثلا GIFT100):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_gift_code)
async def add_gift_code(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    await state.update_data(g_code=message.text.strip())
    await state.set_state(AdminStates.waiting_for_admin_gift_value)
    await message.answer("مبلغ هدیه کیف پول را به تومان وارد کنید (فقط عدد):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_gift_value)
async def add_gift_value(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    await state.update_data(g_value=int(message.text))
    await state.set_state(AdminStates.waiting_for_admin_gift_max_uses)
    await message.answer("تعداد مجاز استفاده را وارد کنید (برای نامحدود 0 ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_gift_max_uses)
async def add_gift_max_uses(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    max_uses = int(message.text)
    await state.update_data(g_max_uses=None if max_uses == 0 else max_uses)
    await state.set_state(AdminStates.waiting_for_admin_gift_expiry)
    await message.answer("تعداد روزهای اعتبار این کد را وارد کنید (برای نامحدود 0 ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_gift_expiry)
async def add_gift_expiry(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    days = int(message.text)
    
    expiry = None
    if days > 0:
        import datetime
        expiry = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
    await state.update_data(g_expiry=expiry)
    await state.set_state(AdminStates.waiting_for_admin_gift_user_id)
    await message.answer("اگر این هدیه اختصاصی است آیدی عددی کاربر را وارد کنید (برای عمومی بودن 0 ارسال کنید):")

@admin_discounts_router.message(AdminStates.waiting_for_admin_gift_user_id)
async def add_gift_save(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    uid = message.text.strip()
    if not uid.isdigit(): return await message.answer("لطفا آیدی عددی معتبر یا 0 وارد کنید.")
    
    user_id = None if uid == "0" else int(uid)
    data = await state.get_data()
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute(
            "INSERT INTO gift_codes (code, amount, max_uses, used_count, expiration_date, user_id_restriction) VALUES (?, ?, ?, 0, ?, ?)",
            (data['g_code'], data['g_value'], data['g_max_uses'], data['g_expiry'], user_id)
        )
        await db.commit()
        
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به مدیریت", callback_data="manage_gifts")
    await message.answer(f"✅ کد هدیه {data['g_code']} با موفقیت ذخیره شد.", reply_markup=builder.as_markup())
