"""
agent_support.py
----------------
Module containing functionalities for agent support management and threaded replies.
"""
import logging
import html
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.states import AgentStates
from database import db_manager

logger = logging.getLogger(__name__)

agent_support_router = Router()

@agent_support_router.callback_query(F.data.startswith("agentreply_"))
async def agent_reply_start(callback: types.CallbackQuery, state: FSMContext):
    """Starts the reply workflow for an agent responding to a support ticket."""
    await callback.answer()
    ticket_id = int(callback.data.split("_")[1])
    
    ticket = await db_manager.get_support_ticket(ticket_id)
    if not ticket:
        return await callback.answer("❌ این تیکت در سیستم یافت نشد.", show_alert=True)
        
    if ticket['status'] == 'answered':
        return await callback.answer("⚠️ به این تیکت قبلاً پاسخ داده شده است.", show_alert=True)
        
    await state.clear()
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(AgentStates.waiting_for_reply)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو پاسخ", callback_data="cancel_reply")
    
    prompt_text = (
        f"✍️ <b>پاسخ به تیکت #{ticket_id}</b>\n\n"
        "لطفاً پاسخ خود را تایپ و ارسال کنید.\n"
        "(ارسال متن، عکس، فایل، ویدیو یا وویس مجاز است):"
    )
    await callback.message.answer(prompt_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@agent_support_router.callback_query(F.data == "cancel_reply")
async def cancel_reply(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ عملیات ارسال پاسخ به کاربر لغو شد.")

@agent_support_router.message(AgentStates.waiting_for_reply)
async def agent_reply_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    if not ticket_id:
        await state.clear()
        return
        
    ticket = await db_manager.get_support_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ تیکت در دیتابیس یافت نشد.")
        await state.clear()
        return
        
    user_id = ticket['user_id']
    user_msg_id = ticket['user_message_id']
    dept_id = ticket['department_id']
    
    # Retrieve department name
    dept_name = "عمومی"
    if dept_id:
        dept = await db_manager.get_department(dept_id)
        if dept:
            dept_name = dept['name']
            
    # Original user message text
    user_initial_text = ticket['text_or_caption'] or "پیام کاربر"
    agent_text = message.text or message.caption or (message.voice and "[پیام صوتی پشتیبان]") or "پاسخ پشتیبان"
    
    # Escape HTML to prevent injection and rendering errors
    escaped_dept_name = html.escape(str(dept_name))
    escaped_user_text = html.escape(str(user_initial_text))
    escaped_agent_text = html.escape(str(agent_text))
    
    # Threaded UI Format with Telegram expandable blockquote
    formatted_html = (
        f"📬 <b>پاسخ جدید از واحد پشتیبانی {escaped_dept_name}</b>\n\n"
        f"<blockquote expandable>{escaped_user_text}</blockquote>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💡 <b>پاسخ پشتیبان:</b>\n"
        f"{escaped_agent_text}"
    )
    
    # Interactive reply button for the user
    user_reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✍️ پاسخ دادن", callback_data=f"user_reply_ticket_{ticket_id}")
        ]]
    )
    
    bot = message.bot
    
    # Helper to send message with fallback if reply_to_message_id fails (e.g. deleted user message)
    async def _send_to_user(reply_to: int = None):
        if message.photo:
            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=formatted_html,
                reply_markup=user_reply_markup,
                reply_to_message_id=reply_to,
                parse_mode="HTML"
            )
        elif message.document:
            await bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=formatted_html,
                reply_markup=user_reply_markup,
                reply_to_message_id=reply_to,
                parse_mode="HTML"
            )
        elif message.video:
            await bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=formatted_html,
                reply_markup=user_reply_markup,
                reply_to_message_id=reply_to,
                parse_mode="HTML"
            )
        elif message.voice:
            # If caption fits within 1024 chars send with voice, otherwise voice + text
            if len(formatted_html) <= 1024:
                await bot.send_voice(
                    chat_id=user_id,
                    voice=message.voice.file_id,
                    caption=formatted_html,
                    reply_markup=user_reply_markup,
                    reply_to_message_id=reply_to,
                    parse_mode="HTML"
                )
            else:
                await bot.send_voice(chat_id=user_id, voice=message.voice.file_id, reply_to_message_id=reply_to)
                await bot.send_message(
                    chat_id=user_id,
                    text=formatted_html,
                    reply_markup=user_reply_markup,
                    parse_mode="HTML"
                )
        elif message.audio:
            await bot.send_audio(
                chat_id=user_id,
                audio=message.audio.file_id,
                caption=formatted_html,
                reply_markup=user_reply_markup,
                reply_to_message_id=reply_to,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=formatted_html,
                reply_markup=user_reply_markup,
                reply_to_message_id=reply_to,
                parse_mode="HTML"
            )
            
    try:
        # Attempt native reply first
        try:
            await _send_to_user(reply_to=user_msg_id)
        except Exception as reply_err:
            logger.warning(f"Native reply to msg {user_msg_id} failed: {reply_err}. Retrying without reply_to...")
            await _send_to_user(reply_to=None)
            
        # Update ticket status in DB
        await db_manager.update_support_ticket_answered(ticket_id, message.message_id)
        await db_manager.add_support_message(
            ticket_id=ticket_id,
            sender_id=message.from_user.id,
            sender_role='agent',
            message_id=message.message_id,
            text=agent_text
        )
        
        await message.answer(
            f"✅ پاسخ شما با موفقیت به همراه نقل‌قول سوال برای کاربر (شناسه: <code>{user_id}</code>) ارسال شد.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error forwarding agent reply to user {user_id} for ticket {ticket_id}: {e}", exc_info=True)
        await message.answer(f"❌ خطا در ارسال پاسخ به کاربر:\n{e}")
        
    await state.clear()
