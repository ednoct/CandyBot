"""
support.py
----------
Module containing functionalities for user support.
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from bot.states import SupportStates
from bot.config import ADMIN_IDS
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db_manager
import jdatetime

support_router = Router()

@support_router.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery, state: FSMContext):
    """Handles support menu."""
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    from aiogram.types import InlineKeyboardButton
    
    # Row 1 (Right to left: FAQ | Support)
    builder.row(
        InlineKeyboardButton(text="🎟 ارسال پیام به پشتیبانی", callback_data="support_send_msg"),
        InlineKeyboardButton(text="❓ سوالات متداول", callback_data="support_faq")
    )
    # Row 2
    builder.row(InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    
    text = (
        "در دکمه زیر (سوالات متداول) سوالات پرتکرار شما آمده است.\n"
        "روی دکمه زیر کلیک کنید و در صورت نیافتن سوال خود روی دکمه پشتیبانی کلیک کنید."
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@support_router.callback_query(F.data == "support_faq")
async def support_faq(callback: types.CallbackQuery):
    faq_text = await db_manager.get_setting("faq_text", "متن سوالات متداول هنوز تنظیم نشده است.")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="support")
    
    await callback.message.edit_text(faq_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@support_router.callback_query(F.data == "support_send_msg")
async def support_send_msg_start(callback: types.CallbackQuery, state: FSMContext):
    depts = await db_manager.get_departments()
    
    if len(depts) <= 1:
        # Only 1 department, skip selection
        dept_id = depts[0]['id'] if depts else 0
        await state.update_data(target_dept_id=dept_id)
        await state.set_state(SupportStates.waiting_for_user_message)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 انصراف", callback_data="support")
        await callback.message.edit_text("لطفاً پیام (متن، عکس، فایل) خود را ارسال کنید:", reply_markup=builder.as_markup())
    else:
        # Multiple departments
        builder = InlineKeyboardBuilder()
        for d in depts:
            builder.button(text=d['name'], callback_data=f"seldept_{d['id']}")
        builder.button(text="🔙 انصراف", callback_data="support")
        builder.adjust(1)
        
        await callback.message.edit_text("کدام دپارتمان؟ لطفاً بخش مورد نظر خود را انتخاب کنید:", reply_markup=builder.as_markup())

@support_router.callback_query(F.data.startswith("seldept_"))
async def support_dept_selected(callback: types.CallbackQuery, state: FSMContext):
    dept_id = int(callback.data.split("_")[1])
    await state.update_data(target_dept_id=dept_id)
    await state.set_state(SupportStates.waiting_for_user_message)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="support")
    await callback.message.edit_text("لطفاً پیام (متن، عکس، فایل) خود را ارسال کنید:", reply_markup=builder.as_markup())

@support_router.message(SupportStates.waiting_for_user_message)
async def process_support_msg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get("target_dept_id", 0)
    
    await state.clear()
    
    # Get department info
    dept_name = "عمومی"
    agent_id = ADMIN_IDS[0] if ADMIN_IDS else None
    
    if dept_id > 0:
        dept = await db_manager.get_department(dept_id)
        if dept:
            dept_name = dept['name']
            if dept['support_user_id']:
                agent_id = dept['support_user_id']
                
    if not agent_id:
        await message.answer("❌ متاسفانه ادمینی برای پاسخگویی یافت نشد.")
        return
        
    # Get message content (text, caption, etc)
    text_or_caption = message.text or message.caption or "بدون متن"
    
    # Save to db
    ticket_id = await db_manager.create_support_ticket(
        user_id=message.from_user.id,
        department_id=dept_id,
        user_message_id=message.message_id,
        text_or_caption=text_or_caption
    )
    
    # Format current time
    now_shamsi = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
    username = message.from_user.username or "ندارد"
    
    msg_text = (
        f"📣 پشتیبان عزیز یک پیام از سمت کاربر برای شما ارسال گردید.\n"
        f"آیدی عددی کاربر: <code>{message.from_user.id}</code>\n"
        f"زمان ارسال: {now_shamsi}\n"
        f"وضعیت پیام: پاسخ داده نشده\n"
        f"نام کاربری کاربر: @{username}\n"
        f"نام دپارتمان: 🏢 {dept_name}\n\n"
        f"متن پیام:\n{text_or_caption}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="پاسخ به پیام", callback_data=f"agentreply_{ticket_id}")
    
    try:
        # Copy the original message to the agent first (if it's a photo/doc)
        if message.photo or message.document or message.video or message.audio:
            await message.bot.copy_message(agent_id, message.chat.id, message.message_id)
            
        await message.bot.send_message(
            agent_id, 
            msg_text, 
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await message.answer("✅ پیام شما با موفقیت برای تیم پشتیبانی ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ خطا در ارسال پیام به پشتیبان.")
