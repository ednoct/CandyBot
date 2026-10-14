"""
agent.py
--------
User-facing router for the Commission Agency system (نمایندگی کمیسیونی).
Handles agency menu, referral link/banner, activation requests, and settlement requests.
"""

import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db_manager
from bot.states import AgentUserStates
from bot.config import ADMIN_IDS
from utils.ui_helpers import send_bottom_message
from utils.exchange import get_gram_irt_price
from bot.routers.user import AFFILIATE_BANNER_FILE_ID

logger = logging.getLogger(__name__)

agent_router = Router()


# === ROUTER: AGENT MAIN MENU ===
@agent_router.callback_query(F.data == "agent_menu")
async def show_agent_menu(callback: types.CallbackQuery, state: FSMContext):
    """Displays the main Agency (نمایندگی) dashboard for the user."""
    await callback.answer()
    await state.clear()
    user_id = callback.from_user.id

    default_text = await db_manager.get_setting(
        "agent_default_text",
        "💼 <b>سامانه نمایندگی و کسب درآمد CandyConnect</b>\n\n"
        "با پیوستن به جمع نمایندگان ما، از هر خرید زیرمجموعه‌های خود کمیسیون دریافت کرده و درآمد مستمر کسب نمایید."
    )
    commission_percent = await db_manager.get_setting("agent_commission_percent", "15")
    min_settle_val = await db_manager.get_setting("agent_min_settlement_amount", "1000000")
    try:
        min_settle = int(min_settle_val)
    except ValueError:
        min_settle = 1000000

    stats = await db_manager.get_agent_stats(user_id)
    commission_balance = stats['commission_balance']
    settlement_active = bool(stats['settlement_active'])

    text = (
        f"{default_text}\n"
        f"📊 <b>درصد کمیسیون شما:</b> <b>{commission_percent}٪</b>\n"
        f"🎯 <b>حداقل موجودی جهت درخواست تسویه:</b> <b>{min_settle:,} تومان</b>\n"
        f"💰 <b>موجودی کمیسیون نماینده:</b> <b>{commission_balance:,} تومان</b>\n\n"
        "<i>توجه: موجودی کمیسیون نمایندگی مجزا از موجودی کیف پول خرید سرویس می‌باشد.</i>"
    )

    builder = InlineKeyboardBuilder()

    # Button 1: Referral Link
    btn_referral = types.InlineKeyboardButton(
        text="🔗 لینک معرف",
        callback_data="agent_referral",
        style="default"
    )

    # Button 2: Activation or Settlement
    if settlement_active:
        btn_action = types.InlineKeyboardButton(
            text="💳 درخواست تسویه",
            callback_data="agent_req_settlement",
            style="success"
        )
    else:
        btn_action = types.InlineKeyboardButton(
            text="🔓 درخواست فعالسازی برداشت",
            callback_data="agent_req_activation",
            style="default"
        )

    builder.row(btn_referral, btn_action)

    # Back to user main menu
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu", style="danger")
    )

    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === ROUTER: AGENT REFERRAL TAB (WITH ATTACHED BANNER) ===
@agent_router.callback_query(F.data == "agent_referral")
async def show_agent_referral(callback: types.CallbackQuery, state: FSMContext):
    """Displays the agent referral tab with banner and unique agent link."""
    await callback.answer()
    await state.clear()
    user_id = callback.from_user.id

    bot_info = await callback.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=agent_{user_id}"

    commission_percent = await db_manager.get_setting("agent_commission_percent", "15")
    stats = await db_manager.get_agent_stats(user_id)
    invited = stats['invited']
    earned = stats['total_earned']
    balance = stats['commission_balance']

    caption = (
        "💼 <b>لینک و بنر اختصاصی نمایندگی</b>\n\n"
        f"با دعوت کاربران از طریق لینک یا بنر اختصاصی خود، از تمامی خریدهای آنها <b>{commission_percent}٪ کمیسیون دائمی</b> دریافت کنید!\n\n"
        f"👥 <b>تعداد اعضای دعوت‌شده:</b> {invited} نفر\n"
        f"💰 <b>مجموع درآمد کمیسیون شما:</b> {earned:,} تومان\n"
        f"💳 <b>موجودی فعلی کمیسیون:</b> {balance:,} تومان\n\n"
        "🔗 <b>لینک دعوت اختصاصی شما:</b>\n"
        f"<code>{invite_link}</code>\n\n"
        "<i>برای کپی کردن، روی لینک فوق ضربه بزنید.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📢 اشتراک‌گذاری بنر اختصاصی شما",
            switch_inline_query_chosen_chat=types.SwitchInlineQueryChosenChat(
                query="share_agent",
                allow_user_chats=True,
                allow_group_chats=True,
                allow_channel_chats=True
            ),
            style="primary"
        )
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت", callback_data="agent_menu", style="danger")
    )

    banner_file_id = await db_manager.get_setting("affiliate_banner_file_id", AFFILIATE_BANNER_FILE_ID)

    # Attempt to send with photo attachment
    try:
        if banner_file_id:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=banner_file_id,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.warning(f"Could not send agent banner photo: {e}")

    # Fallback to bottom text message
    await send_bottom_message(callback, caption, reply_markup=builder.as_markup(), parse_mode="HTML")


