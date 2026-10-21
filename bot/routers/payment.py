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
import datetime
import re
from urllib.parse import urlparse
from utils.date_formatter import get_jalali_date, get_current_jalali
from utils.exchange import get_arz_usdt_rate, get_gram_irt_price

payment_router = Router()

class PaymentState(StatesGroup):
    """Class representing PaymentState."""
    waiting_for_txid = State()
    waiting_for_pingi_receipt = State()
    waiting_for_txid_string = State()
    waiting_for_appeal = State()

class AdminRejectState(StatesGroup):
    """FSM states for Admin Rejection workflow."""
    waiting_for_reason = State()

def extract_tx_hash(input_text: str) -> str:
    """Extracts pure transaction hash from raw text or explorer URL."""
    if not input_text or not isinstance(input_text, str):
        return ""
    text = input_text.strip()
    if "/" in text:
        clean = text.split("?")[0].split("#")[0].rstrip("/")
        parts = [p.strip() for p in clean.split("/") if p.strip()]
        if parts:
            return parts[-1]
    return text.strip()

def format_date_to_jalali(dt_val) -> str:
    """Converts a timestamp or datetime string to formatted Jalali date string."""
    if not dt_val:
        return get_current_jalali()
    if isinstance(dt_val, (int, float)):
        return get_jalali_date(int(dt_val))
    if isinstance(dt_val, datetime.datetime):
        return get_jalali_date(int(dt_val.timestamp()))
    dt_str = str(dt_val).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
        try:
            d = datetime.datetime.strptime(dt_str, fmt)
            return get_jalali_date(int(d.timestamp()))
        except ValueError:
            pass
    return dt_str

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

    crypto_amount = None
    crypto_rate = None
    if gateway_code == 'usdt':
        crypto_amount = usdprice
        crypto_rate = arz_usdt_rate
    elif gateway_code == 'gram':
        crypto_amount = gram_amount
        crypto_rate = gram_irt_price

    invoice_id = str(uuid.uuid4())[:8].upper()
    
    # Generate Invoice in DB
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        # First save to standard invoices for products
        license_note = data.get('license_note', '')
        await db.execute('''
            INSERT INTO invoices (id, user_id, plan_id, days, gb, base_price, wallet_deduction, 
            discount_code, discount_deduction, gift_code, gift_deduction, final_amount, license_note, status, renew_license_id, renew_mode, payment_method, crypto_amount, crypto_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
        ''', (invoice_id, callback.from_user.id, data.get('plan_id'), data.get('days'), data.get('gb'),
              data.get('base_price'), data.get('wallet_deduction'), data.get('discount_code'), 
              data.get('discount_amount', 0), data.get('gift_code'), data.get('gift_amount', 0), 
              amount, license_note, data.get('renew_license_id'), data.get('renew_mode'), gateway_code,
              crypto_amount, crypto_rate))
              
        # Also create a legacy payment_report if offline
        if gateway_code in ['usdt', 'gram']:
            expires_at = int(time.time()) + 86400  # 24 hours for both USDT and GRAM
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
            types.InlineKeyboardButton(text="📢 آموزش پیدا کردن هش رسید", url="https://t.me/CandyConnectHelp/4", style="primary"),
        )
        builder.row(
            types.InlineKeyboardButton(text="💳 ارسال هش رسید (TXID / Hash)", callback_data=f"sendtxid_{invoice_id}_usdt", style="success")
        )
        
        text = (
            f"✅ فاکتور شما ایجاد شد\n\n"
            f"🛒 کد پیگیری: <code>{invoice_id}</code>\n"
            f"🌐 شبکه: BSC (BEP-20)\n"
            f"💵 نرخ هر واحد تتر: {arz_usdt_rate:,} تومان\n"
            f"💰 مقدار: <code>{usdprice}</code> USDT\n\n"
            f"📌 از دکمههای کپی زیر برای کپی مقدار تتر و آدرس کیف پول استفاده کنید، سپس واریز را انجام داده و رسید را ارسال کنید.\n\n"
            f"⚠️ هشدار: لطفاً دقت کنید که شبکه انتخابی شما حتماً BSC (BEP-20) باشد، در غیر این صورت ارز شما از دست خواهد رفت.\n"
            f"⚠️ این فاکتور تا ٢٤ ساعت معتبر است.\n"
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
            row2.append(types.InlineKeyboardButton(text="صرافی بدون کارمزد", web_app=types.WebAppInfo(url=exchanger_gram)), style="danger")
        builder.row(*row2)
        builder.row(
            types.InlineKeyboardButton(text="📢 آموزش پیدا کردن هش رسید", url="https://t.me/CandyConnectHelp/4", style="primary"),
        )
        builder.row(
            types.InlineKeyboardButton(text="💳 ارسال هش رسید (TXID / Hash)", callback_data=f"sendtxid_{invoice_id}_gram", style="success")
        )

        text = (
            f"✅ فاکتور شما ایجاد شد\n\n"
            f"🛒 کد پیگیری: <code>{invoice_id}</code>\n"
            f"🌐 شبکه: TON OPEN NETWORK\n"
            f"💵 نرخ هر واحد گرام (GRAM): {gram_irt_price:,} تومان\n"
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
            builder.row(types.InlineKeyboardButton(text="انصراف ❌", callback_data=f"frenzyex_cancel_{invoice_id}_{request_id}", style="danger"))
            
            # Store frenzy_request_id in payment_reports
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                try:
                    await db.execute('''
                        INSERT INTO payment_reports (user_id, invoice_id, amount, payment_method, status, gateway_request_id)
                        VALUES (?, ?, ?, 'frenzyex', 'pending', ?)
                    ''', (callback.from_user.id, invoice_id, amount, request_id))
                except Exception:
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

@payment_router.callback_query(
    F.data.startswith("frenzyex_cancel_") | F.data.startswith("cancel_frenzyex_")
)
async def cancel_frenzyex_status(callback: types.CallbackQuery):
    """
    Cancels an unpaid FrenzyEx payment request safely.
    Fixes BUG-04:
    1. Matches both 'frenzyex_cancel_' and 'cancel_frenzyex_' callback prefixes.
    2. Accurately resolves invoice_id and gateway_request_id even when f"{invoice_id}_{request_id}"
       is passed and either ID contains underscores.
    3. Checks cancel_res.get('success') and handles HTTP 409 Conflict properly.
    """
    raw_cb = callback.data or ""
    if raw_cb.startswith("frenzyex_cancel_"):
        rem = raw_cb[len("frenzyex_cancel_"):].strip()
    elif raw_cb.startswith("cancel_frenzyex_"):
        rem = raw_cb[len("cancel_frenzyex_"):].strip()
    else:
        await callback.answer("❌ شناسه درخواست نامعتبر است.", show_alert=True)
        return

    if not rem:
        await callback.answer("❌ شناسه درخواست نامعتبر است.", show_alert=True)
        return

    pr_row = None
    inv_row = None

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout = 5000;")
        db.row_factory = aiosqlite.Row

        # 1. Try direct exact match on invoice_id or gateway_request_id, or composite match
        async with db.execute(
            """
            SELECT invoice_id, gateway_request_id, status
            FROM payment_reports
            WHERE invoice_id = ?
               OR gateway_request_id = ?
               OR (invoice_id || '_' || COALESCE(gateway_request_id, '')) = ?
            ORDER BY id DESC LIMIT 1
            """,
            (rem, rem, rem),
        ) as cur:
            pr_row = await cur.fetchone()

        # 2. If not found and `rem` contains '_', try splitting at every underscore boundary
        if not pr_row and "_" in rem:
            parts = rem.split("_")
            for idx in range(1, len(parts)):
                cand_inv = "_".join(parts[:idx])
                cand_req = "_".join(parts[idx:])
                async with db.execute(
                    """
                    SELECT invoice_id, gateway_request_id, status
                    FROM payment_reports
                    WHERE invoice_id = ? OR gateway_request_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (cand_inv, cand_req),
                ) as cur:
                    pr_row = await cur.fetchone()
                    if pr_row:
                        break
                async with db.execute("SELECT * FROM invoices WHERE id = ?", (cand_inv,)) as icur:
                    inv_row = await icur.fetchone()
                    if inv_row:
                        break

    if pr_row:
        invoice_id = str(pr_row["invoice_id"]).strip()
        request_id = str(pr_row["gateway_request_id"] or "").strip()
    elif inv_row:
        invoice_id = str(inv_row["id"]).strip()
        request_id = rem[len(invoice_id) + 1:].strip() if rem.startswith(f"{invoice_id}_") else ""
    else:
        # Final fallback: split on first underscore if present
        if "_" in rem:
            invoice_id, request_id = rem.split("_", 1)
        else:
            invoice_id, request_id = rem, ""

    inv = inv_row or await db_manager.get_invoice_by_id(invoice_id)
    if inv and inv["status"] in ("paid", "approved", "processing", "completed"):
        await callback.answer("✅ این فاکتور قبلاً پرداخت و تایید شده است و قابل لغو نیست.", show_alert=True)
        return

    api_key = (await db_manager.get_setting("frenzyex_api_key", "")).strip()
    base_url = (await db_manager.get_setting("frenzyex_base_url", "https://frenzy.fastsnap.info")).strip()

    if api_key and request_id:
        from payment.gateways import FrenzyExGateway
        gateway = FrenzyExGateway(api_key=api_key, base_url=base_url)
        cancel_res = await gateway.cancel_payment(request_id)

        if not cancel_res.get("success"):
            remote_status = cancel_res.get("status")
            if remote_status == "paid":
                from payment.confirm import PaymentConfirmationManager
                pcm = PaymentConfirmationManager(callback.bot)
                await pcm.confirm_paid(invoice_id, method="FrenzyEx Cancel-Check")
                await callback.answer("✅ پرداخت شما در درگاه انجام شده است! سرویس در حال فعال‌سازی است.", show_alert=True)
                return

            if cancel_res.get("conflict"):
                await callback.answer(
                    "⏳ این تراکنش در درگاه در حال بررسی است و در حال حاضر امکان لغو آن وجود ندارد.",
                    show_alert=True,
                )
                return

            if remote_status not in ("expired", "canceled"):
                await callback.answer(
                    "⚠️ خطا در لغو تراکنش در سمت درگاه. لطفاً چند لحظه دیگر مجدداً تلاش کنید.",
                    show_alert=True,
                )
                return

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout = 5000;")
        await db.execute(
            "UPDATE invoices SET status = 'canceled' WHERE id = ? AND status = 'pending'",
            (invoice_id,),
        )
        await db.execute(
            "UPDATE payment_reports SET status = 'canceled' WHERE invoice_id = ? AND status IN ('pending', 'Unpaid')",
            (invoice_id,),
        )
        await db.commit()

    try:
        await callback.message.edit_text(
            f"❌ <b>فاکتور شماره <code>{invoice_id}</code> با موفقیت لغو شد.</b>",
            parse_mode="HTML",
        )
    except Exception:
        await callback.answer("❌ فاکتور با موفقیت لغو شد.", show_alert=True)

@payment_router.callback_query(F.data.startswith("sendtxid_"))
async def prompt_txid(callback: types.CallbackQuery, state: FSMContext):
    """Handles prompt txid. Format: sendtxid_{invoice_id}_{gateway}"""
    parts = callback.data.split('_')
    invoice_id = parts[1]
    gateway = parts[2] if len(parts) > 2 else 'usdt'
    
    # Check if invoice is already expired or processed
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv or inv['status'] != 'pending':
        return await callback.answer("⏳ این فاکتور منقضی شده یا قبلاً پردازش شده است.", show_alert=True)

    # 1. GRAM Gateway: Show Pingi vs Personal Wallet/Other selection
    if gateway == 'gram':
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="انتقال از صرافی پینگی", callback_data=f"gram_method_pingi_{invoice_id}")
        )
        builder.row(
            types.InlineKeyboardButton(text="انتقال از کیف پول شخصی یا صرافی های دیگر", callback_data=f"gram_method_wallet_{invoice_id}")
        )
        builder.row(
            types.InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_txid", style="danger")
        )
        
        prompt_text = (
            "🧾 <b>انتخاب روش انتقال گرام:</b>\n\n"
            "لطفاً روشی را که از طریق آن واریز گرام را انجام داده‌اید انتخاب کنید:"
        )
        
        await callback.answer()
        await callback.message.answer(
            prompt_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    # 2. USDT Gateway: Immediately prompt for TXID string only
    await state.update_data(txid_invoice_id=invoice_id, txid_gateway='usdt', transfer_method='wallet_or_other')
    await state.set_state(PaymentState.waiting_for_txid_string)
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("UPDATE invoices SET transfer_method = 'wallet_or_other' WHERE id = ?", (invoice_id,))
        try:
            await db.execute("UPDATE payment_reports SET transfer_method = 'wallet_or_other' WHERE invoice_id = ?", (invoice_id,))
        except Exception:
            pass
        await db.commit()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📢 آموزش پیدا کردن هش رسید", url="https://t.me/CandyConnectHelp/4", style="primary"),
    )
    builder.button(text="❌ انصراف", callback_data="cancel_txid", style="danger")
    
    prompt_text = (
        "🔗 <b>ارسال هش تراکنش تتر (USDT)</b>\n\n"
        "لطفاً فقط <b>هش تراکنش (TXID)</b> را به صورت متن ارسال کنید:\n\n"
        "⚠️ <b>توجه:</b> در این مرحله فقط مجاز به ارسال متن هش تراکنش (String) هستید و ارسال تصویر، فایل یا هر فرمت دیگری مجاز نمی‌باشد.\n"
        "💡 هش معتبر با <code>0x</code> شروع شده و طول کل آن ۶۶ کاراکتر است."
    )
    
    await callback.answer()
    await callback.message.answer(
        prompt_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data.startswith("gram_method_pingi_"))
async def gram_pingi_choice(callback: types.CallbackQuery, state: FSMContext):
    """Handles Gram: Transfer from Pingi exchange."""
    invoice_id = callback.data.split('_')[3]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv or inv['status'] != 'pending':
        return await callback.answer("⏳ این فاکتور منقضی شده یا قبلاً پردازش شده است.", show_alert=True)

    await state.update_data(txid_invoice_id=invoice_id, txid_gateway='gram', transfer_method='pingi')
    await state.set_state(PaymentState.waiting_for_pingi_receipt)
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("UPDATE invoices SET transfer_method = 'pingi' WHERE id = ?", (invoice_id,))
        try:
            await db.execute("UPDATE payment_reports SET transfer_method = 'pingi' WHERE invoice_id = ?", (invoice_id,))
        except Exception:
            pass
        await db.commit()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📢 آموزش پیدا کردن هش رسید", url="https://t.me/CandyConnectHelp/4", style="primary"),
    )
    builder.button(text="❌ انصراف", callback_data="cancel_txid", style="danger")
    
    prompt_text = (
        "🧾 <b>انتقال از صرافی پینگی</b>\n\n"
        "لطفاً <b>کد پیگیری تراکنش</b> (۶۴ یا ۴۴ کاراکتر) یا <b>تصویر رسید (اسکرین‌شات)</b> را ارسال کنید:"
    )
    
    await callback.answer()
    await callback.message.edit_text(
        prompt_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data.startswith("gram_method_wallet_"))
async def gram_wallet_choice(callback: types.CallbackQuery, state: FSMContext):
    """Handles Gram: Transfer from personal wallet or other exchanges."""
    invoice_id = callback.data.split('_')[3]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv or inv['status'] != 'pending':
        return await callback.answer("⏳ این فاکتور منقضی شده یا قبلاً پردازش شده است.", show_alert=True)

    await state.update_data(txid_invoice_id=invoice_id, txid_gateway='gram', transfer_method='wallet_or_other')
    await state.set_state(PaymentState.waiting_for_txid_string)
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("UPDATE invoices SET transfer_method = 'wallet_or_other' WHERE id = ?", (invoice_id,))
        try:
            await db.execute("UPDATE payment_reports SET transfer_method = 'wallet_or_other' WHERE invoice_id = ?", (invoice_id,))
        except Exception:
            pass
        await db.commit()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📢 آموزش پیدا کردن هش رسید", url="https://t.me/CandyConnectHelp/4", style="primary"),
    )
    builder.button(text="❌ انصراف", callback_data="cancel_txid", style="danger")
    
    prompt_text = (
        "🔗 <b>انتقال از کیف پول شخصی یا صرافی های دیگر</b>\n\n"
        "لطفاً فقط <b>هش تراکنش (TXID)</b> را به صورت متن ارسال کنید:\n\n"
        "⚠️ <b>توجه:</b> در این مرحله فقط مجاز به ارسال متن هش تراکنش (String) هستید و ارسال تصویر، فایل یا هر فرمت دیگری مجاز نمی‌باشد.\n"
        "💡 هش معتبر گرام دقیقاً ۶۴ یا ۴۴ کاراکتر است."
    )
    
    await callback.answer()
    await callback.message.edit_text(
        prompt_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data == "cancel_txid")
async def cancel_txid(callback: types.CallbackQuery, state: FSMContext):
    """Handles cancel txid."""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("عملیات لغو شد.")

async def build_receipt_notification_content(
    invoice_id: str,
    user_id: int | None = None,
    gateway: str | None = None,
    transfer_method: str | None = None,
    stored_value: str | None = None,
    has_photo: bool | None = None,
    receipt_text: str = "",
    is_appeal: bool = False,
    appeal_text: str = "",
    with_back_button: bool = False
) -> tuple[str, types.InlineKeyboardMarkup, bool, str]:
    """Helper to build payment receipt details, caption, and inline action buttons."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    # 0. Fetch Payment Report if missing fields
    if not user_id or stored_value is None or gateway is None:
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM payment_reports WHERE invoice_id = ?", (invoice_id,)) as cur:
                p_row = await cur.fetchone()
                if p_row:
                    user_id = user_id or p_row['user_id']
                    gateway = gateway or p_row['payment_method']
                    transfer_method = transfer_method or p_row['transfer_method']
                    if stored_value is None:
                        stored_value = p_row['crypto_hash']

    # 1. Fetch Invoice
    invoice = None
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            invoice = await cur.fetchone()
            
    if not invoice:
        invoice = {
            'user_id': user_id or 0,
            'plan_id': 0,
            'days': 0,
            'gb': 0,
            'base_price': 0,
            'wallet_deduction': 0,
            'discount_code': None,
            'discount_deduction': 0,
            'gift_code': None,
            'gift_deduction': 0,
            'final_amount': 0,
            'license_note': '',
            'created_at': None,
            'crypto_amount': None,
            'crypto_rate': None,
            'transfer_method': transfer_method,
            'renew_license_id': None
        }
    else:
        if not user_id:
            user_id = invoice['user_id']
        if not gateway:
            gateway = invoice['gateway'] if 'gateway' in invoice.keys() else (invoice['payment_method'] if 'payment_method' in invoice.keys() else 'unknown')
        if not transfer_method:
            transfer_method = invoice['transfer_method'] if 'transfer_method' in invoice.keys() else None

    # Detect if stored_value is a photo file_id
    if has_photo is None:
        sv = str(stored_value or "").strip()
        has_photo = bool(sv and not sv.startswith("0x") and len(sv) > 50 and " " not in sv)

    # 2. Fetch User & Purchase Stats
    username = "ندارد"
    purchase_count = 0
    total_spent = 0
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT username FROM users WHERE id = ?", (user_id,)) as cur:
            u_row = await cur.fetchone()
            if u_row and u_row['username']:
                username = f"@{u_row['username']}"
                
        async with db.execute("""
            SELECT COUNT(*), COALESCE(SUM(final_amount), 0) 
            FROM invoices 
            WHERE user_id = ? AND status IN ('paid', 'approved', 'completed')
        """, (user_id,)) as cur:
            stats = await cur.fetchone()
            if stats:
                purchase_count = stats[0]
                total_spent = stats[1]

    # 3. Plan / Service Info
    plan_id = invoice['plan_id'] if 'plan_id' in invoice.keys() else 0
    is_wallet_charge = (not plan_id or plan_id == 0)
    
    plan_name = "سرویس سفارشی"
    if not is_wallet_charge:
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT name FROM plans WHERE id = ?", (plan_id,)) as cur:
                p_row = await cur.fetchone()
                if p_row and p_row['name']:
                    plan_name = p_row['name']

    # 4. Dates
    invoice_created_jalali = format_date_to_jalali(invoice['created_at'])
    receipt_sent_jalali = get_current_jalali()

    # 5. Amounts & Crypto
    final_amount = invoice['final_amount'] or 0
    base_price = invoice['base_price'] or final_amount
    crypto_amount = invoice['crypto_amount'] if 'crypto_amount' in invoice.keys() else None
    crypto_rate = invoice['crypto_rate'] if 'crypto_rate' in invoice.keys() else None
    
    # Gateway and Transfer method labels
    if gateway == 'gram':
        gateway_title = "گرام (TON)"
        transfer_title = "انتقال از صرافی پینگی" if transfer_method == 'pingi' else "کیف پول شخصی یا صرافی‌های دیگر"
        crypto_symbol = "GRAM"
        if not crypto_rate:
            crypto_rate = await get_gram_irt_price() or 1
        if not crypto_amount and crypto_rate:
            crypto_amount = round(final_amount / crypto_rate, 2)
    elif gateway == 'usdt':
        gateway_title = "تتر USDT (شبکه BSC BEP-20)"
        transfer_title = "کیف پول شخصی یا صرافی"
        crypto_symbol = "USDT"
        if not crypto_rate:
            crypto_rate = await get_arz_usdt_rate() or 1
        if not crypto_amount and crypto_rate:
            crypto_amount = round(final_amount / crypto_rate, 2)
    else:
        gateway_title = gateway or "کارت به کارت / درگاه"
        transfer_title = transfer_method or "پیش‌فرض"
        crypto_symbol = "ارز دیجیتال"
        crypto_amount = crypto_amount or 0
        crypto_rate = crypto_rate or 0

    # 7. Discount & Gift codes
    discount_code = invoice['discount_code'] if 'discount_code' in invoice.keys() else None
    discount_deduction = (invoice['discount_deduction'] if 'discount_deduction' in invoice.keys() else 0) or 0
    gift_code = invoice['gift_code'] if 'gift_code' in invoice.keys() else None
    gift_deduction = (invoice['gift_deduction'] if 'gift_deduction' in invoice.keys() else 0) or 0
    wallet_deduction = (invoice['wallet_deduction'] if 'wallet_deduction' in invoice.keys() else 0) or 0

    if discount_code and discount_deduction > 0:
        discount_text = f"✅ استفاده شده (کد: <code>{discount_code}</code>) ➔ کسر <b>{discount_deduction:,} تومان</b>"
    else:
        discount_text = "استفاده نشده"

    if gift_code and gift_deduction > 0:
        gift_text = f"✅ استفاده شده (کد: <code>{gift_code}</code>) ➔ کسر <b>{gift_deduction:,} تومان</b>"
    else:
        gift_text = "استفاده نشده"

    # 8. Order / Service Details text
    if is_wallet_charge:
        order_section = (
            f"💰 <b>نوع سفارش: شارژ کیف پول</b>\n"
            f"• مبلغ درخواستی جهت شارژ: <b>{final_amount:,} تومان</b>"
        )
    else:
        renew_id = invoice['renew_license_id'] if 'renew_license_id' in invoice.keys() else None
        renew_str = f"تمدید سرویس (شناسه: {renew_id})" if renew_id else "سرویس جدید"
        note_val = invoice['license_note'] if 'license_note' in invoice.keys() else ''
        note_str = f"\n• یادداشت کاربر: <i>{note_val}</i>" if note_val else ""
        days_val = invoice['days'] if 'days' in invoice.keys() else 0
        gb_val = invoice['gb'] if 'gb' in invoice.keys() else 0
        order_section = (
            f"📦 <b>نوع سفارش: خرید پلن / سرویس</b>\n"
            f"• نام پلن: <b>{plan_name}</b>\n"
            f"• مشخصات سرویس: <b>{days_val} روزه | {gb_val} گیگابایت</b>\n"
            f"• وضعیت: <b>{renew_str}</b>"
            f"{note_str}"
        )

    # 9. Header
    header = "🔄 <b>تجدیدنظر رسید پرداخت</b>" if is_appeal else "📩 <b>رسید پرداخت جدید</b>"

    # 10. Construct full message text
    rate_str = f"{int(crypto_rate):,} تومان" if crypto_rate else "نامشخص"
    amount_crypto_str = f"{crypto_amount} {crypto_symbol}" if crypto_amount is not None else "نامشخص"

    caption_text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>اطلاعات کاربر:</b>\n"
        f"• شناسه عددی: <code>{user_id}</code>\n"
        f"• نام کاربری: {username}\n"
        f"• تعداد خریدهای موفق کاربر: <b>{purchase_count} خرید</b>\n"
        f"• جمع تومانی کل خریدهای موفق: <b>{total_spent:,} تومان</b>\n\n"
        f"🛒 <b>مشخصات فاکتور و سرویس:</b>\n"
        f"• شماره فاکتور: <code>{invoice_id}</code>\n"
        f"{order_section}\n\n"
        f"💵 <b>مبالغ مالی در زمان صدور فاکتور:</b>\n"
        f"• مبلغ اولیه فاکتور: <b>{base_price:,} تومان</b>\n"
        f"• کد تخفیف: {discount_text}\n"
        f"• کد هدیه: {gift_text}\n"
    )

    if wallet_deduction > 0:
        caption_text += f"• کسر از کیف پول: <b>{wallet_deduction:,} تومان</b>\n"

    caption_text += (
        f"• <b>مبلغ نهایی فاکتور:</b> <b>{final_amount:,} تومان</b>\n"
        f"• <b>مبلغ ارزی زمان صدور:</b> <code>{amount_crypto_str}</code>\n"
        f"• نرخ هر واحد ارز: {rate_str}\n\n"
        f"💳 <b>اطلاعات درگاه و پرداخت:</b>\n"
        f"• درگاه: <b>{gateway_title}</b>\n"
        f"• روش انتقال: <b>{transfer_title}</b>\n"
    )

    if has_photo:
        caption_text += "• نوع رسید: <b>تصویر فیش / اسکرین‌شات</b>\n"
        if receipt_text:
            caption_text += f"• متن همراه: <i>{receipt_text}</i>\n"
    else:
        caption_text += f"• هش / کد پیگیری: <code>{stored_value or 'ثبت نشده'}</code>\n"

    caption_text += (
        f"\n⏱ <b>زمان‌بندی:</b>\n"
        f"• تاریخ صدور فاکتور: <b>{invoice_created_jalali}</b>\n"
        f"• تاریخ ارسال رسید: <b>{receipt_sent_jalali}</b>\n"
    )

    if is_appeal and appeal_text:
        caption_text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 <b>توضیحات و پاسخ جدید کاربر (تجدیدنظر):</b>\n"
            f"<blockquote>{appeal_text}</blockquote>\n"
        )

    caption_text += "━━━━━━━━━━━━━━━━━━━━"

    # 11. Extract Hash & Build Action Buttons
    raw_hash_to_clean = stored_value if not has_photo else (receipt_text or "")
    extracted_hash = extract_tx_hash(str(raw_hash_to_clean or ""))

    admin_builder = InlineKeyboardBuilder()

    # Row 1 Button 1: User Management
    btn_user_mgmt = types.InlineKeyboardButton(
        text="👤 مدیریت کاربر", 
        callback_data=f"manage_user_group_{user_id}"
    )

    # Row 1 Button 2: Validate Transaction
    if gateway == 'gram' and transfer_method == 'pingi':
        btn_validate = types.InlineKeyboardButton(
            text="🔍 اعتبارسنجی تراکنش", 
            callback_data=f"no_hash_{invoice_id}"
        )
    elif gateway == 'gram' and transfer_method != 'pingi':
        if extracted_hash:
            btn_validate = types.InlineKeyboardButton(
                text="🔍 اعتبارسنجی تراکنش", 
                url=f"https://tonscan.org/tx/{extracted_hash}"
            )
        else:
            btn_validate = types.InlineKeyboardButton(
                text="🔍 اعتبارسنجی تراکنش", 
                callback_data=f"no_hash_{invoice_id}"
            )
    elif gateway == 'usdt':
        if extracted_hash:
            btn_validate = types.InlineKeyboardButton(
                text="🔍 اعتبارسنجی تراکنش", 
                url=f"https://bsctrace.com/tx/{extracted_hash}"
            )
        else:
            btn_validate = types.InlineKeyboardButton(
                text="🔍 اعتبارسنجی تراکنش", 
                callback_data=f"no_hash_{invoice_id}"
            )
    else:
        btn_validate = types.InlineKeyboardButton(
            text="🔍 اعتبارسنجی تراکنش", 
            callback_data=f"no_hash_{invoice_id}"
        )

    admin_builder.row(btn_user_mgmt, btn_validate)

    # Row 2: Reject & Confirm
    btn_reject = types.InlineKeyboardButton(
        text="❌ رد", 
        callback_data=f"reject_receipt_{invoice_id}"
    )
    btn_confirm = types.InlineKeyboardButton(
        text="✅ تایید", 
        callback_data=f"confirm_receipt_{invoice_id}"
    )
    admin_builder.row(btn_reject, btn_confirm)

    # Row 3: Delete invoice (button 5)
    btn_del_invoice = types.InlineKeyboardButton(
        text="🗑 حذف فاکتور", 
        callback_data=f"fin_del_inv_{invoice_id}",
        style="danger"
    )
    admin_builder.row(btn_del_invoice)

    # Row 4: Back button (if requested)
    if with_back_button:
        back_cb = with_back_button if isinstance(with_back_button, str) else "fin_pending_receipts"
        btn_back = types.InlineKeyboardButton(
            text="🔙 بازگشت", 
            callback_data=back_cb,
            style="danger"
        )
        admin_builder.row(btn_back)

    return caption_text, admin_builder.as_markup(), has_photo, (stored_value or "")


async def _forward_receipt_to_admins(
    bot,
    user_id: int,
    invoice_id: str,
    gateway: str,
    transfer_method: str,
    stored_value: str,
    has_photo: bool,
    receipt_text: str = "",
    is_appeal: bool = False,
    appeal_text: str = ""
):
    """Helper to forward payment receipt to admins with inline action buttons."""
    from bot.config import ADMIN_IDS
    caption_text, reply_markup, has_photo_val, stored_val = await build_receipt_notification_content(
        invoice_id=invoice_id,
        user_id=user_id,
        gateway=gateway,
        transfer_method=transfer_method,
        stored_value=stored_value,
        has_photo=has_photo,
        receipt_text=receipt_text,
        is_appeal=is_appeal,
        appeal_text=appeal_text,
        with_back_button=False
    )
    for admin_id in ADMIN_IDS:
        try:
            if has_photo_val:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=stored_val,
                    caption=caption_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=caption_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        except Exception:
            continue

@payment_router.callback_query(F.data.startswith("no_hash_"))
async def admin_no_hash_alert(callback: types.CallbackQuery):
    """Alerts admin that this receipt has no blockchain tx hash (Scenario 1: Pingi exchange)."""
    await callback.answer(
        "❌ خطای رسید هش ندارد\n(این واریزی از صرافی پینگی انجام شده و فاقد هش بلاکچین مستقیم است.)",
        show_alert=True
    )

@payment_router.message(PaymentState.waiting_for_pingi_receipt)
async def process_pingi_receipt(message: types.Message, state: FSMContext):
    """Handles Pingi receipt — accepts either tracking code (text) or screenshot (photo)."""
    has_photo = bool(message.photo)
    has_text = bool(message.text and message.text.strip())
    
    if not has_photo and not has_text:
        return await message.reply(
            "❌ خطا: لطفاً کد پیگیری تراکنش (متن) یا تصویر رسید (اسکرین‌شات) را ارسال کنید.",
            parse_mode="HTML"
        )
        
    data = await state.get_data()
    invoice_id = data.get('txid_invoice_id')
    gateway = data.get('txid_gateway', 'gram')
    transfer_method = data.get('transfer_method', 'pingi')
    
    if has_text and not has_photo:
        pingi_code = message.text.strip()
        if len(pingi_code) not in (64, 44):
            return await message.reply(
                "❌ <b>کد پیگیری تراکنش نامعتبر است!</b>\n\n"
                "طول کد پیگیری تراکنش پینگی (گرام) باید دقیقاً ۶۴ یا ۴۴ کاراکتر باشد.\n"
                "لطفاً کد معتبر را ارسال نمایید یا تصویر رسید را بفرستید.",
                parse_mode="HTML"
            )
        stored_value = pingi_code
        receipt_text = ""
    else:
        stored_value = message.photo[-1].file_id
        receipt_text = message.caption or ""
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout = 5000;")
        await db.execute('''
            UPDATE invoices 
            SET status = 'pending_receipt', transfer_method = ? 
            WHERE id = ?
        ''', (transfer_method, invoice_id))
        try:
            await db.execute('''
                UPDATE payment_reports 
                SET status = 'pending_receipt', crypto_hash = ?, transfer_method = ?, receipt_time = CURRENT_TIMESTAMP
                WHERE invoice_id = ?
            ''', (stored_value, transfer_method, invoice_id))
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    """
                    UPDATE payment_reports
                    SET status = 'pending_receipt', crypto_hash = ?
                    WHERE invoice_id = ?
                    """,
                    (stored_value, invoice_id),
                )
            except aiosqlite.OperationalError:
                await db.execute(
                    """
                    UPDATE payment_reports
                    SET payment_Status = 'pending_receipt', crypto_hash = ?
                    WHERE id_invoice = ?
                    """,
                    (stored_value, invoice_id),
                )
        await db.commit()
        
    await state.clear()
    await message.reply("✅ رسید شما جهت بررسی ثبت شد. پس از تایید مدیر، فاکتور شما نهایی خواهد شد.")
    
    await _forward_receipt_to_admins(
        bot=message.bot,
        user_id=message.from_user.id,
        invoice_id=invoice_id,
        gateway=gateway,
        transfer_method=transfer_method,
        stored_value=stored_value,
        has_photo=has_photo,
        receipt_text=receipt_text
    )

