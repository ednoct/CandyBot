"""
admin_support.py
----------------
Module containing functionalities for admin support management.
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.states import AdminSupportStates
from bot.routers.admin import is_admin
from database import db_manager

admin_support_router = Router()

# Main support management menu
@admin_support_router.callback_query(F.data == "admin_support")
async def admin_support(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    from aiogram.types import InlineKeyboardButton
    
    # Row 1
    builder.row(InlineKeyboardButton(text="👤 تنظیم آیدی پشتیبانی", callback_data="admin_support_set_agent"))
    # Row 2 (Right to left in code for RTL: Add | Remove)
    builder.row(
        InlineKeyboardButton(text="🔼 اضافه کردن دپارتمان", callback_data="admin_support_add_dept"),
        InlineKeyboardButton(text="🔽 حذف کردن دپارتمان", callback_data="admin_support_remove_dept")
    )
    # Row 3 (Right to left: Back to previous | Back to admin menu)
    builder.row(
        InlineKeyboardButton(text="📝 تنظیم متن سوالات متداول", callback_data="admin_support_set_faq")
    )
    builder.row(
        InlineKeyboardButton(text="▶️ بازگشت به منوی قبل", callback_data="admin_settings"),
        InlineKeyboardButton(text="🏠 بازگشت به منوی مدیریت", callback_data="admin_back")
    )
    
    text = "🏢 **مدیریت دپارتمان‌های پشتیبانی**\n\nیک گزینه را انتخاب کنید:"
    
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# Add department
@admin_support_router.callback_query(F.data == "admin_support_add_dept")
async def add_dept_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminSupportStates.waiting_for_dept_name)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="admin_support")
    await callback.message.edit_text("لطفاً نام دپارتمان جدید را وارد کنید (مثلاً: فنی):", reply_markup=builder.as_markup())

@admin_support_router.message(AdminSupportStates.waiting_for_dept_name)
async def add_dept_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    name = message.text.strip()
    
    success = await db_manager.add_department(name)
    if success:
        await message.answer(f"✅ دپارتمان '{name}' با موفقیت اضافه شد.")
    else:
        await message.answer("❌ خطا در افزودن دپارتمان (ممکن است نام تکراری باشد).")
        
    await state.clear()

# Remove department
@admin_support_router.callback_query(F.data == "admin_support_remove_dept")
async def remove_dept_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    depts = await db_manager.get_departments()
    
    builder = InlineKeyboardBuilder()
    for d in depts:
        builder.button(text=d['name'], callback_data=f"deldept_{d['id']}")
    builder.button(text="🔙 انصراف", callback_data="admin_support")
    builder.adjust(1)
    
    await callback.message.edit_text("کدام دپارتمان را می‌خواهید حذف کنید؟", reply_markup=builder.as_markup())

@admin_support_router.callback_query(F.data.startswith("deldept_"))
async def remove_dept_process(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    dept_id = int(callback.data.split("_")[1])
    
    await db_manager.remove_department(dept_id)
    await callback.answer("✅ دپارتمان با موفقیت حذف شد.", show_alert=True)
    await admin_support(callback, state)

# Set agent
@admin_support_router.callback_query(F.data == "admin_support_set_agent")
async def set_agent_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    depts = await db_manager.get_departments()
    
    builder = InlineKeyboardBuilder()
    for d in depts:
        agent = d['support_user_id']
        status = f"(تنظیم شده: {agent})" if agent else "(بدون پشتیبان اختصاصی)"
        builder.button(text=f"{d['name']} {status}", callback_data=f"setagentdept_{d['id']}")
    builder.button(text="🔙 انصراف", callback_data="admin_support")
    builder.adjust(1)
    
    await callback.message.edit_text("دپارتمان مورد نظر را برای تنظیم آیدی پشتیبان انتخاب کنید:", reply_markup=builder.as_markup())

@admin_support_router.callback_query(F.data.startswith("setagentdept_"))
async def set_agent_dept_selected(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    dept_id = int(callback.data.split("_")[1])
    await state.update_data(target_dept_id=dept_id)
    await state.set_state(AdminSupportStates.waiting_for_agent_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="حذف پشتیبان فعلی (بدون پشتیبان)", callback_data="clear_agent")
    builder.button(text="🔙 انصراف", callback_data="admin_support")
    builder.adjust(1)
    
    text = (
        "⚠️ **توجه: قبل از تنظیم آیدی، مطمئن شوید که پشتیبان حداقل یک‌بار ربات را استارت کرده باشد.**\n\n"
        "لطفاً آیدی عددی پشتیبان را ارسال کنید:"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_support_router.callback_query(F.data == "clear_agent")
async def clear_agent_process(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    data = await state.get_data()
    dept_id = data.get("target_dept_id")
    if dept_id:
        await db_manager.set_department_support_user(dept_id, None)
        await callback.answer("✅ پشتیبان اختصاصی این دپارتمان حذف شد.", show_alert=True)
    await admin_support(callback, state)

@admin_support_router.message(AdminSupportStates.waiting_for_agent_id)
async def set_agent_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    data = await state.get_data()
    dept_id = data.get("target_dept_id")
    
    try:
        user_id = int(message.text.strip())
        await db_manager.set_department_support_user(dept_id, user_id)
        await message.answer(f"✅ آیدی {user_id} با موفقیت به‌عنوان پشتیبان این دپارتمان تنظیم شد.")
    except ValueError:
        await message.answer("❌ لطفاً یک آیدی عددی معتبر ارسال کنید.")
        
    await state.clear()

# Set FAQ
@admin_support_router.callback_query(F.data == "admin_support_set_faq")
async def set_faq_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminSupportStates.waiting_for_faq_text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="admin_support")
    
    await callback.message.edit_text("متن جدید سوالات متداول (FAQ) را به صورت کامل تایپ کرده و ارسال کنید:", reply_markup=builder.as_markup())

@admin_support_router.message(AdminSupportStates.waiting_for_faq_text)
async def set_faq_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    faq_text = message.html_text
    await db_manager.api_update_setting("faq_text", faq_text)
    await message.answer("✅ متن سوالات متداول با موفقیت بروزرسانی شد.")
    await state.clear()
