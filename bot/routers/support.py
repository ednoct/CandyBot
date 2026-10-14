"""
support.py
----------
Module containing functionalities for user support and ticket routing.
"""
import logging
import html
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from bot.states import SupportStates
from bot.config import ADMIN_IDS
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from database import db_manager
from utils.ui_helpers import send_bottom_message
from utils.date_formatter import get_current_jalali

logger = logging.getLogger(__name__)

support_router = Router()

@support_router.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery, state: FSMContext):
    """Handles support menu with bottom-anchored navigation."""
    await callback.answer()
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    # Row 1 (Right to left: FAQ | Support)
    builder.row(
        InlineKeyboardButton(text="🎟 ارسال پیام به پشتیبانی", callback_data="support_send_msg"),
        InlineKeyboardButton(text="❓ سوالات متداول", callback_data="support_faq")
    )
    # Row 2
    builder.row(InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="main_menu", style="danger"))
    
    text = (
        "💬 <b>مرکز پشتیبانی و ارتباط با کارشناسان</b>\n\n"
        "در بخش «سوالات متداول» پاسخ پرسش‌های پرتکرار قرار داده شده است.\n"
        "در صورتی که پاسخ خود را نیافتید، می‌توانید از طریق دکمه «ارسال پیام به پشتیبانی» تیکت جدید ثبت کنید."
    )
    
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.callback_query(F.data == "support_faq")
async def support_faq(callback: types.CallbackQuery, state: FSMContext):
    """Displays frequently asked questions."""
    await callback.answer()
    await state.clear()
    
    faq_text = await db_manager.get_setting("faq_text", "متن سوالات متداول هنوز تنظیم نشده است.")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="support", style="danger")
    
    await send_bottom_message(callback, faq_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.callback_query(F.data == "support_send_msg")
async def support_send_msg_start(callback: types.CallbackQuery, state: FSMContext):
    """Initiates message sending, selecting department if multiple exist."""
    await callback.answer()
    await state.clear()
    
    depts = await db_manager.get_departments(active_only=True)
    if not depts:
        depts = await db_manager.get_departments()
    
    if len(depts) <= 1:
        # Only 1 department, skip selection
        dept_id = depts[0]['id'] if depts else 0
        dept_name = depts[0]['name'] if depts else "عمومی"
        await state.update_data(target_dept_id=dept_id)
        await state.set_state(SupportStates.waiting_for_user_message)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 انصراف", callback_data="support", style="danger")
        
        text = f"✍️ لطفاً پیام خود (متن، عکس، فایل، ویدیو یا وویس) را برای واحد پشتیبانی <b>{dept_name}</b> ارسال کنید:"
        await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        # Multiple departments
        builder = InlineKeyboardBuilder()
        for d in depts:
            builder.button(text=f"🏢 {d['name']}", callback_data=f"seldept_{d['id']}")
        builder.button(text="🔙 انصراف", callback_data="support", style="danger")
        builder.adjust(1)
        
        text = "🏢 <b>انتخاب دپارتمان پشتیبانی</b>\n\nلطفاً واحد مربوطه برای دریافت پیام خود را انتخاب نمایید:"
        await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.callback_query(F.data.startswith("seldept_"))
async def support_dept_selected(callback: types.CallbackQuery, state: FSMContext):
    """Handles department selection by user."""
    await callback.answer()
    dept_id = int(callback.data.split("_")[1])
    dept = await db_manager.get_department(dept_id)
    dept_name = dept['name'] if dept else "عمومی"
    
    await state.clear()
    await state.update_data(target_dept_id=dept_id)
    await state.set_state(SupportStates.waiting_for_user_message)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="support", style="danger")
    
    text = f"✍️ لطفاً پیام خود (متن، عکس، فایل، ویدیو یا وویس) را برای واحد پشتیبانی <b>{dept_name}</b> ارسال کنید:"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.callback_query(F.data.startswith("user_reply_ticket_"))