@payment_router.message(PaymentState.waiting_for_txid_string)
async def process_txid_string(message: types.Message, state: FSMContext):
    """Handles TXID input — strictly requires a string/text. Rejects images and files with error."""
    # Check if user sent photo, file, sticker, voice, video, or any non-text media
    if message.photo or message.document or message.video or message.voice or message.audio or message.sticker or message.animation:
        return await message.reply(
            "❌ ارسال تصویر یا فایل مجاز نمی‌باشد!\nلطفاً فقط هش تراکنش (TXID) را به صورت متن (String) ارسال کنید.",
            parse_mode="HTML"
        )
        
    if not message.text or not isinstance(message.text, str) or not message.text.strip():
        return await message.reply(
            "❌ ورودی نامعتبر است. لطفاً فقط هش تراکنش (TXID) را به صورت متن (String) ارسال کنید.",
            parse_mode="HTML"
        )
        
    txid = message.text.strip()
    data = await state.get_data()
    invoice_id = data.get('txid_invoice_id')
    gateway = data.get('txid_gateway', 'usdt')
    transfer_method = data.get('transfer_method', 'wallet_or_other')
    
    # Hash format validation based on gateway
    if gateway == 'usdt':
        is_valid_usdt = (
            txid.startswith(("0x", "0X"))
            and len(txid) == 66
            and all(c in "0123456789abcdefABCDEF" for c in txid[2:])
        )
        if not is_valid_usdt:
            return await message.reply(
                "❌ <b>هش تراکنش نامعتبر است!</b>\n\n"
                "هش تراکنش درگاه تتر (USDT) باید با <code>0x</code> شروع شده و طول کل آن دقیقاً ۶۶ کاراکتر باشد.\n"
                "لطفاً فقط کد هش معتبر را به صورت متن ارسال فرمایید.",
                parse_mode="HTML"
            )
    elif gateway == 'gram':
        if len(txid) not in (64, 44):
            return await message.reply(
                "❌ <b>هش تراکنش / کد پیگیری نامعتبر است!</b>\n\n"
                "طول هش تراکنش درگاه گرام باید دقیقاً ۶۴ یا ۴۴ کاراکتر باشد.\n"
                "لطفاً هش معتبر را مجدداً ارسال نمایید.",
                parse_mode="HTML"
            )
    else:
        if len(txid) < 5:
            return await message.reply(
                "❌ هش تراکنش نامعتبر است. لطفاً کد کامل هش تراکنش (TXID) را به صورت متن ارسال کنید.",
                parse_mode="HTML"
            )
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('''
            UPDATE invoices 
            SET status = 'pending_receipt', transfer_method = ? 
            WHERE id = ?
        ''', (transfer_method, invoice_id))
        try:
            await db.execute('''
                UPDATE payment_reports 
                SET status = 'pending_receipt', crypto_hash = ?, transfer_method = ?, receipt_time = CURRENT_TIMESTAMP
                WHERE invoice_id = ?
            ''', (txid, transfer_method, invoice_id))
        except aiosqlite.OperationalError:
            await db.execute('''
                UPDATE payment_reports 
                SET payment_Status = 'pending_receipt', crypto_hash = ?
                WHERE id_invoice = ?
            ''', (txid, invoice_id))
        await db.commit()
        
    await state.clear()
    await message.reply("✅ هش تراکنش شما جهت بررسی ثبت شد. پس از تایید مدیر، حساب شما شارژ خواهد شد.")
    
    await _forward_receipt_to_admins(
        bot=message.bot,
        user_id=message.from_user.id,
        invoice_id=invoice_id,
        gateway=gateway,
        transfer_method=transfer_method,
        stored_value=txid,
        has_photo=False
    )

