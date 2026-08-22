"""
user.py
-------
Module containing functionalities for user.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
import aiosqlite
from database import db_manager
from utils.ui_helpers import apply_premium_emojis
from ..states import UserStates

user_router = Router()

# === HELPER: BUILD MAIN MENU ===
async def _build_main_menu(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """Builds the main menu message text and keyboard for a given user.
    
    Returns a (text, markup) tuple. The text has premium emoji tags applied;
    the keyboard buttons retain raw emoji strings (Telegram renders them
    client-side as Lottie animations automatically).
    """
    # Fetch user balance
    user = await db_manager.get_user(user_id)
    user_balance = f"{user['balance']:,}" if user else "0"

    # === MESSAGE TEXT (HTML, with premium emoji substitution) ===
    raw_text = (
        "<strong>به ربات کندی کانکت خوش آمدید!</strong>\n\n"
        f"💰 موجودی کیف پول شما <strong>{user_balance} تومان</strong>\n\n"
        "استفاده از ربات به منزله پذیرش شرایط و قوانین است."
    )
    message_text = apply_premium_emojis(raw_text)

    # === KEYBOARD LAYOUT ===
    # NOTE: Do NOT apply apply_premium_emojis() to button texts.
    # Telegram's Bot API rejects HTML in button labels. The client app
    # handles Lottie animation substitution for standard emojis automatically.
    builder = InlineKeyboardBuilder()

    # Row 1: Renewal | Purchase
    builder.row(
        types.InlineKeyboardButton(text="🌀 تمدید", callback_data="renewal", style="success"),
        types.InlineKeyboardButton(text="⭐ خرید لایسنس", callback_data="buy_subscription", style="success"),
    )
    # Row 2: Affiliate | Wallet
    builder.row(
        types.InlineKeyboardButton(text="🤝 همکاری در فروش", callback_data="affiliate", style="default"),
        types.InlineKeyboardButton(text="💰 کیف پول", callback_data="my_profile", style="default"),
    )
    # Row 3: My Subscriptions
    builder.row(
        types.InlineKeyboardButton(text="🔗 اشتراکهای من", callback_data="my_services", style="primary"),
    )
    # Row 4: News | FAQ
    builder.row(
        types.InlineKeyboardButton(text="📢 اخبار", url="https://t.me/CandyConnect"),
        types.InlineKeyboardButton(text="❓ مشکلات متداول", url="https://t.me/CandyConnectMistakes"),
    )
    # Row 5: Tutorials | Downloads
    builder.row(
        types.InlineKeyboardButton(text="❔ آموزش‌ها", url="https://t.me/CandyConnectHelp"),
        types.InlineKeyboardButton(text="📥 دانلودها", url="https://t.me/CandyConnectDownload"),
    )
    # Row 6: Support
    builder.row(
        types.InlineKeyboardButton(text="💬 پشتیبانی", callback_data="support", style="success"),
    )
    # Row 7: Free Trial
    builder.row(
        types.InlineKeyboardButton(text="🆓 تست رایگان", callback_data="free_test", style="primary"),
    )
    # Row 8: Terms & Conditions
    builder.row(
        types.InlineKeyboardButton(text="✍️ شرایط و قوانین", callback_data="terms", style="danger"),
    )

    return message_text, builder.as_markup()


# === ROUTER: START COMMAND ===
@user_router.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject = None):
    """Handles cmd start."""
    await state.clear()
    await db_manager.create_user(message.from_user.id, message.from_user.username)

    if command and command.args and command.args.startswith("ref_"):
        ref_code = command.args[4:]
        await db_manager.set_referred_by(message.from_user.id, ref_code)

    message_text, markup = await _build_main_menu(message.from_user.id)
    await message.answer(message_text, reply_markup=markup, parse_mode="HTML")

# === ROUTER: BUY SUBSCRIPTION ===
@user_router.callback_query(F.data == "buy_subscription")
async def show_plans(callback: types.CallbackQuery):
    """Handles show plans."""
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
    """Handles my profile."""
    user = await db_manager.get_user(callback.from_user.id)
    text = f"👤 پروفایل کاربری\n\nآیدی: {user['id']}\nموجودی کیف پول: {user['balance']:,} تومان"
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💰 شارژ حساب", callback_data="wallet_charge"))
    builder.row(types.InlineKeyboardButton(text="💳 تاریخچه کیف پول", callback_data="wallet_history"))
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@user_router.callback_query(F.data == "wallet_history")
async def show_wallet_history(callback: types.CallbackQuery):
    """Handles show wallet history."""
    import aiosqlite
    from database.db_manager import DB_PATH
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 15", 
            (callback.from_user.id,)
        ) as cur:
            txs = await cur.fetchall()
            
    if not txs:
        text = "شما هنوز هیچ تراکنشی در کیف پول خود ندارید."
    else:
        text = "💳 <b>تاریخچه کیف پول (۱۵ تراکنش آخر):</b>\n\n"
        for tx in txs:
            sign = "+" if tx['amount'] > 0 else ""
            reason = tx['reason'] or 'تراکنش'
            date_str = str(tx['created_at'])[:16]
            text += f"▪️ {sign}{tx['amount']:,} تومان | {reason} | <code>{date_str}</code>\n"
            
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به پروفایل", callback_data="my_profile")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# === ROUTER: MAIN MENU ===
@user_router.callback_query(F.data == "main_menu")
async def return_main_menu(callback: types.CallbackQuery):
    """Handles return main menu."""
    message_text, markup = await _build_main_menu(callback.from_user.id)
    await callback.message.edit_text(message_text, reply_markup=markup, parse_mode="HTML")


# === ROUTER: RENEWAL (redirect to my_services for selection) ===
@user_router.callback_query(F.data == "renewal")
async def renewal_start(callback: types.CallbackQuery):
    """Handles the renewal shortcut button — redirects user to their services list."""
    licenses = await db_manager.get_licenses_for_user(callback.from_user.id)

    if not licenses:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⭐ خرید لایسنس", callback_data="buy_subscription"))
        builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))
        return await callback.message.edit_text(
            "📦 <b>تمدید لایسنس</b>\n\n"
            "شما هنوز هیچ لایسنسی برای تمدید ندارید.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    builder = InlineKeyboardBuilder()
    for lic in licenses:
        note = lic['license_note'] or 'بدون یادداشت'
        builder.row(
            types.InlineKeyboardButton(text=f"♻️ تمدید | {note}", callback_data=f"renew_lic_{lic['id']}")
        )
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))

    await callback.message.edit_text(
        f"🌀 <b>تمدید لایسنس</b>\n\n"
        f"شما <b>{len(licenses)}</b> لایسنس دارید. جهت تمدید انتخاب کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# === ROUTER: TERMS & CONDITIONS ===
@user_router.callback_query(F.data == "terms")
async def show_terms(callback: types.CallbackQuery):
    """Handles display of terms & conditions."""
    text = (
        "📜 <b>شرایط و قوانین</b>\n\n"
        "١. استفاده از ربات به منزلهٔ پذیرش کامل این شرایط است. قوانین ممکن است در هر زمان به‌روزرسانی شوند و نسخهٔ همین صفحه ملاک است.\n\n"
        "٢. تمام پرداخت‌ها و بازگشت‌وجه‌ها فقط داخل ربات (کیف پول) انجام می‌شود؛ امکان برداشت وجه از ربات به کارت بانکی یا کیف پول ارز دیجیتال وجود ندارد.\n\n"
        "٣. اگر پرداختی انجام دادید و فاکتور تأیید نشد یا لایسنس را تحویل نگرفتید، لازم است حداکثر تا ۲۴ ساعت به پشتیبانی اطلاع دهید؛ پس از این مهلت، رسیدگی تضمین نمی‌شود.\n\n"
        "٤. لایسنس‌ها حکم مالکیت شما را دارد؛ در نگهداری آن دقت کنید. مسئولیت در اختیار گذاشتن لایسنس به دیگران بر عهدهٔ خود کاربر است.\n\n"
        "٥. اطلاعات حساب شما در اختیار هیچ کاربر دیگری قرار نمی‌گیرد. پشتیبانی نیز اشتراک یا موجودی را بین حساب‌ها جابه‌جا نمی‌کند — حتی با ادعای مالکیت، چون این ادعا قابل بررسی نیست. انتقال موجودی فقط توسط خود شما از طریق «انتقال وجه» در کیف پول امکان‌پذیر است.\n\n"
        "٦. از ارسال پیام‌های نامرتبط به پشتیبانی خودداری کنید.\n\n"
        "٧. در صورت عدم رعایت شرایط و قوانین، حساب کاربر مسدود می‌شود."
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === NEW HANDLERS FOR USER ROUTER ===
@user_router.callback_query(F.data == "my_services")
async def my_services(callback: types.CallbackQuery):
    """Handles my services."""
    user_id = callback.from_user.id
    licenses = await db_manager.get_licenses_for_user(user_id)

    if not licenses:
        builder = InlineKeyboardBuilder()
        builder.button(text="🛒 خرید اشتراک", callback_data="buy_subscription")
        builder.button(text="🔙 برگشت", callback_data="main_menu")
        builder.adjust(1)
        return await callback.message.edit_text(
            "📦 <b>لایسنس های من</b>\n\n"
            "شما هنوز هیچ لایسنسی ندارید.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    builder = InlineKeyboardBuilder()
    for lic in licenses:
        note = lic['license_note'] or 'بدون نام'
        builder.button(text=f"📦 {note}", callback_data=f"view_license_{lic['id']}")
        
    builder.adjust(2) # 2-column grid
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))

    await callback.message.edit_text(
        f"📦 <b>لایسنس های من</b>\n\n"
        f"شما <b>{len(licenses)}</b> لایسنس دارید. برای مشاهده جزئیات روی نام سرویس کلیک کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@user_router.callback_query(F.data.startswith("view_license_"))
async def view_license(callback: types.CallbackQuery):
    """Show full license details: QR code + sub_id copy button."""
    license_id = int(callback.data.split("_")[2])

    # Fetch the license — ensure it belongs to this user
    import aiosqlite
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT l.*, p.url as panel_url FROM xui_licenses l "
            "LEFT JOIN xui_panels p ON p.id = l.panel_id "
            "WHERE l.id = ? AND l.user_id = ?",
            (license_id, callback.from_user.id)
        ) as cursor:
            lic = await cursor.fetchone()

    if not lic:
        return await callback.answer("❌ لایسنس پیدا نشد.", show_alert=True)

    sub_id = lic['sub_id']
    note = lic['license_note'] or 'بدون یادداشت'
    note_line = f"\n📝 یادداشت لایسنس: <b>{note}</b>" if lic['license_note'] else ""

    # Fetch Live Status
    from bot.services.sub_stats import fetch_sub_stats
    live_status = "در حال دریافت وضعیت..."
    
    try:
        sub_link = lic['sub_link'] if 'sub_link' in lic.keys() else None # Need to make sure it's fetched
        if not sub_link:
            # Re-fetch panel sub_link if not explicitly joined in query
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT sub_link FROM xui_panels WHERE id = ?", (lic['panel_id'],)) as cur:
                    prow = await cur.fetchone()
                    if prow:
                        sub_link = prow['sub_link']

        if sub_link:
            stats = await fetch_sub_stats(sub_link, sub_id)
            if stats:
                if stats['is_unlimited_traffic']:
                    trf_text = f"مصرف شده: {stats['used_gb']:.2f} GB / نامحدود"
                else:
                    trf_text = f"ترافیک: {stats['used_gb']:.2f} / {stats['total_gb']:.2f} GB"
                    
                if stats['is_unlimited_time']:
                    exp_text = "اعتبار: نامحدود"
                else:
                    exp_text = f"اعتبار: {stats['days_left']:.1f} روز"
                    
                status_text = "🔴 پایان یافته / مسدود" if stats['is_expired'] else "🟢 فعال"
                live_status = f"\nوضعیت: {status_text}\n{trf_text}\n{exp_text}"
            else:
                live_status = "\nوضعیت: 🔴 نامشخص (خطا در دریافت اطلاعات ساب لینک)"
        else:
            live_status = "\nوضعیت: ⚠️ پنل فاقد ساب لینک است"
    except Exception as e:
        import logging
        logging.error(f"Error fetching live status for license {license_id}: {e}")
        live_status = "\nوضعیت: ⚠️ خطا در ارتباط با سرور"

    caption = (
        f"🔑 <b>جزئیات لایسنس</b>{note_line}\n"
        f"{live_status}\n\n"
        f"<code>{sub_id}</code>\n\n"
        "از دکمه زیر برای کپی کردن لایسنس استفاده کنید."
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📋 کپی لایسنس",
            copy_text=types.CopyTextButton(text=sub_id)
        )
    )
    builder.row(types.InlineKeyboardButton(text="♻️ تمدید", callback_data=f"renew_lic_{license_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به سرویس‌ها", callback_data="my_services"))

    # Try to send QR code as a new message with photo
    from bot.services.xui_client import generate_qr_bytes
    qr_buf = generate_qr_bytes(sub_id)

    try:
        if qr_buf is not None:
            # Can't edit a text message into a photo; send QR as new message
            await callback.message.answer_photo(
                photo=types.BufferedInputFile(qr_buf.read(), filename="license_qr.png"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            # Acknowledge callback
            await callback.answer()
        else:
            # Text-only fallback
            await callback.message.edit_text(caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        # Ultimate fallback
        await callback.message.edit_text(caption, reply_markup=builder.as_markup(), parse_mode="HTML")


@user_router.callback_query(F.data.startswith("renew_lic_"))
async def renew_license_start(callback: types.CallbackQuery, state: FSMContext):
    """Start renewal flow for an existing license."""
    license_id = int(callback.data.split("_")[2])
    # Set the state to remember we are renewing this license
    await state.update_data(renew_license_id=license_id)
    
    # Redirect to the shop to pick a plan
    from bot.routers.user import cmd_shop
    # Re-route the callback to the shop command
    callback.data = "buy_subscription"
    await cmd_shop(callback.message, state, callback)


@user_router.callback_query(F.data == "affiliate")
async def affiliate_dashboard(callback: types.CallbackQuery):
    """Handles affiliate dashboard."""
    user_id = callback.from_user.id
    ref_code = await db_manager.get_or_create_referral_code(user_id)
    stats = await db_manager.get_referral_stats(user_id)
    bot_info = await callback.bot.me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{ref_code}"
    
    text = (
        f"👥 <b>سیستم زیرمجموعه گیری (بازاریابی)</b>\n\n"
        f"با دعوت دوستان خود، درصدی از مبلغ خرید آنها را به عنوان پورسانت دریافت کنید!\n\n"
        f"📊 <b>آمار شما:</b>\n"
        f"تعداد دعوت شده‌ها: {stats['invited']} نفر\n"
        f"تعداد خریداران: {stats['buyers']} نفر\n"
        f"کل پورسانت دریافتی: {stats['earned']:,} تومان\n\n"
        f"🔗 <b>لینک اختصاصی شما:</b>\n<code>{ref_link}</code>"
    )
    
    builder = InlineKeyboardBuilder()
    share_url = f"https://t.me/share/url?url={ref_link}&text=برای خرید بهترین کانفیگ ها به این ربات سر بزن!"
    builder.row(types.InlineKeyboardButton(text="📤 ارسال به دوستان", url=share_url))
    builder.row(types.InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@user_router.callback_query(F.data == "wallet_charge")
async def wallet_charge_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles wallet charge start."""
    await state.set_state(UserStates.waiting_for_charge_amount)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="my_profile")
    await callback.message.edit_text("💰 لطفاً مبلغ مورد نظر برای شارژ کیف پول را به تومان وارد کنید (مثلاً 50000):", reply_markup=builder.as_markup())