# === ROUTER: REQUEST SETTLEMENT ACTIVATION ===
@agent_router.callback_query(F.data == "agent_req_activation")
async def handle_agent_activation_request(callback: types.CallbackQuery):
    """
    Handles request to permanently activate the settlement button.
    Requires at least 1,000,000 Tomans in commission balance.
    """
    user_id = callback.from_user.id
    stats = await db_manager.get_agent_stats(user_id)

    if stats['settlement_active']:
        await callback.answer("✅ دکمه درخواست تسویه برای شما قبلاً فعال شده است.", show_alert=True)
        return

    commission_balance = stats['commission_balance']
    if commission_balance < 1_000_000:
        diff = 1_000_000 - commission_balance
        await callback.answer(
            f"❌ خطا: حداقل موجودی کمیسیون برای فعالسازی تسویه ۱,۰۰۰,۰۰۰ تومان می‌باشد.\n"
            f"موجودی فعلی شما: {commission_balance:,} تومان\n"
            f"فاصله تا حد نصاب: {diff:,} تومان",
            show_alert=True
        )
        return

    # Check if a pending request is already waiting
    if await db_manager.has_pending_activation_request(user_id):
        await callback.answer(
            "⚠️ درخواست فعالسازی برداشت شما قبلاً ثبت شده و در انتظار بررسی مدیریت است.",
            show_alert=True
        )
        return

    req_id = await db_manager.create_agent_activation_request(
        user_id=user_id,
        commission_balance=commission_balance,
        sub_users_count=stats['invited']
    )

    # Send notifications to Admin(s)
    admin_notif_text = (
        "🔔 <b>درخواست جدید فعالسازی تسویه نمایندگی</b>\n\n"
        f"👤 <b>نماینده:</b> {callback.from_user.full_name} (<code>{user_id}</code>)\n"
        f"🆔 <b>نام کاربری:</b> @{callback.from_user.username or 'ندارد'}\n"
        f"💰 <b>موجودی کمیسیون:</b> {commission_balance:,} تومان\n"
        f"👥 <b>تعداد دعوت‌ها:</b> {stats['invited']} نفر\n"
    )

    admin_builder = InlineKeyboardBuilder()
    admin_builder.row(
        types.InlineKeyboardButton(text="✅ تایید", callback_data=f"agent_act_approve_{req_id}"),
        types.InlineKeyboardButton(text="❌ رد کردن", callback_data=f"agent_act_reject_{req_id}"),
    )

    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_notif_text,
                reply_markup=admin_builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} for activation request: {e}")

    await callback.answer(
        "✅ درخواست فعالسازی دکمه تسویه برای مدیریت ارسال شد.\nنتیجه بررسی از طریق پیام به شما اطلاع داده خواهد شد.",
        show_alert=True
    )