@payment_router.message(PaymentState.waiting_for_txid)
async def process_txid_legacy(message: types.Message, state: FSMContext):
    """Fallback handler for legacy waiting_for_txid state."""
    await process_txid_string(message, state)

# === ROUTER: ADMIN RECEIPT REJECTION WORKFLOW ===

@payment_router.callback_query(F.data.startswith("reject_receipt_"))
async def admin_reject_receipt(callback: types.CallbackQuery, state: FSMContext):
    """Handles admin reject receipt: starts rejection flow by asking for the reason."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.split('_')[2]
    
    # Check if already confirmed
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if inv and inv['status'] in ('paid', 'approved', 'completed'):
        return await callback.answer("⚠️ این فاکتور قبلاً تایید شده و امکان رد آن وجود ندارد.", show_alert=True)

    await state.update_data(reject_invoice_id=invoice_id)
    await state.set_state(AdminRejectState.waiting_for_reason)
    
    cancel_builder = InlineKeyboardBuilder()
    cancel_builder.button(text="🔙 انصراف", callback_data="cancel_admin_reject")
    
    await callback.answer()
    await callback.message.reply(
        f"✍️ <b>ثبت دلیل رد رسید فاکتور <code>{invoice_id}</code>:</b>\n\n"
        f"لطفاً دلیل رد رسید را به صورت متنی ارسال نمایید (این متن برای کاربر ارسال خواهد شد):",
        reply_markup=cancel_builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data == "cancel_admin_reject")
async def cancel_admin_reject(callback: types.CallbackQuery, state: FSMContext):
    """Cancels admin reject flow."""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("عملیات رد لغو شد.")

@payment_router.message(AdminRejectState.waiting_for_reason)
async def admin_reject_reason_received(message: types.Message, state: FSMContext):
    """Receives rejection reason, then asks admin if 'Reply' button should be provided to user."""
    from bot.config import ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:
        return
        
    if not message.text or not message.text.strip():
        return await message.reply("❌ لطفاً دلیل رد را به صورت متنی وارد کنید:")
        
    reason = message.text.strip()
    data = await state.get_data()
    invoice_id = data.get('reject_invoice_id')
    
    await state.update_data(reject_reason=reason)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ بله، دکمه پاسخ دادن فعال باشد", callback_data=f"set_reply_yes_{invoice_id}"))
    builder.row(types.InlineKeyboardButton(text="❌ خیر، فقط پیام رد ارسال شود", callback_data=f"set_reply_no_{invoice_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 انصراف و لغو رد", callback_data="cancel_admin_reject"))
    
    await message.reply(
        f"📋 <b>دلیل ثبت شد:</b>\n"
        f"<blockquote>{reason}</blockquote>\n\n"
        f"❓ <b>آیا مایلید دکمه «💬 پاسخ دادن» برای کاربر فعال باشد؟</b>\n"
        f"<i>(در صورت فعال بودن، کاربر می‌تواند توضیحات تکمیلی یا رسید اصلاحی جهت تجدیدنظر ارسال نماید.)</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.callback_query(F.data.startswith("set_reply_yes_") | F.data.startswith("set_reply_no_"))
async def admin_reject_decision(callback: types.CallbackQuery, state: FSMContext):
    """Finalizes rejection and sends notification to user with or without reply button."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    allow_reply = callback.data.startswith("set_reply_yes_")
    invoice_id = callback.data.split('_')[3]
    
    data = await state.get_data()
    reason = data.get('reject_reason', 'رسید ارسالی مورد تایید مدیریت قرار نگرفت.')
    await state.clear()
    
    # Update DB
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
        if not inv:
            return await callback.answer("❌ فاکتور یافت نشد.", show_alert=True)
            
        await db.execute("UPDATE invoices SET status = 'rejected' WHERE id = ?", (invoice_id,))
        try:
            await db.execute("UPDATE payment_reports SET status = 'rejected' WHERE invoice_id = ?", (invoice_id,))
        except Exception:
            pass
        await db.commit()
        
    user_id = inv['user_id']
    
    # Build user notification
    user_text = (
        f"❌ <b>کاربر گرامی، رسید پرداخت شما برای فاکتور <code>{invoice_id}</code> تایید نشد.</b>\n\n"
        f"📝 <b>دلیل رد:</b>\n"
        f"<blockquote>{reason}</blockquote>\n"
    )
    
    user_markup = None
    if allow_reply:
        user_text += "\n💡 در صورتی که نیاز به توضیح یا ارسال مجدد رسید اصلاحی دارید، می‌توانید از دکمه زیر استفاده نمایید:"
        u_builder = InlineKeyboardBuilder()
        u_builder.button(text="💬 پاسخ دادن", callback_data=f"appeal_receipt_{invoice_id}")
        user_markup = u_builder.as_markup()
        
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=user_text,
            reply_markup=user_markup,
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    status_str = "همراه با دکمه پاسخ" if allow_reply else "بدون دکمه پاسخ"
    await callback.answer("❌ فاکتور رد شد.", show_alert=True)
    await callback.message.edit_text(
        f"❌ فاکتور <code>{invoice_id}</code> با موفقیت رد شد و به کاربر اطلاع داده شد ({status_str}).",
        parse_mode="HTML"
    )

