# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from ..states import SupportStates
from ..config import ADMIN_IDS
from aiogram.utils.keyboard import InlineKeyboardBuilder

support_router = Router()

# === ROUTER: SUPPORT REQUEST ===
@support_router.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_for_user_message)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="main_menu")
    await callback.message.edit_text("لطفا پیام خود را برای بخش پشتیبانی ارسال کنید:", reply_markup=builder.as_markup())

@support_router.message(SupportStates.waiting_for_user_message)
async def process_support_msg(message: types.Message, state: FSMContext):
    await state.set_state(None)
    
    # Forward to all admins
    text = f"📨 پیام جدید از پشتیبانی:\nکاربر: {message.from_user.id}\nمتن:\n{message.text}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="پاسخ", callback_data=f"reply_{message.from_user.id}")
    
    # Use bot instance from message
    bot = message.bot
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=builder.as_markup())
        except:
            pass
            
    await message.answer("✅ پیام شما با موفقیت برای تیم پشتیبانی ارسال شد.")

# === ROUTER: ADMIN REPLY ===
@support_router.callback_query(F.data.startswith('reply_'))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split('_')[1])
    await state.update_data(reply_to_user_id=user_id)
    await state.set_state(SupportStates.waiting_for_admin_reply)
    await callback.message.answer(f"لطفا پاسخ خود را برای کاربر {user_id} بنویسید:")

@support_router.message(SupportStates.waiting_for_admin_reply)
async def admin_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('reply_to_user_id')
    if not user_id:
        return await state.set_state(None)
        
    text = f"📞 پاسخ پشتیبانی:\n\n{message.text}"
    try:
        await message.bot.send_message(user_id, text)
        await message.answer("✅ پاسخ شما با موفقیت ارسال شد.")
    except Exception as e:
        await message.answer(f"خطا در ارسال: {e}")
        
    await state.set_state(None)