# === ROUTER: REQUEST SETTLEMENT ===
@agent_router.callback_query(F.data == "agent_req_settlement")
async def handle_agent_settlement_request(callback: types.CallbackQuery, state: FSMContext):
    """
    Initiates settlement request if the agent's commission balance reaches minimum threshold.
    """
    user_id = callback.from_user.id
    stats = await db_manager.get_agent_stats(user_id)

    if not stats['settlement_active']:
        return await handle_agent_activation_request(callback)

    min_settle_val = await db_manager.get_setting("agent_min_settlement_amount", "1000000")
    try:
        min_settle = int(min_settle_val)
    except ValueError:
        min_settle = 1000000

    commission_balance = stats['commission_balance']
    if commission_balance < min_settle:
        diff = min_settle - commission_balance
        await callback.answer(
            f"❌ هنوز موجودی کمیسیون شما {diff:,} تومان با حداقل موجودی درخواست تسویه ({min_settle:,} تومان) فاصله دارد.",
            show_alert=True
        )
        return

    await callback.answer()
    await state.set_state(AgentUserStates.waiting_for_withdraw_amount)
    await state.update_data(max_balance=commission_balance, min_settle=min_settle)

    text = (
        "💳 <b>ثبت درخواست تسویه حساب کمیسیون</b>\n\n"
        f"💰 <b>موجودی کمیسیون شما:</b> <b>{commission_balance:,} تومان</b>\n"
        f"🎯 <b>حداقل مبلغ مجاز تسویه:</b> <b>{min_settle:,} تومان</b>\n\n"
        "لطفاً مبلغ مورد نظر خود برای تسویه را به <b>تومان</b> ارسال فرمایید (به صورت عدد انگلیسی):\n"
        "<i>یا جهت تسویه کامل، دکمه «کل موجودی» را لمس کنید.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 کل موجودی", callback_data="agent_withdraw_all")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger")
    )

    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")


@agent_router.callback_query(F.data == "agent_withdraw_all", AgentUserStates.waiting_for_withdraw_amount)
async def handle_agent_withdraw_all(callback: types.CallbackQuery, state: FSMContext):
    """Handles the 'withdraw all' button click."""
    await callback.answer()
    stats = await db_manager.get_agent_stats(callback.from_user.id)
    balance = stats['commission_balance']

    await _process_settlement_amount_flow(
        event=callback,
        state=state,
        amount=balance,
        user_id=callback.from_user.id
    )


@agent_router.message(AgentUserStates.waiting_for_withdraw_amount)
async def process_withdraw_amount_message(message: types.Message, state: FSMContext):
    """Processes user input for settlement amount in Tomans."""
    raw_text = (message.text or "").strip().replace(",", "").replace("،", "")
    if not raw_text.isdigit():
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger"))
        await message.answer("❌ لطفاً یک عدد معتبر به تومان وارد کنید:", reply_markup=builder.as_markup())
        return

    amount = int(raw_text)
    user_id = message.from_user.id
    stats = await db_manager.get_agent_stats(user_id)
    commission_balance = stats['commission_balance']

    min_settle_val = await db_manager.get_setting("agent_min_settlement_amount", "1000000")
    try:
        min_settle = int(min_settle_val)
    except ValueError:
        min_settle = 1000000

    if amount < min_settle:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger"))
        await message.answer(
            f"❌ حداقل مبلغ برای ثبت درخواست تسویه <b>{min_settle:,} تومان</b> است.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    if amount > commission_balance:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger"))
        await message.answer(
            f"❌ مبلغ درخواستی بیشتر از موجودی کمیسیون شما (<b>{commission_balance:,} تومان</b>) است.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    await _process_settlement_amount_flow(
        event=message,
        state=state,
        amount=amount,
        user_id=user_id
    )