# === ROUTER: USER APPEAL / REPLY WORKFLOW ===

@payment_router.callback_query(F.data.startswith("appeal_receipt_"))
async def user_start_appeal(callback: types.CallbackQuery, state: FSMContext):
    """User clicks '💬 پاسخ دادن' on rejected receipt notification."""
    invoice_id = callback.data.split('_')[2]
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv:
        return await callback.answer("❌ فاکتور یافت نشد.", show_alert=True)
        
    if inv['status'] in ('paid', 'approved', 'completed'):
        return await callback.answer("✅ این فاکتور قبلاً تایید شده است.", show_alert=True)
        
    await state.update_data(appeal_invoice_id=invoice_id)
    await state.set_state(PaymentState.waiting_for_appeal)
    
    cancel_builder = InlineKeyboardBuilder()
    cancel_builder.button(text="🔙 انصراف", callback_data="cancel_txid")
    
    await callback.answer()
    await callback.message.reply(
        f"✍️ <b>پاسخ به رد رسید (درخواست تجدیدنظر)</b>\n\n"
        f"🛒 فاکتور: <code>{invoice_id}</code>\n\n"
        f"لطفاً توضیحات جدید، کد پیگیری صحیح یا اسکرین‌شات اصلاحی خود را ارسال نمایید تا جهت بررسی برای مدیریت ارسال گردد:",
        reply_markup=cancel_builder.as_markup(),
        parse_mode="HTML"
    )