@user_router.message(UserStates.waiting_for_charge_amount)
async def process_wallet_charge(message: types.Message, state: FSMContext):
    """Handles process wallet charge."""
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
        ('کارت به کارت هوشمند', 'frenzyex', 'pay_frenzyex')
    ]
    
    async with aiosqlite.connect(DB_PATH) as db:
        for name, code, cb_data in available_gateways:
            key_name = f"{code}_status" if code in ['frenzyex', 'usdt', 'gram'] else f"gateway_status_{code}"
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key_name,)) as cursor:
                row = await cursor.fetchone()
                is_active = (row and row[0] == '1')
                if is_active:
                    builder.row(types.InlineKeyboardButton(text=f"💳 {name}", callback_data=cb_data))
                    
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="my_profile"))
    
    from bot.config import ADMIN_IDS
    if message.from_user.id in ADMIN_IDS:
        builder.row(types.InlineKeyboardButton(text="⚙️ ورود به مدیریت", callback_data="admin_panel_start"))
    
    await message.answer(f"💰 مبلغ {amount:,} تومان جهت شارژ تایید شد.\nلطفاً یک روش پرداخت انتخاب کنید:", reply_markup=builder.as_markup())


# === ROUTER: ACQUISITION & FEEDBACK ===

@user_router.callback_query(F.data.startswith("acq_"))
async def handle_acquisition_survey(callback: types.CallbackQuery):
    """Handles handle acquisition survey."""
    source_map = {
        "acq_friends": "معرفی دوستان",
        "acq_telegram": "تلگرام",
        "acq_instagram": "اینستاگرام",
        "acq_other": "سایر"
    }
    source = source_map.get(callback.data)
    if source:
        await db_manager.save_acquisition_source(callback.from_user.id, source)
        await callback.message.edit_text(f"از نظرسنجی شما متشکریم! ({source})")
        