async def user_reply_ticket_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Handles when the user clicks '✍️ پاسخ دادن' on an agent's response.
    Enters waiting_for_user_message with ticket and department context.
    """
    await callback.answer()
    ticket_id = int(callback.data.split("_")[3])
    ticket = await db_manager.get_support_ticket(ticket_id)
    if not ticket:
        return await callback.answer("❌ این تیکت یافت نشد.", show_alert=True)
        
    await state.clear()
    dept_id = ticket['department_id'] or 0
    await state.update_data(target_dept_id=dept_id, parent_ticket_id=ticket_id)
    await state.set_state(SupportStates.waiting_for_user_message)
    
    dept = await db_manager.get_department(dept_id) if dept_id else None
    dept_name = dept['name'] if dept else "عمومی"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="support", style="danger")
    
    prompt_text = (
        f"✍️ <b>ارسال پاسخ به تیکت #{ticket_id} (دپارتمان {dept_name})</b>\n\n"
        "لطفاً پاسخ یا توضیحات تکمیلی خود را ارسال کنید:"
    )
    await send_bottom_message(callback, prompt_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.message(SupportStates.waiting_for_user_message)
async def process_support_msg(message: types.Message, state: FSMContext):
    """Processes user support message and routes to the appropriate agent with robust fallback."""
    data = await state.get_data()
    dept_id = data.get("target_dept_id", 0)
    parent_ticket_id = data.get("parent_ticket_id")
    
    await state.clear()
    
    # 1. Resolve department details
    dept_name = "عمومی"
    dept_agent_id = None
    target_dept = None
    
    if dept_id > 0:
        target_dept = await db_manager.get_department(dept_id)
        if target_dept:
            dept_name = target_dept['name']
            if target_dept['support_user_id']:
                dept_agent_id = int(target_dept['support_user_id'])
                
    # 2. Extract message content
    text_or_caption = (
        message.text or 
        message.caption or 
        (message.voice and "[پیام صوتی]") or 
        (message.photo and "[تصویر]") or 
        (message.document and "[فایل]") or 
        (message.video and "[ویدیو]") or 
        "بدون متن"
    )
    
    # 3. Create ticket and save message in database
    subject = f"پاسخ به تیکت #{parent_ticket_id}" if parent_ticket_id else f"تیکت دپارتمان {dept_name}"
    ticket_id = await db_manager.create_support_ticket(
        user_id=message.from_user.id,
        department_id=dept_id if dept_id > 0 else None,
        user_message_id=message.message_id,
        text_or_caption=text_or_caption,
        subject=subject
    )
    
    await db_manager.add_support_message(
        ticket_id=ticket_id,
        sender_id=message.from_user.id,
        sender_role='user',
        message_id=message.message_id,
        text=text_or_caption
    )
    
    # 4. Routing & Fallback Candidate Selection
    # Candidates priority: 
    #   Priority 1: Department's assigned agent
    #   Priority 2: General Department's agent ("عمومی")
    #   Priority 3: Main bot admin (ADMIN_IDS[0])
    recipient_candidates = []
    
    # Priority 1
    if dept_agent_id:
        recipient_candidates.append(("پشتیبان اختصاصی دپارتمان", dept_agent_id))
        
    # Priority 2: General department agent
    general_dept = await db_manager.get_department_by_name("عمومی")
    if not general_dept:
        # Fallback to first department
        depts = await db_manager.get_departments()
        if depts:
            general_dept = depts[0]
            
    if general_dept and general_dept['support_user_id']:
        gen_agent = int(general_dept['support_user_id'])
        if not any(c[1] == gen_agent for c in recipient_candidates):
            recipient_candidates.append(("پشتیبان دپارتمان عمومی", gen_agent))
            
    # Priority 3: Bot Main Admin
    if ADMIN_IDS:
        main_admin = int(ADMIN_IDS[0])
        if not any(c[1] == main_admin for c in recipient_candidates):
            recipient_candidates.append(("ادمین اصلی ربات", main_admin))
            
    if not recipient_candidates:
        await message.answer("❌ متاسفانه ادمینی برای پاسخگویی در سیستم پیکربندی نشده است.")
        return
        
    # 5. Format notification for support agent
    now_shamsi = get_current_jalali()
    username = f"@{message.from_user.username}" if message.from_user.username else "ندارد"
    escaped_content = html.escape(str(text_or_caption))
    
    header_extra = f" (در پاسخ به تیکت #{parent_ticket_id})" if parent_ticket_id else ""
    msg_text = (
        f"📣 <b>پیام جدید پشتیبانی از کاربر{header_extra}</b>\n\n"
        f"👤 <b>آیدی عددی:</b> <code>{message.from_user.id}</code>\n"
        f"📛 <b>نام کاربری:</b> {username}\n"
        f"🏢 <b>دپارتمان:</b> {dept_name}\n"
        f"🎫 <b>شماره تیکت:</b> #{ticket_id}\n"
        f"⏰ <b>زمان ارسال:</b> {now_shamsi}\n\n"
        f"📝 <b>متن پیام:</b>\n"
        f"{escaped_content}"
    )
    
    agent_builder = InlineKeyboardBuilder()
    agent_builder.button(text="💬 پاسخ به تیکت", callback_data=f"agentreply_{ticket_id}")
    
    # 6. Attempt delivery with fallback
    sent_successfully = False
    for role_name, agent_id in recipient_candidates:
        try:
            # Copy media if present
            if message.photo or message.document or message.video or message.audio or message.voice:
                await message.bot.copy_message(chat_id=agent_id, from_chat_id=message.chat.id, message_id=message.message_id)
                
            await message.bot.send_message(
                chat_id=agent_id,
                text=msg_text,
                reply_markup=agent_builder.as_markup(),
                parse_mode="HTML"
            )
            sent_successfully = True
            logger.info(f"Ticket #{ticket_id} routed successfully to {role_name} (ID: {agent_id})")
            break
        except Exception as send_err:
            logger.warning(
                f"Failed to route ticket #{ticket_id} to {role_name} (ID: {agent_id}): {send_err}. Attempting fallback..."
            )
            continue
            
    # 7. User feedback
    conf_builder = InlineKeyboardBuilder()
    conf_builder.button(text="🔙 بازگشت به منوی اصلی", callback_data="main_menu", style="danger")
    
    if sent_successfully:
        await message.answer(
            f"✅ <b>پیام شما با موفقیت برای تیم پشتیبانی ارسال شد.</b>\n\n"
            f"🎫 شماره تیکت شما: <b>#{ticket_id}</b>\n"
            "به محض بررسی کارشناسان، پاسخ مستقیماً در همین چت برای شما ارسال خواهد شد.",
            reply_markup=conf_builder.as_markup(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ متاسفانه در حال حاضر ارسال پیام به پشتیبان مقدور نمی‌باشد. لطفاً دقایقی دیگر تلاش فرمایید.",
            reply_markup=conf_builder.as_markup(),
            parse_mode="HTML"
        )