@payment_router.message(PaymentState.waiting_for_appeal)
async def process_appeal_response(message: types.Message, state: FSMContext):
    """Processes user's appeal message (text, photo, or photo+caption) and resends receipt to admins."""
    has_photo = bool(message.photo)
    has_text = bool(message.text and message.text.strip())
    
    if not has_photo and not has_text:
        return await message.reply(
            "❌ ورودی نامعتبر است. لطفاً توضیحات متنی یا تصویر رسید را ارسال فرمایید.",
            parse_mode="HTML"
        )
        
    data = await state.get_data()
    invoice_id = data.get('appeal_invoice_id')
    await state.clear()
    
    if not invoice_id:
        return await message.reply("❌ خطا: فاکتور منقضی شده است. لطفاً مجدداً تلاش کنید.")

    stored_value = message.photo[-1].file_id if has_photo else message.text.strip()
    appeal_text = (message.caption or "").strip() if has_photo else message.text.strip()
    if has_photo and not appeal_text:
        appeal_text = "کاربر تصویر فیش جدید ارسال کرده است."

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    gateway = inv['payment_method'] if inv and inv['payment_method'] else 'gram'
    transfer_method = inv['transfer_method'] if inv and 'transfer_method' in inv.keys() and inv['transfer_method'] else 'wallet_or_other'

    # Update DB to pending_receipt
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("UPDATE invoices SET status = 'pending_receipt' WHERE id = ?", (invoice_id,))
        try:
            await db.execute("""
                UPDATE payment_reports 
                SET status = 'pending_receipt', crypto_hash = ? 
                WHERE invoice_id = ?
            """, (stored_value, invoice_id))
        except Exception:
            pass
        await db.commit()

    await message.reply("✅ توضیحات و رسید جدید شما جهت تجدیدنظر برای مدیریت ارسال شد. لطفاً منتظر بررسی بمانید.")

    # Resend to admins with appeal title and note
    await _forward_receipt_to_admins(
        bot=message.bot,
        user_id=message.from_user.id,
        invoice_id=invoice_id,
        gateway=gateway,
        transfer_method=transfer_method,
        stored_value=stored_value,
        has_photo=has_photo,
        receipt_text=message.caption if has_photo else "",
        is_appeal=True,
        appeal_text=appeal_text
    )

