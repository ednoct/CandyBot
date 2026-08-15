# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..states import CheckoutStates
from database import db_manager
import uuid

checkout_router = Router()

# === HELPER: GENERATE INVOICE ===
async def generate_invoice_text(plan_name, admin_description, days, gb, base_price, discount_code, discount_amount, gift_code, gift_amount, wallet_deduction, final_amount):
    text = "پیش پرداخت شما به شرح زیر است:\n"
    text += "خرید اشتراک جدید\nنوع اشتراک: لاینس کندی کانکت\n"
    text += f"سطح: {plan_name}\n\n"
    text += "اشتراک جدید شما به شرح زیر است:\n"
    text += f"حجم: {gb} گیگابایت\n"
    text += f"مدت: {days} روز\n\n"
    if admin_description:
        text += f"توضیحات ادمین:\n{admin_description}\n\n"
    text += f"مبلغ: {base_price:,} تومان\n"
    if wallet_deduction > 0:
        text += f"کسر از کیف پول: -{wallet_deduction:,} تومان\n"
    if discount_amount > 0:
        text += f"تخفیف (کد {discount_code}): -{discount_amount:,} تومان\n"
    if gift_amount > 0:
        text += f"هدیه (کد {gift_code}): -{gift_amount:,} تومان\n"
    text += f"------------------------\n"
    text += f"مبلغ نهایی قابل پرداخت: {final_amount:,} تومان\n"
    return text

# === ROUTER: START CALCULATOR ===
@checkout_router.callback_query(F.data.startswith('checkout_plan_'))
async def start_calculator(callback: types.CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split('_')[2])
    plan = await db_manager.get_plan(plan_id)
    if not plan:
         return await callback.answer("پلن یافت نشد.", show_alert=True)
         
    await state.update_data(
        plan_id=plan_id, 
        plan_price_day=plan['price_per_day'], 
        plan_price_gb=plan['price_per_gb'], 
        admin_description=plan['admin_description'],
        plan_name=plan['name']
    )
    
    await render_calculator(callback.message, state, plan_id)

async def render_calculator(message: types.Message, state: FSMContext, plan_id: int):
    data = await state.get_data()
    
    time_packages = await db_manager.get_time_packages(plan_id)
    traffic_packages = await db_manager.get_traffic_packages(plan_id)
    
    if not time_packages and not traffic_packages:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 برگشت", callback_data="main_menu")
        return await message.edit_text("متاسفانه هیچ بسته‌ای برای این پلن تعریف نشده است.", reply_markup=builder.as_markup())
        
    sel_time_id = data.get('time_id', time_packages[0]['id'] if time_packages else 0)
    sel_traffic_id = data.get('traffic_id', traffic_packages[0]['id'] if traffic_packages else 0)
    
    sel_days = 0
    sel_gb = 0
    for tp in time_packages:
        if tp['id'] == sel_time_id: sel_days = tp['days']
    for tp in traffic_packages:
        if tp['id'] == sel_traffic_id: sel_gb = tp['gb']
        
    # fallback if selected was deleted
    if time_packages and sel_days == 0:
        sel_time_id = time_packages[0]['id']
        sel_days = time_packages[0]['days']
    if traffic_packages and sel_gb == 0:
        sel_traffic_id = traffic_packages[0]['id']
        sel_gb = traffic_packages[0]['gb']
        
    await state.update_data(time_id=sel_time_id, days=sel_days, traffic_id=sel_traffic_id, gb=sel_gb)
    
    builder = InlineKeyboardBuilder()
    
    if time_packages:
        # Header Time
        builder.row(types.InlineKeyboardButton(text=f"زمان (روز) • هر روز {data['plan_price_day']:,} تومان 🕒", callback_data="none"))
        
        # Grid Time (max 3 per row)
        time_buttons = []
        for tp in time_packages:
            text = f"{tp['days']} روز" + (" ✅" if tp['id'] == sel_time_id else "")
            time_buttons.append(types.InlineKeyboardButton(text=text, callback_data=f"calc_time_{tp['id']}"))
        builder.row(*time_buttons, width=3)
        
        # Selected Time summary
        builder.row(types.InlineKeyboardButton(text=f"روز انتخاب شده: {sel_days} ✅", callback_data="none"))
        
    if traffic_packages:
        # Header Traffic
        builder.row(types.InlineKeyboardButton(text=f"حجم (گیگ) • هر گیگ {data['plan_price_gb']:,} تومان 🔋", callback_data="none"))
        
        # Grid Traffic
        traffic_buttons = []
        for tp in traffic_packages:
            text = f"{tp['gb']} گیگ" + (" ✅" if tp['id'] == sel_traffic_id else "")
            traffic_buttons.append(types.InlineKeyboardButton(text=text, callback_data=f"calc_traffic_{tp['id']}"))
        builder.row(*traffic_buttons, width=3)
        
        # Selected Traffic summary
        builder.row(types.InlineKeyboardButton(text=f"گیگ انتخاب شده: {sel_gb} ✅", callback_data="none"))
    
    # Payment Button
    base_price = (sel_days * data['plan_price_day']) + (sel_gb * data['plan_price_gb'])
    builder.row(types.InlineKeyboardButton(text=f"💸 پرداخت {base_price:,} تومان", callback_data="checkout_confirm"))
    
    # Back
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))
    
    text = f"خرید اشتراک جدید\nنوع اشتراک: V2Ray\nسطح: {data['plan_name']} 💎"
    
    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())

