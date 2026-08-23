"""
agent_support.py
----------------
Module containing functionalities for agent support management.
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from bot.states import AgentStates
from database import db_manager

agent_support_router = Router()

@agent_support_router.callback_query(F.data.startswith("agentreply_"))
async def agent_reply_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[1])
    
    # Check if the user is a valid agent for any department or an admin.
    # To isolate, we just allow anyone who receives this button to click it,
    # but we can verify if they are really an agent.
    
    ticket = await db_manager.get_support_ticket(ticket_id)
    if not ticket:
        return await callback.answer("❌ این تیکت در سیستم یافت نشد.", show_alert=True)
        
    if ticket['status'] == 'answered':
        return await callback.answer("⚠️ به این تیکت قبلاً پاسخ داده شده است.", show_alert=True)
        
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(AgentStates.waiting_for_reply)
    
    # Check if original message still exists, can't easily do it, so just reply.
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data="cancel_reply")
    
    await callback.message.answer("لطفاً پاسخ خود را بنویسید (متن، عکس، فایل مجاز است):", reply_markup=builder.as_markup())
    
@agent_support_router.callback_query(F.data == "cancel_reply")
async def cancel_reply(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("عملیات لغو شد.")
    
@agent_support_router.message(AgentStates.waiting_for_reply)
async def agent_reply_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    if not ticket_id:
        return await state.clear()
        
    ticket = await db_manager.get_support_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ تیکت یافت نشد.")
        return await state.clear()
        
    user_id = ticket['user_id']
    
    # Forward the reply to the user
    try:
        if message.photo or message.document or message.video or message.audio:
            await message.bot.copy_message(user_id, message.chat.id, message.message_id)
        else:
            text = f"📞 پاسخ پشتیبانی:\n\n{message.text}"
            await message.bot.send_message(user_id, text)
            
        await message.answer("✅ پاسخ شما با موفقیت برای کاربر ارسال شد.")
        
        # Update ticket status in DB
        await db_manager.update_support_ticket_answered(ticket_id, message.message_id)
        
        # Ideally, we should also edit the agent's original message to show "پاسخ داده شده".
        # We don't have the agent's original message ID in the DB (only the user's message ID),
        # but we can try to infer it or just leave it. If we wanted to, we could store it in the DB when we send it to the agent.
        
    except Exception as e:
        await message.answer(f"❌ خطا در ارسال پاسخ: {e}")
        
    await state.clear()