# === ROUTER: ADMIN RECEIPT APPROVAL WITH STRICT SECURITY ===

@payment_router.callback_query(F.data.startswith("confirm_receipt_"))
async def admin_confirm_receipt(callback: types.CallbackQuery):
    """Handles admin confirm receipt with strict deduplication and atomic safety."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.split('_')[2]
    
    # 1. Check if already confirmed in DB
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
            
    if not inv:
        return await callback.answer("❌ فاکتور یافت نشد.", show_alert=True)
        
    if inv['status'] in ('paid', 'approved', 'completed'):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await callback.answer("⚠️ این رسید قبلاً تایید شده است!", show_alert=True)

    # 2. Strict Check for Hash Deduplication across all confirmed invoices
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT crypto_hash FROM payment_reports WHERE invoice_id = ?", (invoice_id,)) as cur:
            rep = await cur.fetchone()
            
    raw_hash = rep['crypto_hash'] if rep and rep['crypto_hash'] else None
    if raw_hash and len(str(raw_hash).strip()) >= 8:
        clean_h = extract_tx_hash(str(raw_hash))
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT pr.invoice_id 
                FROM payment_reports pr
                JOIN invoices inv ON pr.invoice_id = inv.id
                WHERE (pr.crypto_hash = ? OR pr.crypto_hash = ? OR pr.crypto_hash LIKE ?)
                  AND pr.invoice_id != ?
                  AND (pr.status IN ('paid', 'approved', 'completed') OR inv.status IN ('paid', 'approved', 'completed'))
                LIMIT 1
            """, (raw_hash, clean_h, f"%{clean_h}%", invoice_id)) as cur:
                duplicate_used = await cur.fetchone()
                
        if duplicate_used:
            return await callback.answer(
                f"⛔️ هشدار امنیتی!\nاین هش قبلاً در فاکتور {duplicate_used['invoice_id']} تایید شده است.\nامکان تایید مجدد وجود ندارد!",
                show_alert=True
            )

    # 3. Remove buttons immediately to prevent fast double-clicks
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # 4. Delegate to PaymentConfirmationManager (Atomic rowcount check inside)
    from payment.confirm import PaymentConfirmationManager
    pcm = PaymentConfirmationManager(callback.bot)
    success = await pcm.confirm_paid(invoice_id, method="offline_receipt")
    
    if success:
        await callback.answer("✅ رسید با موفقیت تایید شد.", show_alert=True)
        await callback.message.reply(
            f"✅ رسید فاکتور <code>{invoice_id}</code> با موفقیت تایید و اعمال گردید.",
            parse_mode="HTML"
        )
    else:
        await callback.answer("⚠️ این رسید قبلاً تایید شده یا قابل پردازش نمی‌باشد.", show_alert=True)

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