@checkout_router.callback_query(F.data.startswith('calc_time_'))
async def update_time(callback: types.CallbackQuery, state: FSMContext):
    time_id = int(callback.data.split('_')[2])
    await state.update_data(time_id=time_id)
    data = await state.get_data()
    await render_calculator(callback.message, state, data['plan_id'])

@checkout_router.callback_query(F.data.startswith('calc_traffic_'))
async def update_traffic(callback: types.CallbackQuery, state: FSMContext):
    traffic_id = int(callback.data.split('_')[2])
    await state.update_data(traffic_id=traffic_id)
    data = await state.get_data()
    await render_calculator(callback.message, state, data['plan_id'])

# === ROUTER: PRE-PAYMENT INVOICE ===
@checkout_router.callback_query(F.data == 'checkout_confirm')
async def show_pre_payment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await prepare_and_send_invoice(callback.message, callback.from_user.id, data, state)

async def prepare_and_send_invoice(message: types.Message, user_id: int, data: dict, state: FSMContext):
    # Base Values
    days = data['days']
    gb = data['gb']
    price_per_day = data['plan_price_day']
    price_per_gb = data['plan_price_gb']
    
    # User Profile
    user = await db_manager.get_user(user_id)
    wallet_balance = user['balance'] if user else 0
    
    # Modifiers
    discount_code = data.get('discount_code', None)
    discount_amount = data.get('discount_amount', 0)
    gift_code = data.get('gift_code', None)
    gift_amount = data.get('gift_amount', 0)
    
    # Step 1: Base Price
    base_price = (days * price_per_day) + (gb * price_per_gb)
    current_total = base_price
    
    # Step 2: Discount Code
    if discount_amount > 0:
        current_total -= discount_amount
        if current_total < 0: current_total = 0
        
    # Step 3: Gift Code
    if gift_amount > 0:
        current_total -= gift_amount
        if current_total < 0: current_total = 0
        
    # Step 4: Wallet Deduction
    wallet_deduction = 0
    if current_total > 0 and wallet_balance > 0:
        wallet_deduction = min(wallet_balance, current_total)
        current_total -= wallet_deduction
        
    final_amount = current_total
    
    # Update state with calculated final amounts for invoice creation later
    await state.update_data(
        base_price=base_price,
        wallet_deduction=wallet_deduction,
        final_amount=final_amount
    )
    
    text = await generate_invoice_text(
        data['plan_name'], 
        data['admin_description'], 
        days, 
        gb, 
        base_price, 
        discount_code, 
        discount_amount, 
        gift_code, 
        gift_amount, 
        wallet_deduction, 
        final_amount
    )
    
    builder = InlineKeyboardBuilder()
    
    # Modifiers
    if wallet_balance > 0:
        builder.row(types.InlineKeyboardButton(text="استفاده از کیف پول 💰", callback_data="none"))
        builder.row(types.InlineKeyboardButton(text=f"موجودی: ({wallet_balance:,}) تومان", callback_data="none"))
        
    builder.row(types.InlineKeyboardButton(text="🎫 ثبت کد تخفیف", callback_data="apply_discount"))
    builder.row(types.InlineKeyboardButton(text="🎁 ثبت کد هدیه", callback_data="apply_gift"))
    
    if final_amount > 0:
        # Show gateways
        import aiosqlite
        from database.db_manager import DB_PATH
        
        available_gateways = [
            ('کارت به کارت', 'cart', 'pay_card')
        ]
        
        async with aiosqlite.connect(DB_PATH) as db:
            for name, code, cb_data in available_gateways:
                async with db.execute("SELECT value FROM settings WHERE key = ?", (f"gateway_status_{code}",)) as cursor:
                    row = await cursor.fetchone()
                    # By default make cart and zarinpal active if not defined yet
                    is_active = (row and row[0] == '1') or (not row and code in ['cart', 'zarinpal'])
                    if is_active:
                        builder.row(types.InlineKeyboardButton(text=f"💳 {name}", callback_data=cb_data))
    else:
        builder.row(types.InlineKeyboardButton(text="✅ تکمیل خرید (رایگان)", callback_data="pay_free"))
        
    builder.row(types.InlineKeyboardButton(text="برگشت ⬅️", callback_data=f"checkout_plan_{data['plan_id']}"))
    
    if isinstance(message, types.Message):
        try:
            await message.edit_text(text, reply_markup=builder.as_markup())
        except AttributeError:
            await message.answer(text, reply_markup=builder.as_markup())