async def _process_settlement_amount_flow(event: types.CallbackQuery | types.Message, state: FSMContext, amount: int, user_id: int):
    """Helper to convert amount to GRAM (TON) and present the invoice."""
    bot = event.bot
    chat_id = event.message.chat.id if isinstance(event, types.CallbackQuery) else event.chat.id

    gram_irt_price = await get_gram_irt_price()
    if gram_irt_price is None:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به نمایندگی", callback_data="agent_menu", style="danger"))
        error_msg = "❌ خطا در دریافت قیمت لحظه‌ای گرام. لطفاً چند لحظه بعد مجدداً تلاش فرمایید."
        if isinstance(event, types.CallbackQuery):
            await event.answer(error_msg, show_alert=True)
        else:
            await event.answer(error_msg, reply_markup=builder.as_markup())
        return

    gram_amount = round(amount / gram_irt_price, 2)
    if gram_amount < 0.1:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 بازگشت به نمایندگی", callback_data="agent_menu", style="danger"))
        error_msg = "❌ خطا: کمترین مبلغ برای تسویه در این درگاه 0.1 گرام می‌باشد."
        if isinstance(event, types.CallbackQuery):
            await event.answer(error_msg, show_alert=True)
        else:
            await event.answer(error_msg, reply_markup=builder.as_markup())
        return

    await state.update_data(
        settle_amount_irt=amount,
        settle_gram_amount=gram_amount,
        settle_gram_price=gram_irt_price
    )

    invoice_text = (
        "🌐 شبکه: TON OPEN NETWORK\n"
        f"💵 (تون)نرخ هر واحد گرام (GRAM): {gram_irt_price:,} تومان\n"
        f"💰 مقدار: <code>{gram_amount}</code> گرام (تون)\n\n"
        f"💵 معادل تومانی درخواستی: <b>{amount:,} تومان</b>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📥 وارد کردن آدرس کیف پول", callback_data="agent_enter_wallet")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger")
    )

    if isinstance(event, types.CallbackQuery):
        await send_bottom_message(event, invoice_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await event.answer(invoice_text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === ROUTER: ENTER WALLET ADDRESS ===
@agent_router.callback_query(F.data == "agent_enter_wallet")
async def start_enter_wallet(callback: types.CallbackQuery, state: FSMContext):
    """Prompts the user to enter their TON wallet address."""
    await callback.answer()
    data = await state.get_data()
    if "settle_amount_irt" not in data:
        return await show_agent_menu(callback, state)

    await state.set_state(AgentUserStates.waiting_for_wallet_address)

    prompt_text = (
        "👛 <b>ورود آدرس کیف پول TON</b>\n\n"
        "لطفاً آدرس کیف پول <b>شبکه تون (TON Open Network)</b> خود را با دقت ارسال فرمایید.\n\n"
        "⚠️ <b>هشدار مهم:</b> مسئولیت وارد کردن آدرس اشتباه تماماً به عهده شخص شماست و امکان ویرایش یا بازگشت وجه پس از واریز وجود ندارد."
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger")
    )

    await send_bottom_message(callback, prompt_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@agent_router.message(AgentUserStates.waiting_for_wallet_address)
async def process_wallet_address(message: types.Message, state: FSMContext):
    """Validates the wallet address and shows the final confirmation invoice."""
    wallet_addr = (message.text or "").strip()

    if len(wallet_addr) < 20 or " " in wallet_addr or len(wallet_addr) > 120:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger"))
        await message.answer(
            "❌ فرمت آدرس کیف پول نامعتبر است. لطفاً یک آدرس معتبر شبکه TON ارسال نمایید:",
            reply_markup=builder.as_markup()
        )
        return

    data = await state.get_data()
    amount_irt = data.get("settle_amount_irt", 0)
    gram_amount = data.get("settle_gram_amount", 0.0)
    gram_price = data.get("settle_gram_price", 0)

    await state.update_data(settle_wallet_address=wallet_addr)

    confirm_text = (
        "📋 <b>پیش‌فاکتور نهایی درخواست تسویه</b>\n\n"
        "🌐 شبکه: TON OPEN NETWORK\n"
        f"💵 (تون)نرخ هر واحد گرام (GRAM): {gram_price:,} تومان\n"
        f"💰 مقدار: <code>{gram_amount}</code> گرام (تون)\n"
        f"💵 مبلغ تومانی: <b>{amount_irt:,} تومان</b>\n\n"
        f"👛 <b>آدرس کیف پول شما:</b>\n<code>{wallet_addr}</code>\n\n"
        "⚠️ <i>مسئولیت وارد کردن آدرس اشتباه به عهده خود کاربر است.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نهایی کردن درخواست تسویه", callback_data="agent_finalize_settle")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 انصراف", callback_data="agent_menu", style="danger")
    )

    await message.answer(confirm_text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === ROUTER: FINALIZE SETTLEMENT REQUEST ===
@agent_router.callback_query(F.data == "agent_finalize_settle")
async def finalize_settlement_request(callback: types.CallbackQuery, state: FSMContext):
    """
    Atomically deducts balance and creates settlement record, then notifies admin.
    """
    user_id = callback.from_user.id
    data = await state.get_data()

    amount_irt = data.get("settle_amount_irt")
    gram_amount = data.get("settle_gram_amount")
    gram_price = data.get("settle_gram_price")
    wallet_address = data.get("settle_wallet_address")

    if not (amount_irt and gram_amount and wallet_address):
        await callback.answer("❌ اطلاعات درخواست ناقص است. لطفاً مجدداً تلاش فرمایید.", show_alert=True)
        return await show_agent_menu(callback, state)

    settlement_id = await db_manager.create_agent_settlement(
        agent_id=user_id,
        amount_irt=amount_irt,
        amount_gram=gram_amount,
        gram_price=gram_price,
        wallet_address=wallet_address
    )

    if not settlement_id:
        await callback.answer("❌ موجودی کمیسیون شما برای ثبت این تسویه کافی نیست.", show_alert=True)
        await state.clear()
        return await show_agent_menu(callback, state)

    await state.clear()
    await callback.answer("✅ درخواست تسویه با موفقیت ثبت شد.", show_alert=False)

    stats = await db_manager.get_agent_stats(user_id)
    invites_count = stats['invited']

    # Send confirmation to agent
    user_confirm_text = (
        "✅ <b>درخواست تسویه با موفقیت نهایی شد!</b>\n\n"
        f"🆔 <b>شماره پیگیری:</b> #{settlement_id}\n"
        f"💰 <b>مبلغ تومانی:</b> {amount_irt:,} تومان\n"
        f"💎 <b>مقدار ارزی:</b> <code>{gram_amount}</code> گرام (تون)\n"
        f"👛 <b>آدرس کیف پول:</b>\n<code>{wallet_address}</code>\n\n"
        "درخواست شما جهت بررسی و واریز برای مدیریت ارسال شد. پس از واریز، لینک هش تراکنش برای شما ارسال خواهد شد."
    )
    user_builder = InlineKeyboardBuilder()
    user_builder.row(
        types.InlineKeyboardButton(text="🔙 بازگشت به نمایندگی", callback_data="agent_menu", style="danger")
    )
    await send_bottom_message(callback, user_confirm_text, reply_markup=user_builder.as_markup(), parse_mode="HTML")

    # Send notification to Admin(s)
    admin_notif_text = (
        "🔔 <b>درخواست جدید تسویه حساب نماینده</b>\n\n"
        f"🆔 <b>شماره تسویه:</b> #{settlement_id}\n"
        f"👤 <b>مشخصات نماینده:</b> {callback.from_user.full_name} (<code>{user_id}</code>)\n"
        f"🔗 <b>نام کاربری:</b> @{callback.from_user.username or 'ندارد'}\n"
        f"👥 <b>تعداد دعوت‌ها:</b> {invites_count} نفر\n\n"
        f"💵 <b>مبلغ تومانی تسویه:</b> {amount_irt:,} تومان\n"
        f"💎 <b>معادل گرامی مبلغ تسویه:</b> <code>{gram_amount}</code> گرام\n"
        f"💵 <b>نرخ هر گرام:</b> {gram_price:,} تومان\n\n"
        f"👛 <b>آدرس کیف پول TON:</b>\n<code>{wallet_address}</code>"
    )

    admin_builder = InlineKeyboardBuilder()
    # Row 1: Copy Wallet Address
    admin_builder.row(
        types.InlineKeyboardButton(
            text="📋 کپی آدرس کیف پول",
            copy_text=types.CopyTextButton(text=wallet_address)
        )
    )
    # Row 2: Settled or Wait
    admin_builder.row(
        types.InlineKeyboardButton(text="✅ تسویه شد", callback_data=f"agent_stl_done_{settlement_id}"),
        types.InlineKeyboardButton(text="⏳ منتظر بماند", callback_data=f"agent_stl_wait_{settlement_id}")
    )

    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_notif_text,
                reply_markup=admin_builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} for settlement #{settlement_id}: {e}")