# === ROUTER: ADMIN DELETE INVOICE FROM RECEIPT VIEW ===

@payment_router.callback_query(F.data.startswith("fin_del_inv_"))
async def admin_prompt_delete_invoice(callback: types.CallbackQuery):
    """Prompts admin confirmation before deleting invoice from receipt view."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
    
    invoice_id = callback.data.replace("fin_del_inv_", "").strip()
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🗑 بله، فاکتور حذف شود", callback_data=f"fin_confirm_del_inv_{invoice_id}"),
        types.InlineKeyboardButton(text="🔙 انصراف", callback_data=f"fin_cancel_del_inv_{invoice_id}")
    )
    await callback.message.reply(
        f"⚠️ <b>آیا از حذف کامل فاکتور <code>{invoice_id}</code> اطمینان دارید؟</b>\n\n"
        f"با تایید، این فاکتور و اطلاعات رسید مربوط به آن از دیتابیس حذف خواهند شد.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.callback_query(F.data.startswith("fin_confirm_del_inv_"))
async def admin_confirm_delete_invoice(callback: types.CallbackQuery):
    """Executes deletion of invoice and associated payment reports/licenses."""
    from bot.config import ADMIN_IDS
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        
    invoice_id = callback.data.replace("fin_confirm_del_inv_", "").strip()
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout = 5000;")
        await db.execute("DELETE FROM xui_licenses WHERE invoice_id = ?", (invoice_id,))
        await db.execute("DELETE FROM payment_reports WHERE invoice_id = ?", (invoice_id,))
        await db.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        await db.commit()
        
    await callback.answer("✅ فاکتور با موفقیت حذف شد.", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass


@payment_router.callback_query(F.data.startswith("fin_cancel_del_inv_"))
async def admin_cancel_delete_invoice(callback: types.CallbackQuery):
    """Cancels invoice deletion prompt."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("عملیات حذف فاکتور لغو شد.")