# === ROUTER: DISCOUNT CODE ===
@checkout_router.callback_query(F.data == "apply_discount")
async def ask_discount(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CheckoutStates.waiting_for_discount_code)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="cancel_modifier")
    await callback.message.edit_text("لطفا کد تخفیف خود را ارسال کنید:", reply_markup=builder.as_markup())

@checkout_router.message(CheckoutStates.waiting_for_discount_code)
async def process_discount(message: types.Message, state: FSMContext):
    code = message.text
    # validate code against db_manager
    discount = await db_manager.get_discount_code(code, message.from_user.id)
    if not discount or 'error' in discount:
        err_msg = discount['error'] if discount and 'error' in discount else "کد تخفیف نامعتبر است. مجددا تلاش کنید یا انصراف دهید."
        return await message.answer(f"❌ {err_msg}")
    
    data = await state.get_data()
    base_price = (data['days'] * data['plan_price_day']) + (data['gb'] * data['plan_price_gb'])
    
    amount = 0
    if discount['type'] == 'fixed':
        amount = discount['value']
    elif discount['type'] == 'percent':
        amount = int(base_price * (discount['value'] / 100))
        
    await state.update_data(discount_code=code, discount_amount=amount)
    await state.set_state(None)
    
    await message.answer("✅ کد تخفیف با موفقیت اعمال شد.")
    # Show pre-payment again
    await prepare_and_send_invoice(message, message.from_user.id, await state.get_data(), state)

# === ROUTER: GIFT CODE ===
@checkout_router.callback_query(F.data == "apply_gift")
async def ask_gift(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CheckoutStates.waiting_for_gift_code)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="cancel_modifier")
    await callback.message.edit_text("لطفا کد هدیه خود را ارسال کنید:", reply_markup=builder.as_markup())

@checkout_router.message(CheckoutStates.waiting_for_gift_code)
async def process_gift(message: types.Message, state: FSMContext):
    code = message.text
    gift = await db_manager.get_gift_code(code, message.from_user.id)
    if not gift or 'error' in gift:
        err_msg = gift['error'] if gift and 'error' in gift else "کد هدیه نامعتبر است."
        return await message.answer(f"❌ {err_msg}")
        
    await state.update_data(gift_code=code, gift_amount=gift['value'])
    await state.set_state(None)
    
    await message.answer("✅ کد هدیه با موفقیت اعمال شد.")
    await prepare_and_send_invoice(message, message.from_user.id, await state.get_data(), state)

# === ROUTER: CANCEL MODIFIER ===
@checkout_router.callback_query(F.data == "cancel_modifier")
async def cancel_modifier(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await prepare_and_send_invoice(callback.message, callback.from_user.id, await state.get_data(), state)

@checkout_router.callback_query(F.data == "pay_free")
async def pay_free(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice_id = str(uuid.uuid4())[:8].upper()
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('''
            INSERT INTO invoices (id, user_id, plan_id, days, gb, base_price, wallet_deduction, 
            discount_code, discount_deduction, gift_code, gift_deduction, final_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'paid')
        ''', (invoice_id, callback.from_user.id, data['plan_id'], data['days'], data['gb'],
              data['base_price'], data['wallet_deduction'], data.get('discount_code'), 
              data.get('discount_amount', 0), data.get('gift_code'), data.get('gift_amount', 0), 
              0))
        await db.commit()
        
    await state.clear()
    
    from payment.confirm import PaymentConfirmationManager
    from bot import bot
    pcm = PaymentConfirmationManager(bot)
    await pcm.confirm_paid(invoice_id, 0, 'free_discount')
    
    await callback.message.edit_text("✅ در حال تحویل لایسنس شما...")

# === ROUTER: FREE TEST ===
@checkout_router.callback_query(F.data == "free_test")
async def process_free_test(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM payment_reports WHERE user_id = ? AND payment_method = 'free_test'", (user_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            
        if count > 0:
            return await callback.answer("❌ شما قبلا از تست رایگان استفاده کرده‌اید.", show_alert=True)
            
        async with db.execute("SELECT id, license_key FROM licenses_cargo WHERE is_free_test = 1 LIMIT 1") as cursor:
            cargo = await cursor.fetchone()
            
        if not cargo:
            return await callback.answer("❌ متاسفانه در حال حاضر لایسنس تست رایگان موجود نیست.", show_alert=True)
            
        await db.execute("DELETE FROM licenses_cargo WHERE id = ?", (cargo[0],))
        
        await db.execute("INSERT INTO payment_reports (user_id, invoice_id, amount, payment_method, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 'TEST', 0, 'free_test', 'approved'))
        await db.commit()
        
    text = (
        f"🎁 **تست رایگان شما آماده است!**\n\n"
        f"لایسنس:\n`{cargo[1]}`\n\n"
        f"با آرزوی بهترین‌ها برای شما!"
    )


