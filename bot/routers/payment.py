"""
This module corresponds to the 'bot/routers/payment.py' branch in the candy_architecture.md map.
It acts as the UNIFIED PAYMENT HANDLER, routing 'pay_*' callbacks triggered from checkout,
and integrating both online (FrenzyEx) and offline (USDT, GRAM) gateways.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uuid
import aiosqlite
import time
from database import db_manager
from utils.exchange import get_arz_usdt_rate, get_gram_irt_price

payment_router = Router()

class PaymentState(StatesGroup):
    """Class representing PaymentState."""
    waiting_for_txid = State()

# === ROUTER: UNIFIED PAYMENT HANDLER ===
@payment_router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery, state: FSMContext):
    """Handles process payment."""
    gateway_code = callback.data.split('_')[1] # e.g. 'usdt', 'gram', 'frenzyex'
    
    data = await state.get_data()
    if 'final_amount' not in data:
        return await callback.answer("⏳ زمان شما منقضی شده است. لطفا فرایند خرید یا شارژ را از ابتدا شروع کنید.", show_alert=True)
        
    amount = data['final_amount']
        
    # Fetch settings for api keys and gateway validation
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT key, value FROM settings') as cursor:
            settings_rows = await cursor.fetchall()
            legacy_settings = {row['key']: row['value'] for row in settings_rows}

    # Gateway early validation
    if gateway_code == 'frenzyex':
        frenzyex_api_key = legacy_settings.get('frenzyex_api_key', '')
        if not frenzyex_api_key:
            return await callback.answer("❌ درگاه پرداخت آنلاین پیکربندی نشده است.", show_alert=True)
            
    if gateway_code == 'usdt':
        arz_usdt_rate = await get_arz_usdt_rate()
        if arz_usdt_rate is None:
            return await callback.answer("خطا در دریافت قیمت لحظه ای تتر. لطفا مجددا تلاش کنید.", show_alert=True)
        usdprice = round(amount / arz_usdt_rate, 2)
        if usdprice < 1.0:
            return await callback.answer("❌ خطا: کمترین مبلغ برای پرداخت در این درگاه 1 دلار می باشد.", show_alert=True)

    if gateway_code == 'gram':
        gram_irt_price = await get_gram_irt_price()
        if gram_irt_price is None:
            return await callback.answer("خطا در دریافت قیمت لحظه ای گرام. لطفا مجددا تلاش کنید.", show_alert=True)
        gram_amount = round(amount / gram_irt_price, 2)
        if gram_amount < 0.1:
            return await callback.answer("❌ خطا: کمترین مبلغ برای پرداخت در این درگاه 0.1 گرام می باشد.", show_alert=True)

    invoice_id = str(uuid.uuid4())[:8].upper()
    
    # Generate Invoice in DB
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        # First save to standard invoices for products
        license_note = data.get('license_note', '')
        await db.execute('''
            INSERT INTO invoices (id, user_id, plan_id, days, gb, base_price, wallet_deduction, 
            discount_code, discount_deduction, gift_code, gift_deduction, final_amount, license_note, status, renew_license_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (invoice_id, callback.from_user.id, data.get('plan_id'), data.get('days'), data.get('gb'),
              data.get('base_price'), data.get('wallet_deduction'), data.get('discount_code'), 
              data.get('discount_amount', 0), data.get('gift_code'), data.get('gift_amount', 0), 
              amount, license_note, data.get('renew_license_id')))
              
        # Also create a legacy payment_report if offline
        if gateway_code in ['usdt', 'gram']:
            expires_at = int(time.time()) + (7200 if gateway_code == 'usdt' else 86400)
            method = f"{gateway_code} offline"
            try:
                await db.execute('''
                    INSERT INTO payment_reports (user_id, invoice_id, amount, payment_method, status)
                    VALUES (?, ?, ?, ?, 'pending')
                ''', (callback.from_user.id, invoice_id, amount, method))
            except aiosqlite.OperationalError:
                await db.execute('''
                    INSERT INTO payment_reports (id_user, id_order, time, price, payment_Status, Payment_Method, id_invoice, expires_at)
                    VALUES (?, ?, ?, ?, 'Unpaid', ?, ?, ?)
                ''', (callback.from_user.id, invoice_id, time.strftime('%Y/%m/%d %H:%M:%S'), amount, method, invoice_id, expires_at))

        await db.commit()
        
    # Store gateway_code in state so receipt handler knows which type
    await state.update_data(last_gateway=gateway_code)
    

    # 2. Handle USDT (Offline)
    if gateway_code == 'usdt':

        walletaddressusdt = legacy_settings.get('wallet_usdt', '')
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="کپی مقدار تتر", copy_text=types.CopyTextButton(text=str(usdprice))),
            types.InlineKeyboardButton(text="کپی آدرس", copy_text=types.CopyTextButton(text=str(walletaddressusdt)))
        )
        builder.row(
            types.InlineKeyboardButton(text="📎 ارسال رسید / TxID", callback_data=f"sendtxid_{invoice_id}_usdt")
        )
        
        text = (
            f"✅ فاکتور شما ایجاد شد\n\n"
            f"🛒 کد پیگیری: <code>{invoice_id}</code>\n"
            f"🌐 شبکه: BSC (BEP-20)\n"
            f"💵 نرخ هر واحد تتر: {arz_usdt_rate:,} تومان\n"
            f"💰 مقدار: <code>{usdprice}</code> USDT\n\n"
            f"📌 از دکمههای کپی زیر برای کپی مقدار تتر و آدرس کیف پول استفاده کنید، سپس واریز را انجام داده و رسید را ارسال کنید.\n\n"
            f"⚠️ هشدار: لطفاً دقت کنید که شبکه انتخابی شما حتماً BSC (BEP-20) باشد، در غیر این صورت ارز شما از دست خواهد رفت.\n"
            f"⚠️ این فاکتور تا ٢ ساعت معتبر است.\n"
            f"💡 <b>نکات مهم پیش از انتقال:</b>\n"
            f"لطفاً آدرس کیف پول مقصد و شبکه تتر را با دقت بررسی و وارد کنید. در صورت وارد کردن اشتباه آدرس، ارز شما از دست رفته و هرگز به دست ما نخواهد رسید. همچنین در صورت واریز از کیف صرافی (برداشت) هنگام خرید تتر مبلغ کارمزد برداشت صرافی را هم لحاظ کنید تا بتوانید دقیقاً مبلغ فاکتور را از صرافیتان به آدرس کیف پول ما انتقال دهید اگر هم از قبل در کیف صرافی تتر موجود دارید باید حداقل موجودیتان مبلغ فاکتور + کارمزد برداشت صرافیتان باشد\n"
            f"اگر از کیفپول شخصی، واریز را انجام میدهید دقت کنید در کیف پولتان به اندازه کارمزد شبکه BNB موجود داشته باشین تا بتوانید انتقال را انجام دهید و فاکتور تایید شود. در صورت دریافت مبلغ کمتر از مقدار درج شده در فاکتور، فاکتور شما تایید نخواهد شد اما با اینحال در صورتی که آدرس شبکه و نوع شبکه را درست وارد کرده باشید و مبلغ توسط ما دریافت شده باشد دارایی تان از دست نمی رود و کیف تان در ربات به اندازه مبلغ دریافتی شارژ میشود."
        )
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        return

    # 3. Handle GRAM (Offline)
    if gateway_code == 'gram':

        walletaddressgram = legacy_settings.get('wallet_gram', '')
        memo_gram = legacy_settings.get('memo_gram', '')
        exchanger_gram = legacy_settings.get('exchanger_gram', '')
        
        # Build keyboard
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="کپی مقدار گرام", copy_text=types.CopyTextButton(text=str(gram_amount))),
            types.InlineKeyboardButton(text="کپی آدرس", copy_text=types.CopyTextButton(text=str(walletaddressgram)))
        )
        
        row2 = [types.InlineKeyboardButton(text="کپی کامنت", copy_text=types.CopyTextButton(text=str(memo_gram)))]
        if exchanger_gram and exchanger_gram != "0" and exchanger_gram.startswith("http"):
            row2.append(types.InlineKeyboardButton(text="خرید از صرافی", web_app=types.WebAppInfo(url=exchanger_gram)))
        builder.row(*row2)

        builder.row(
            types.InlineKeyboardButton(text="📎 ارسال رسید / TxID", callback_data=f"sendtxid_{invoice_id}_gram")
        )

        text = (
            f"✅ فاکتور شما ایجاد شد\n\n"
            f"🛒 کد پیگیری: <code>{invoice_id}</code>\n"
            f"🌐 شبکه: TON OPEN NETWORK\n"
            f"💵 (تون)نرخ هر واحد گرام (GRAM): {gram_irt_price:,} تومان\n"
            f"💰 مقدار: <code>{gram_amount}</code> گرام (تون)\n"
            f"💳 آدرس ولت: <code>{walletaddressgram}</code>\n"
            f"📝 کامنت (Memo): <code>{memo_gram}</code>\n\n"
            f"💡 <b>راهنمای واریز امن:</b>\n"
            f"لطفاً آدرس کیف پول و <b>کامنت (Memo)</b> فوق را با دقت وارد نمایید. در صورت وارد کردن اشتباه آدرس یا کامنت، ارز شما از دست رفته و هرگز به دست ما نخواهد رسید.\n\n"
            f"🎁 <b>مزیت استفاده از صرافی اختصاصی:</b>\n"
            f"در صورت استفاده از <b>صرافی اختصاصی (دکمه زیر فاکتور)</b>، کارمزد انتقال برای شما <b>رایگان</b> خواهد بود و لازم است فقط مقدار گرام درج شده در فاکتور را خریداری کنید و در هنگام برداشت گرام از صرافی اختصاصی مقدار گرام درج شده در فاکتور را که خریداری کرده اید با آدرس کیف پول و کامنت درج شده در فاکتور را وارد کنید اگر صرافی کارمزد نشان داد نگران نباشید چون اعمال نخواهد شد.\n"
            f"اما چنانچه از صرافی دیگری اقدام میکنید هنگام خرید مقدار گرام فاکتور کارمزد شبکه تون را هم که معمولا 0.1 است را لحاظ کنید تا در هنگام برداشت گرام از صرافی بتوانید دقیقاً مبلغ فاکتور را از صرافیتان به آدرس کیف پول و کامنت (ممو) درج شده در فاکتور برداشت کنید.\n"
            f"اما اگر از کیفپول شخصی اقدام میکنید، لطفاً چک کنید مبلغ فاکتور+ کارمزد شبکه در کیف پولتان موجود باشد تا <b>دقیقا مبلغ فاکتور</b>  را برای آدرس کیف پول و کامنت (ممو) درج شده در فاکتور ارسال کنید در صورت دریافت مبلغ کمتر از مقدار درج شده در فاکتور، فاکتور شما تایید نخواهد شد اما با اینحال در صورتی که کامنت و آدرس کیف پول را صحیح وارد کرده باشید و مبلغ توسط ما دریافت شده باشد دارایی تان از دست نمی رود و کیف تان در ربات به اندازه مبلغ دریافتی شارژ میشود.\n\n"
            f"⚠️ این فاکتور تا ۲۴ ساعت معتبر است."
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        return

    # 4. Handle FrenzyEx (Online)
    if gateway_code == 'frenzyex':
        await state.clear()
        from payment.gateways import FrenzyExGateway
        
        frenzyex_base_url = legacy_settings.get('frenzyex_base_url', 'https://frenzy.fastsnap.info')
        gateway = FrenzyExGateway(api_key=frenzyex_api_key, base_url=frenzyex_base_url)
        
        from bot.config import WEBHOOK_DOMAIN
        callback_url = f"https://{WEBHOOK_DOMAIN}/ipn/frenzyex"
        
        # FrenzyExGateway expects (order_id, amount, callback_url)
        result = await gateway.create_payment(invoice_id, amount, callback_url)
        
        if result.get('success'):
            builder = InlineKeyboardBuilder()
            if result.get('payment_url_bot'):
                builder.row(types.InlineKeyboardButton(text="پرداخت در تلگرام 💳", url=result.get('payment_url_bot')))
            if result.get('payment_url_web'):
                builder.row(types.InlineKeyboardButton(text="صفحه پرداخت تحت وب 🌐", url=result.get('payment_url_web')))
                
            request_id = result.get('request_id')
            builder.row(types.InlineKeyboardButton(text="بررسی وضعیت پرداخت 🔄", callback_data=f"frenzyex_check_{invoice_id}_{request_id}"))
            builder.row(types.InlineKeyboardButton(text="انصراف ❌", callback_data=f"frenzyex_cancel_{invoice_id}_{request_id}"))
            
            # Store frenzy_request_id in payment_reports
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                try:
                    await db.execute("UPDATE payment_reports SET gateway_request_id = ? WHERE invoice_id = ?", (request_id, invoice_id))
                except:
                    pass
                await db.commit()
            
            await callback.message.edit_text(
                f"✅ فاکتور آنلاین شما ایجاد شد\n\n"
                f"🛒 کد پیگیری: `{invoice_id}`\n"
                f"💰 مبلغ قابل پرداخت: {amount:,} تومان\n\n"
                f"لطفاً از طریق دکمه‌های زیر پرداخت را انجام دهید:",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await callback.answer(f"❌ خطا در ایجاد فاکتور: {result.get('error', 'Unknown Error')}", show_alert=True)
        return

@payment_router.callback_query(F.data.startswith("frenzyex_check_"))
async def check_frenzyex_status(callback: types.CallbackQuery):
    """Checks frenzyex payment status manually."""
    parts = callback.data.split('_')
    invoice_id = parts[2]
    request_id = parts[3]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT key, value FROM settings WHERE key = "frenzyex_api_key" OR key = "frenzyex_base_url"') as cursor:
            settings_rows = await cursor.fetchall()
            settings = {row['key']: row['value'] for row in settings_rows}
            
    frenzyex_api_key = settings.get('frenzyex_api_key', '')
    frenzyex_base_url = settings.get('frenzyex_base_url', 'https://frenzy.fastsnap.info')
    
    if not frenzyex_api_key:
        return await callback.answer("API Key یافت نشد.", show_alert=True)
        
    from payment.gateways import FrenzyExGateway
    gateway = FrenzyExGateway(api_key=frenzyex_api_key, base_url=frenzyex_base_url)
    result = await gateway.get_payment_status(request_id)
    
    if result.get('success'):
        status = result.get('status')
        if status == 'paid':
            await callback.answer("پرداخت انجام شده است! در حال پردازش...", show_alert=True)
            from payment.confirm import PaymentConfirmationManager
            pcm = PaymentConfirmationManager(callback.bot)
            success = await pcm.confirm_paid(invoice_id, method="FrenzyEx")
            if success:
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.reply(f"فاکتور {invoice_id} با موفقیت تایید شد.")
        elif status == 'pending':
            await callback.answer("پرداخت هنوز انجام نشده است (pending).", show_alert=True)
        elif status == 'expired':
            await callback.answer("فاکتور منقضی شده است.", show_alert=True)
        elif status == 'canceled':
            await callback.answer("فاکتور لغو شده است.", show_alert=True)
        else:
            await callback.answer(f"وضعیت نامشخص: {status}", show_alert=True)
    else:
        await callback.answer(f"خطا در ارتباط با درگاه: {result.get('error')}", show_alert=True)

@payment_router.callback_query(F.data.startswith("frenzyex_cancel_"))
async def cancel_frenzyex_status(callback: types.CallbackQuery):
    """Cancels a frenzyex payment manually."""
    parts = callback.data.split('_')
    invoice_id = parts[2]
    request_id = parts[3]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT key, value FROM settings WHERE key = "frenzyex_api_key" OR key = "frenzyex_base_url"') as cursor:
            settings_rows = await cursor.fetchall()
            settings = {row['key']: row['value'] for row in settings_rows}
            
    frenzyex_api_key = settings.get('frenzyex_api_key', '')
    frenzyex_base_url = settings.get('frenzyex_base_url', 'https://frenzy.fastsnap.info')
    
    from payment.gateways import FrenzyExGateway
    gateway = FrenzyExGateway(api_key=frenzyex_api_key, base_url=frenzyex_base_url)
    
    await callback.message.edit_text("در حال لغو فاکتور...")
    success = await gateway.cancel_payment(request_id)
    if success:
        await callback.message.edit_text("فاکتور با موفقیت لغو شد.")
    else:
        await callback.message.edit_text("امکان لغو فاکتور وجود ندارد یا قبلا لغو شده است.")

@payment_router.callback_query(F.data.startswith("sendtxid_"))
async def prompt_txid(callback: types.CallbackQuery, state: FSMContext):
    """Handles prompt txid. Format: sendtxid_{invoice_id}_{gateway}"""
    parts = callback.data.split('_')
    invoice_id = parts[1]
    gateway = parts[2] if len(parts) > 2 else 'usdt'
    
    await state.update_data(txid_invoice_id=invoice_id, txid_gateway=gateway)
    await state.set_state(PaymentState.waiting_for_txid)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data="cancel_txid")
    
    prompt_text = (
        "📎 <b>ارسال رسید پرداخت</b>\n\n"
        "لطفاً <b>هش تراکنش (TxID)</b> یا <b>تصویر رسید</b> را ارسال کنید:\n\n"
        "🖼 <i>میتوانید اسکرین‌شات رسید کیف پول را ارسال کنید</i>\n"
        "🔢 <i>یا TxID (هش تراکنش) را به صورت متن paste کنید</i>"
    )
    
    await callback.answer()
    await callback.message.answer(
        prompt_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data == "cancel_txid")
async def cancel_txid(callback: types.CallbackQuery, state: FSMContext):
    """Handles cancel txid."""
    await state.clear()
    await callback.message.delete()
    await callback.answer("عملیات لغو شد.")

@payment_router.message(PaymentState.waiting_for_txid)
async def process_txid(message: types.Message, state: FSMContext):
    """Handles process txid — accepts both image and text."""
    has_photo = bool(message.photo)
    txid_text = message.text or message.caption or ''
    
    if not has_photo and not txid_text.strip():
        return await message.answer(
            "❌ لطفا تصویر رسید یا کد پیگیری / هش تراکنش را ارسال کنید.",
            parse_mode="HTML"
        )
        
    data = await state.get_data()
    invoice_id = data.get('txid_invoice_id')
    gateway = data.get('txid_gateway', 'usdt')
    
    # Store: for image receipts store the file_id in crypto_hash, text goes in crypto_hash too
    stored_value = message.photo[-1].file_id if has_photo else txid_text.strip()
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        # Try new schema column name first
        try:
            await db.execute('''
                UPDATE payment_reports 
                SET status = 'pending_receipt', crypto_hash = ? 
                WHERE invoice_id = ?
            ''', (stored_value, invoice_id))
        except aiosqlite.OperationalError:
            # Fallback for legacy schema
            await db.execute('''
                UPDATE payment_reports 
                SET payment_Status = 'pending_receipt'
                WHERE id_invoice = ?
            ''', (invoice_id,))
        await db.commit()
        
    await state.clear()
    await message.reply("✅ رسید شما جهت بررسی ثبت شد. پس از تایید مدیر، حساب شما شارژ خواهد شد.")
    
    # Forward receipt to admins with inline buttons
    from bot.config import ADMIN_IDS
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    admin_builder = InlineKeyboardBuilder()
    admin_builder.button(text="✅ تایید", callback_data=f"confirm_receipt_{invoice_id}")
    admin_builder.button(text="❌ رد", callback_data=f"reject_receipt_{invoice_id}")
    
    gateway_label = {'usdt': 'تتر (USDT)', 'gram': 'گرام (TON)'}.get(gateway, gateway)
    caption_text = (
        f"📩 <b>رسید جدید</b>\n\n"
        f"👤 کاربر: <code>{message.from_user.id}</code>\n"
        f"🛒 فاکتور: <code>{invoice_id}</code>\n"
        f"💳 درگاه: {gateway_label}\n"
        f"📝 {'تصویر رسید' if has_photo else 'متن/هش'}: {'' if has_photo else (message.text or message.caption or '-')}"
    )

    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                await message.bot.send_photo(
                    chat_id=admin_id,
                    photo=message.photo[-1].file_id,
                    caption=caption_text,
                    parse_mode="HTML",
                    reply_markup=admin_builder.as_markup()
                )
            else:
                await message.bot.send_message(
                    chat_id=admin_id, 
                    text=caption_text,
                    parse_mode="HTML",
                    reply_markup=admin_builder.as_markup()
                )
        except Exception:
            pass

# === ROUTER: ADMIN RECEIPT APPROVAL ===

@payment_router.callback_query(F.data.startswith("confirm_receipt_"))
async def admin_confirm_receipt(callback: types.CallbackQuery):
    """Handles admin confirm receipt."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.split('_')[2]
    
    # Check if already processed
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv or inv['status'] != 'pending':
        return await callback.answer("این فاکتور قبلا پردازش شده است.", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"⏳ در حال صدور لایسنس برای فاکتور {invoice_id}...")
    
    # Delegate to PaymentConfirmationManager
    from payment.confirm import PaymentConfirmationManager
    pcm = PaymentConfirmationManager(callback.bot)
    success = await pcm.confirm_paid(invoice_id, method="offline_receipt")
    
    if success:
        await callback.answer("✅ تایید شد.", show_alert=True)
    else:
        await callback.answer("❌ خطا در فرآیند تایید.", show_alert=True)

@payment_router.callback_query(F.data.startswith("reject_receipt_"))
async def admin_reject_receipt(callback: types.CallbackQuery, state: FSMContext):
    """Handles admin reject receipt."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.split('_')[2]
    
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Notify failure
    from payment.confirm import PaymentConfirmationManager
    pcm = PaymentConfirmationManager(callback.bot)
    await pcm.notify_failed(invoice_id, reason="رسید ارسالی مورد تایید مدیریت قرار نگرفت.")
    
    await callback.answer("❌ رسید رد شد.", show_alert=True)
    await callback.message.reply(f"فاکتور {invoice_id} رد شد.")

@payment_router.callback_query(F.data.startswith("retry_provision_"))
async def admin_retry_provision(callback: types.CallbackQuery):
    """Handles admin retry provision."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.split('_')[2]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv or inv['status'] != 'issue':
        return await callback.answer("فقط فاکتورهای دارای خطا قابل تلاش مجدد هستند.", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("در حال تلاش مجدد...")
    
    # Re-run provision and deliver
    from payment.confirm import PaymentConfirmationManager
    pcm = PaymentConfirmationManager(callback.bot)
    await pcm._provision_and_deliver(invoice_id, inv['user_id'], inv)