@user_router.callback_query(F.data.startswith("fb_rate_"))
async def handle_feedback_rating(callback: types.CallbackQuery, state: FSMContext):
    """Handles handle feedback rating."""
    parts = callback.data.split("_")
    invoice_id = parts[2]
    rating = int(parts[3])
    
    await db_manager.save_feedback(invoice_id, callback.from_user.id, rating, "")
    await callback.message.edit_reply_markup(reply_markup=None)
    
    if rating <= 3:
        await state.update_data(fb_invoice_id=invoice_id)
        await state.set_state(UserStates.waiting_for_feedback_comment)
        await callback.message.reply("متاسفیم که رضایت کامل نداشتید. لطفاً دلیل نارضایتی یا پیشنهاد خود را برای ما بنویسید:")
    else:
        await callback.message.edit_text(f"شما امتیاز {rating} ستاره دادید. از ثبت نظر شما سپاسگزاریم! 💖")

@user_router.message(UserStates.waiting_for_feedback_comment)
async def handle_feedback_comment(message: types.Message, state: FSMContext):
    """Handles handle feedback comment."""
    data = await state.get_data()
    invoice_id = data.get('fb_invoice_id')
    if invoice_id:
        import aiosqlite
        from database.db_manager import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE customer_feedback SET comment = ? WHERE invoice_id = ?", (message.text, invoice_id))
            await db.commit()
            
    await state.clear()
    await message.reply("نظر شما ثبت شد. با تشکر از همراهی شما! 🌺")
