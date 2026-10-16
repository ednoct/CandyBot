"""
checkout.py
-----------
Module containing functionalities for checkout with Dynamic Tiered Pricing.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..states import CheckoutStates
from database import db_manager
import uuid

checkout_router = Router()

# ============================================================
# === TIERED PRICING ENGINE (موتور قیمت‌گذاری پلکانی هوشمند) ===
# ============================================================

# ساختار هر پلکان: (حداقل_گیگ, حداکثر_گیگ, درصد_تخفیف, عنوان_پلکان, ایموجی)
TRAFFIC_TIERS = [
    (1, 99, 0, "پلکان پایه (۱ تا ۹۹ گیگ)", "🔹"),
    (100, 199, 10, "پلکان نقره‌ای (۱۰۰ تا ۱۹۹ گیگ)", "🥈"),
    (200, 499, 18, "پلکان طلایی (۲۰۰ تا ۴۹۹ گیگ)", "🥇"),
    (500, 999999, 25, "پلکان الماس (۵۰۰ گیگ به بالا)", "💎"),
]

def calculate_tiered_gb_price(base_price_per_gb: int, selected_gb: int) -> dict:
    """
    محاسبه قیمت داینامیک هر گیگ، مبلغ کل ترافیک و سود کاربر بر اساس پلکان حجم انتخابی.
    """
    discount_percent = 0
    tier_name = TRAFFIC_TIERS[0][3]
    tier_emoji = TRAFFIC_TIERS[0][4]
    tier_index = 0
    next_tier_gb = None
    next_tier_discount = None
    next_tier_unit_price = None

    for i, (min_gb, max_gb, disc, name, emoji) in enumerate(TRAFFIC_TIERS):
        if min_gb <= selected_gb <= max_gb:
            discount_percent = disc
            tier_name = name
            tier_emoji = emoji
            tier_index = i
            if i + 1 < len(TRAFFIC_TIERS):
                next_tier_gb = TRAFFIC_TIERS[i + 1][0]
                next_tier_discount = TRAFFIC_TIERS[i + 1][2]
                next_tier_unit_price = int(round((base_price_per_gb * (100 - next_tier_discount) / 100) / 10.0) * 10)
            break

    # رند کردن به ضریب ۱۰ تومان برای حفظ زیبایی اعداد در تمام قیمت‌های پایه
    if discount_percent == 0:
        unit_price = base_price_per_gb
    else:
        unit_price = int(round((base_price_per_gb * (100 - discount_percent) / 100) / 10.0) * 10)

    total_traffic_price = selected_gb * unit_price
    original_traffic_price = selected_gb * base_price_per_gb
    saved_amount = original_traffic_price - total_traffic_price

    return {
        "unit_price": unit_price,
        "base_unit_price": base_price_per_gb,
        "discount_percent": discount_percent,
        "tier_name": tier_name,
        "tier_emoji": tier_emoji,
        "tier_index": tier_index,
        "total_traffic_price": total_traffic_price,
        "saved_amount": saved_amount,
        "next_tier_gb": next_tier_gb,
        "next_tier_discount": next_tier_discount,
        "next_tier_unit_price": next_tier_unit_price,
    }


# === HELPER: GENERATE INVOICE ===
async def generate_invoice_text(
    plan_name, admin_description, days, gb, base_price,
    discount_code, discount_amount, gift_code, gift_amount,
    wallet_deduction, final_amount, tier_info=None
):
    """Handles generate invoice text with tiered savings info."""
    text = "🧾 <b>پیش‌فاکتور رسمی شما به شرح زیر است:</b>\n\n"
    text += "خرید اشتراک جدید\nنوع اشتراک: لایسنس کندی کانکت\n"
    text += f"سطح سرویس: <b>{plan_name}</b>\n\n"
    text += "📦 <b>مشخصات اشتراک انتخابی:</b>\n"
    text += f"• حجم: <b>{gb} گیگابایت</b>\n"
    if tier_info:
        if tier_info['discount_percent'] > 0:
            text += (
                f"• تعرفه پلکانی: <b>هر گیگ {tier_info['unit_price']:,} تومان</b> "
                f"({tier_info['discount_percent']}٪ تخفیف پلکان حجمی 🔥)\n"
            )
        else:
            text += f"• تعرفه هر گیگ: <b>{tier_info['unit_price']:,} تومان</b>\n"
    text += f"• مدت زمان: <b>{days} روز</b>\n\n"
    
    if admin_description:
        text += f"📌 <b>توضیحات سرویس:</b>\n{admin_description}\n\n"
        
    if tier_info and tier_info['saved_amount'] > 0:
        text += f"🎉 <b>سود شما از خرید پلکانی: {tier_info['saved_amount']:,} تومان</b>\n"
        
    text += f"💰 مبلغ کل اشتراک: {base_price:,} تومان\n"
    if wallet_deduction > 0:
        text += f"👛 کسر از کیف پول: -{wallet_deduction:,} تومان\n"
    if discount_amount > 0:
        text += f"🎫 تخفیف (کد {discount_code}): -{discount_amount:,} تومان\n"
    if gift_amount > 0:
        text += f"🎁 هدیه (کد {gift_code}): -{gift_amount:,} تومان\n"
    text += "------------------------\n"
    text += f"💳 <b>مبلغ نهایی قابل پرداخت: {final_amount:,} تومان</b>\n"
    return text


# ============================================================
# === STEP 0: CONFIG NOTE PROMPT (before calculator) ===
# ============================================================

LICENSE_NOTE_TEXT = (
    "📝 <b>نام / یادداشت لایسنس</b>\n\n"
    "لطفاً یک نام برای لایسنس خود وارد کنید (مثلاً نام دستگاه یا شخص استفاده کننده).\n"
    "این نام به شما کمک می‌کند لایسنس‌های خود را راحت‌تر مدیریت کنید."
)

@checkout_router.callback_query(F.data.startswith('checkout_plan_'))
async def prompt_license_note(callback: types.CallbackQuery, state: FSMContext):
    """
    Intercept plan selection. Before showing the calculator, ask the user for
    a config note/remark (used as the 3x-UI client label and search identifier).
    """
    op_mode = await db_manager.get_operating_mode()
    if op_mode == "MAINTENANCE":
        return await callback.answer("ربات در حال بروزرسانی است. لطفاً بعداً تلاش کنید.", show_alert=True)
    elif op_mode == "SALES_PAUSED":
        return await callback.answer("فروش در حال حاضر متوقف شده است.", show_alert=True)
        
    plan_id = int(callback.data.split('_')[2])
    plan = await db_manager.get_plan(plan_id)
    if not plan:
        return await callback.answer("پلن یافت نشد.", show_alert=True)

    # Stash plan data for later use
    await state.update_data(
        plan_id=plan_id,
        plan_price_day=plan['price_per_day'],
        plan_price_gb=plan['price_per_gb'],
        admin_description=plan['admin_description'],
        plan_name=plan['name'],
        license_note=''  # default empty
    )
    await state.set_state(CheckoutStates.waiting_for_license_note)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="main_menu", style="danger")

    await callback.message.edit_text(
        LICENSE_NOTE_TEXT,
        reply_markup=builder.as_markup()
    )


@checkout_router.message(CheckoutStates.waiting_for_license_note)
async def save_license_note(message: types.Message, state: FSMContext):
    """User typed their license note. Save it and proceed to calculator."""
    note = (message.text or "").strip()[:100]  # cap at 100 chars
    
    # Validation for mandatory note
    if not note or len(note) < 2:
        return await message.answer("❌ نام/یادداشت لایسنس نباید خالی باشد. لطفاً یک نام معتبر وارد کنید:")
        
    await state.update_data(license_note=note)
    await state.set_state(None)

    data = await state.get_data()
    await render_calculator(message, state, data['plan_id'])


# ============================================================
# === ROUTER: DYNAMIC TIERED CALCULATOR ===
# ============================================================

def build_calculator_marketing_text(plan_name: str, base_gb_price: int, sel_gb: int, tier_info: dict) -> str:
    """
    تولید متن بازاریابی حرفه‌ای و جدول پلکان‌های داینامیک در بالای ماشین‌حساب
    """
    text = (
        "💎 <b>ماشین‌حساب هوشمند اشتراک</b>\n"
        f"<b>{plan_name}</b>\n"
        "⚡️ <i>قانون طلایی: حجم بیشتر = قیمت بسیار ارزان‌تر برای هر گیگ!</i>\n\n"
        f"📊 <b>جدول پلکان‌های تخفیف حجمی این سرویس:</b>\n"
    )

    for i, (min_gb, max_gb, disc, name, emoji) in enumerate(TRAFFIC_TIERS):
        if disc == 0:
            t_price = base_gb_price
            disc_str = "قیمت پایه"
        else:
            t_price = int(round((base_gb_price * (100 - disc) / 100) / 10.0) * 10)
            disc_str = f"<b>{disc}٪ تخفیف</b> 🔥"

        # مشخص کردن پلکانی که کاربر در حال حاضر روی آن قرار دارد
        is_active = (i == tier_info["tier_index"])
        active_badge = " 👈 <b>[پلکان فعلی شما ✅]</b>" if is_active else ""
        
        text += f"{emoji} {name}: گیگی <b>{t_price:,}</b> تومان ({disc_str}){active_badge}\n"

    text += "\n"

    # پیام‌های ترغیبی هوشمند (Psychological Nudges)
    if tier_info["saved_amount"] > 0:
        text += (
            f"🎉 <b>تبریک!</b> با انتخاب <b>{sel_gb} گیگ</b>، شما وارد "
            f"<b>{tier_info['tier_name']}</b> شدید و <b>{tier_info['saved_amount']:,} تومان</b> "
            f"کمتر پرداخت می‌کنید!\n"
        )
        if tier_info["next_tier_gb"]:
            text += (
                f"💡 <i>پیشنهاد ویژه: با انتخاب حداقل {tier_info['next_tier_gb']} گیگ، "
                f"تخفیف خود را به {tier_info['next_tier_discount']}٪ (گیگی {tier_info['next_tier_unit_price']:,} تومان) برسانید!</i>"
            )
    else:
        if tier_info["next_tier_gb"]:
            text += (
                f"💡 <b>پیشنهاد هوشمند:</b> شما در پلکان پایه هستید. "
                f"کافیست حجم را روی <b>{tier_info['next_tier_gb']} گیگ یا بالاتر</b> قرار دهید تا "
                f"قیمت هر گیگ فوراً به <b>{tier_info['next_tier_unit_price']:,} تومان ({tier_info['next_tier_discount']}٪ ارزان‌تر)</b> بشکند!"
            )

    return text


async def render_calculator(message: types.Message, state: FSMContext, plan_id: int):
    """Handles render calculator with dynamic tiered pricing."""
    data = await state.get_data()
    
    time_packages = await db_manager.get_time_packages(plan_id)
    traffic_packages = await db_manager.get_traffic_packages(plan_id)
    
    if not time_packages and not traffic_packages:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 برگشت", callback_data="main_menu", style="danger")
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

    # محاسبه قیمت داینامیک بر اساس پلکان حجم انتخابی
    tier_info = calculate_tiered_gb_price(data['plan_price_gb'], sel_gb)
    dynamic_gb_price = tier_info['unit_price']
        
    await state.update_data(
        time_id=sel_time_id,
        days=sel_days,
        traffic_id=sel_traffic_id,
        gb=sel_gb,
        effective_price_gb=dynamic_gb_price
    )
    
    builder = InlineKeyboardBuilder()
    
    if time_packages:
        # Header Time
        builder.row(types.InlineKeyboardButton(text=f"زمان (روز) • هر روز {data['plan_price_day']:,} تومان 🕒", callback_data="none", style="success"))
        
        # Grid Time (max 3 per row)
        time_buttons = []
        for tp in time_packages:
            text_btn = f"{tp['days']} روز" + (" ✅" if tp['id'] == sel_time_id else "")
            time_buttons.append(types.InlineKeyboardButton(text=text_btn, callback_data=f"calc_time_{tp['id']}"))
        builder.row(*time_buttons, width=3)
        
        # Selected Time summary
        builder.row(types.InlineKeyboardButton(text=f"روز انتخاب شده: {sel_days} ✅", callback_data="none", style="primary"))
        
    if traffic_packages:
        # Header Traffic (پویا و حساس به پلکان)
        if tier_info['discount_percent'] > 0:
            traffic_header_text = f"حجم • هر گیگ {dynamic_gb_price:,} تومان ({tier_info['discount_percent']}٪ تخفیف 🔥) ⚡"
        else:
            traffic_header_text = f"حجم (گیگ) • هر گیگ {dynamic_gb_price:,} تومان ⚡"
            
        builder.row(types.InlineKeyboardButton(text=traffic_header_text, callback_data="none", style="success"))
        
        # Grid Traffic
        traffic_buttons = []
        for tp in traffic_packages:
            # افزودن نشانگر کوچک برای بسته‌های دارای تخفیف پلکانی
            gb_val = tp['gb']
            is_selected = (tp['id'] == sel_traffic_id)
            btn_label = f"{gb_val} گیگ" + (" ✅" if is_selected else (" 🔥" if gb_val >= 100 else ""))
            traffic_buttons.append(types.InlineKeyboardButton(text=btn_label, callback_data=f"calc_traffic_{tp['id']}"))
        builder.row(*traffic_buttons, width=3)
        
        # Selected Traffic summary
        summary_gb_text = f"گیگ انتخاب شده: {sel_gb} ✅"
        if tier_info['saved_amount'] > 0:
            summary_gb_text += f" (سود شما: {tier_info['saved_amount']:,} ت)"
        builder.row(types.InlineKeyboardButton(text=summary_gb_text, callback_data="none", style="primary"))
    
    # Payment Button (محاسبه با قیمت پلکانی جدید)
    base_price = (sel_days * data['plan_price_day']) + tier_info['total_traffic_price']
    builder.row(types.InlineKeyboardButton(text=f"💸 پرداخت {base_price:,} تومان", callback_data="checkout_confirm"))
    
    # Back
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu", style="danger"))
    
    text = build_calculator_marketing_text(data['plan_name'], data['plan_price_gb'], sel_gb, tier_info)
    
    try:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err or "not modified" in err:
            return  # کاربر دوباره روی دکمه انتخابی کلیک کرد — نادیده بگیر
        try:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            pass

# === NEUTRAL BUTTONS HANDLER (PREVENTS "QUERY IS TOO OLD") ===
@checkout_router.callback_query(F.data.in_(["noop", "none"]))
async def handle_noop(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

@checkout_router.callback_query(F.data.startswith('calc_time_'))
async def update_time(callback: types.CallbackQuery, state: FSMContext):
    """Handles update time."""
    await callback.answer()
    time_id = int(callback.data.split('_')[2])
    await state.update_data(time_id=time_id)
    data = await state.get_data()
    await render_calculator(callback.message, state, data['plan_id'])

@checkout_router.callback_query(F.data.startswith('calc_traffic_'))
async def update_traffic(callback: types.CallbackQuery, state: FSMContext):
    """Handles update traffic."""
    await callback.answer()
    traffic_id = int(callback.data.split('_')[2])
    await state.update_data(traffic_id=traffic_id)
    data = await state.get_data()
    await render_calculator(callback.message, state, data['plan_id'])

# === ROUTER: PRE-PAYMENT INVOICE ===
@checkout_router.callback_query(F.data == 'checkout_confirm')
async def show_pre_payment(callback: types.CallbackQuery, state: FSMContext):
    """Handles show pre payment."""
    data = await state.get_data()
    await prepare_and_send_invoice(callback.message, callback.from_user.id, data, state)

async def prepare_and_send_invoice(message: types.Message, user_id: int, data: dict, state: FSMContext):
    """Handles prepare and send invoice with tiered calculation."""
    days = data['days']
    gb = data['gb']
    price_per_day = data['plan_price_day']
    base_price_per_gb = data['plan_price_gb']
    
    # محاسبه پلکانی برای فاکتور
    tier_info = calculate_tiered_gb_price(base_price_per_gb, gb)
    
    # User Profile
    user = await db_manager.get_user(user_id)
    wallet_balance = user['balance'] if user else 0
    
    # Modifiers
    discount_code = data.get('discount_code', None)
    discount_amount = data.get('discount_amount', 0)
    gift_code = data.get('gift_code', None)
    gift_amount = data.get('gift_amount', 0)
    
    # Step 1: Base Price (بر اساس قیمت پلکانی)
    base_price = (days * price_per_day) + tier_info['total_traffic_price']
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
        effective_price_gb=tier_info['unit_price'],
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
        final_amount,
        tier_info=tier_info
    )
    
    builder = InlineKeyboardBuilder()        
    builder.row(types.InlineKeyboardButton(text="🎫 ثبت کد تخفیف", callback_data="apply_discount"))
    builder.row(types.InlineKeyboardButton(text="🎁 ثبت کد هدیه", callback_data="apply_gift"))
    
    if final_amount > 0:
        # درگاه‌های فعال را از db_manager بخواهیم (no raw SQL in router)
        active_gateways = await db_manager.get_active_payment_gateways()
        for name, cb_data in active_gateways:
            if cb_data in ("pay_frenzyex", "frenzyex") or name == "کارت به کارت هوشمند":
                builder.row(types.InlineKeyboardButton(text=f"💳 {name}", callback_data=cb_data, style="success"))
            else:
                builder.row(types.InlineKeyboardButton(text=f"💳 {name}", callback_data=cb_data))
    else:
        builder.row(types.InlineKeyboardButton(text="✅ تکمیل خرید (رایگان)", callback_data="pay_free"))
        
    builder.row(types.InlineKeyboardButton(text="برگشت ⬅️", callback_data=f"checkout_plan_{data['plan_id']}", style="danger"))
    
    if isinstance(message, types.Message):
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err or "not modified" in err:
                return  # نادیده بگیر — محتوا تغییر نکرده
            # دکمه‌های اینلاین قابل ویرایش نیستند، پیام جدید ارسال شود
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# === ROUTER: DISCOUNT CODE ===
@checkout_router.callback_query(F.data == "apply_discount")
async def ask_discount(callback: types.CallbackQuery, state: FSMContext):
    """Handles ask discount."""
    await state.set_state(CheckoutStates.waiting_for_discount_code)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="cancel_modifier", style="danger")
    await callback.message.edit_text("لطفا کد تخفیف خود را ارسال کنید:", reply_markup=builder.as_markup())

@checkout_router.message(CheckoutStates.waiting_for_discount_code)
async def process_discount(message: types.Message, state: FSMContext):
    """Handles process discount."""
    code = message.text
    # validate code against db_manager
    discount = await db_manager.get_discount_code(code, message.from_user.id)
    if not discount or 'error' in discount:
        err_msg = discount['error'] if discount and 'error' in discount else "کد تخفیف نامعتبر است. مجددا تلاش کنید یا انصراف دهید."
        return await message.answer(f"❌ {err_msg}")
    
    data = await state.get_data()
    tier_info = calculate_tiered_gb_price(data['plan_price_gb'], data['gb'])
    base_price = (data['days'] * data['plan_price_day']) + tier_info['total_traffic_price']
    
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
    """Handles ask gift."""
    await state.set_state(CheckoutStates.waiting_for_gift_code)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="cancel_modifier", style="danger")
    await callback.message.edit_text("لطفا کد هدیه خود را ارسال کنید:", reply_markup=builder.as_markup())

@checkout_router.message(CheckoutStates.waiting_for_gift_code)
async def process_gift(message: types.Message, state: FSMContext):
    """Handles process gift."""
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
    """Handles cancel modifier."""
    await state.set_state(None)
    await prepare_and_send_invoice(callback.message, callback.from_user.id, await state.get_data(), state)

@checkout_router.callback_query(F.data == "pay_free")
async def pay_free(callback: types.CallbackQuery, state: FSMContext):
    """Handles zero-cost invoice creation and immediate license delivery."""
    data = await state.get_data()
    invoice_id = str(uuid.uuid4())[:8].upper()

    ok = await db_manager.create_free_invoice(
        invoice_id=invoice_id,
        user_id=callback.from_user.id,
        plan_id=data['plan_id'],
        days=data['days'],
        gb=data['gb'],
        base_price=data.get('base_price', 0),
        wallet_deduction=data.get('wallet_deduction', 0),
        discount_code=data.get('discount_code'),
        discount_amount=data.get('discount_amount', 0),
        gift_code=data.get('gift_code'),
        gift_amount=data.get('gift_amount', 0),
        license_note=data.get('license_note', ''),
        renew_license_id=data.get('renew_license_id'),
    )
    if not ok:
        return await callback.answer(
            "❌ موجودی کیف پول شما برای این پرداخت کافی نیست.",
            show_alert=True
        )

    await state.clear()
    from payment.confirm import PaymentConfirmationManager
    # callback.bot — متغیر bot از پکیج bot قابل import نیست
    pcm = PaymentConfirmationManager(callback.bot)
    await callback.message.edit_text("✅ در حال تحویل لایسنس شما...")
    await pcm.confirm_paid(invoice_id, 0, 'free_discount')

# NOTE: The old `free_test` handler has been permanently removed from this file.
# All free-trial logic now lives exclusively in bot/routers/user_free_trial.py
# (modern XUI-based provisioning via the free_trial_usage table).