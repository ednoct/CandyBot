"""
This module corresponds to the 'bot/routers/payment.py' branch in the candy_architecture.md map.
It acts as the UNIFIED PAYMENT HANDLER, routing 'pay_*' callbacks triggered from checkout,
and integrating both online (Tetra) and offline (USDT, GRAM) gateways.
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
    waiting_for_txid = State()

# === ROUTER: UNIFIED PAYMENT HANDLER ===
@payment_router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery, state: FSMContext):
    gateway_code = callback.data.split('_')[1] # e.g. 'card', 'zarinpal', 'aqaye', 'trx', 'usdt', 'gram', 'tetra'
    
    data = await state.get_data()
    if 'final_amount' not in data:
        return await callback.answer("فاکتور شما یافت نشد. لطفا مجددا تلاش کنید.", show_alert=True)
        
    invoice_id = str(uuid.uuid4())[:8].upper()
    amount = data['final_amount']
    
    # Generate Invoice in DB
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        # First save to standard invoices for products
        await db.execute('''
            INSERT INTO invoices (id, user_id, plan_id, days, gb, base_price, wallet_deduction, 
            discount_code, discount_deduction, gift_code, gift_deduction, final_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (invoice_id, callback.from_user.id, data.get('plan_id'), data.get('days'), data.get('gb'),
              data.get('base_price'), data.get('wallet_deduction'), data.get('discount_code'), 
              data.get('discount_amount', 0), data.get('gift_code'), data.get('gift_amount', 0), 
              amount))
              
        # Also create a legacy payment_report if offline
        if gateway_code in ['usdt', 'gram']:
            expires_at = int(time.time()) + (7200 if gateway_code == 'usdt' else 86400)
            method = f"{gateway_code} offline"
            await db.execute('''
                INSERT INTO payment_reports (id_user, id_order, time, price, payment_Status, Payment_Method, id_invoice, expires_at)
                VALUES (?, ?, ?, ?, 'Unpaid', ?, ?, ?)
            ''', (callback.from_user.id, invoice_id, time.strftime('%Y/%m/%d %H:%M:%S'), amount, method, invoice_id, expires_at))

        # Fetch settings for api keys
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT key, value FROM settings') as cursor:
            settings_rows = await cursor.fetchall()
            legacy_settings = {row['key']: row['value'] for row in settings_rows}
            
        await db.commit()
        
    await state.clear()
    
    # 1. Handle Card to Card (Offline)
    if gateway_code == 'card':
        # Default card number fallback
        card_number = legacy_settings.get('card_number', "1234-5678-9012-3456")
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="ارسال رسید تراکنش", callback_data=f"sendtxid_{invoice_id}"))
        
        await callback.message.edit_text(
            f"💳 **پرداخت کارت به کارت**\n\n"
            f"کد فاکتور شما: `{invoice_id}`\n"
            f"مبلغ قابل پرداخت: {amount:,} تومان\n\n"
            f"شماره کارت: `{card_number}`\n\n"
            f"پس از واریز، رسید خود را به پشتیبانی ارسال کنید یا از دکمه زیر جهت ارسال رسید استفاده نمایید.",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    # 2. Handle USDT (Offline)
    if gateway_code == 'usdt':
        arz_usdt_rate = await get_arz_usdt_rate()
        if arz_usdt_rate is None:
            return await callback.answer("خطا در دریافت قیمت لحظه ای تتر. لطفا مجددا تلاش کنید.", show_alert=True)
            
        usdprice = round(amount / arz_usdt_rate, 2)
        if usdprice <= 1:
            return await callback.answer("❌ خطا: کمترین مبلغ برای پرداخت در این درگاه 2 دلار می باشد.", show_alert=True)

        walletaddressusdt = legacy_settings.get('wallet_usdt', '')
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="کپی مقدار تتر", copy_text=types.CopyTextButton(text=str(usdprice))),
            types.InlineKeyboardButton(text="کپی آدرس", copy_text=types.CopyTextButton(text=str(walletaddressusdt)))
        )
        builder.row(
            types.InlineKeyboardButton(text="ارسال رسید تراکنش", callback_data=f"sendtxid_{invoice_id}")
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
        gram_irt_price = await get_gram_irt_price()
        if gram_irt_price is None:
            return await callback.answer("خطا در دریافت قیمت لحظه ای گرام. لطفا مجددا تلاش کنید.", show_alert=True)
            
        gram_amount = round(amount / gram_irt_price, 2)
        if gram_amount <= 0.1:
            return await callback.answer("❌ خطا: کمترین مبلغ برای پرداخت در این درگاه 0.1 گرام می باشد.", show_alert=True)

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
            types.InlineKeyboardButton(text="ارسال رسید تراکنش", callback_data=f"sendtxid_{invoice_id}")
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

    # 4. Handle Tetra (Online)
    if gateway_code == 'tetra':
        from payment.gateways import TetraGateway
        tetra_api_key = legacy_settings.get('tetra_api_key', '')
        if not tetra_api_key:
            return await callback.answer("❌ درگاه تتر فعال یا پیکربندی نشده است.", show_alert=True)
            
        gateway = TetraGateway(tetra_api_key)
        # We can hardcode the URL or get it from settings, usually the API domain is enough
        domain = legacy_settings.get('web_domain', 'https://candy.candyconnect.online')
        callback_url = f"{domain}/api/payment/webhook/tetra"
        
        # TetraGateway expects (invoice_id, amount_toman, callback_url)
        result = await gateway.create_payment(invoice_id, amount, callback_url)
        
        if result.get('success'):
            url = result.get('payment_url_bot') or result.get('payment_url_web')
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(text="💳 پرداخت آنلاین", url=url))
            
            await callback.message.edit_text(
                f"✅ فاکتور آنلاین شما ایجاد شد\n\n"
                f"🛒 کد پیگیری: `{invoice_id}`\n"
                f"💰 مبلغ قابل پرداخت: {amount:,} تومان\n\n"
                f"لطفاً از طریق دکمه زیر پرداخت را انجام دهید:",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await callback.answer(f"❌ خطا در ایجاد فاکتور: {result.get('error', 'Unknown Error')}", show_alert=True)
        return

@payment_router.callback_query(F.data.startswith("sendtxid_"))
async def prompt_txid(callback: types.CallbackQuery, state: FSMContext):
    invoice_id = callback.data.split('_')[1]
    await state.update_data(txid_invoice_id=invoice_id)
    await state.set_state(PaymentState.waiting_for_txid)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="انصراف", callback_data="cancel_txid")
    await callback.message.edit_text(
        "لطفا هش (TxID) تراکنش خود را ارسال کنید:", 
        reply_markup=builder.as_markup()
    )

@payment_router.callback_query(F.data == "cancel_txid")
async def cancel_txid(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("عملیات لغو شد.")

@payment_router.message(PaymentState.waiting_for_txid)
async def process_txid(message: types.Message, state: FSMContext):
    if message.photo:
        txid = message.photo[-1].file_id
    else:
        txid = message.text or message.caption
        
    if not txid:
        return await message.answer("❌ لطفا هش تراکنش (متن) یا تصویر رسید را ارسال کنید.")
        
    data = await state.get_data()
    invoice_id = data.get('txid_invoice_id')
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('''
            UPDATE payment_reports 
            SET status = 'pending_receipt', tracking_code = ? 
            WHERE id_order = ?
        ''', (txid, invoice_id))
        await db.commit()
        
    await state.clear()
    await message.reply(f"✅ رسید شما جهت بررسی ثبت شد. پس از تایید مدیر، حساب شما شارژ خواهد شد.", parse_mode="Markdown")
    
    # Forward receipt to admins
    from bot.config import ADMIN_IDS
    for admin_id in ADMIN_IDS:
        try:
            await message.forward(chat_id=admin_id)
            await message.bot.send_message(chat_id=admin_id, text=f"رسید جدید برای فاکتور `{invoice_id}` ارسال شد.\nلطفا از بخش رسیدهای تایید نشده بررسی کنید.", parse_mode="Markdown")
        except:
            pass
