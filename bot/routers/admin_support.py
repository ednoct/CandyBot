"""
admin_support.py
----------------
Module containing functionalities for admin support management.
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.states import AdminSupportStates
from bot.routers.admin import is_admin
from database import db_manager
from utils.ui_helpers import send_bottom_message

admin_support_router = Router()

# Main support management menu
@admin_support_router.callback_query(F.data == "admin_support")
async def admin_support(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await callback.answer()
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    
    # Row 1
    builder.row(InlineKeyboardButton(text="👤 تنظیم آیدی پشتیبانی", callback_data="admin_support_set_agent"))
    # Row 2 (Right to left: Add | Remove)
    builder.row(
        InlineKeyboardButton(text="🔼 اضافه کردن دپارتمان", callback_data="admin_support_add_dept"),
        InlineKeyboardButton(text="🔽 حذف کردن دپارتمان", callback_data="admin_support_remove_dept")
    )
    # Row 3
    builder.row(
        InlineKeyboardButton(text="📝 تنظیم متن سوالات متداول", callback_data="admin_support_set_faq")
    )
    # Row 4
    builder.row(
        InlineKeyboardButton(text="▶️ بازگشت به منوی قبل", callback_data="admin_settings", style="danger"),
        InlineKeyboardButton(text="🏠 بازگشت به منوی مدیریت", callback_data="admin_back", style="danger")
    )
    
    text = "🏢 <b>مدیریت دپارتمان‌های پشتیبانی</b>\n\nلطفاً یک گزینه را انتخاب کنید:"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

# Add department
@admin_support_router.callback_query(F.data == "admin_support_add_dept")
async def add_dept_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await callback.answer()
    await state.set_state(AdminSupportStates.waiting_for_dept_name)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
    
    text = "🏢 لطفاً <b>نام دپارتمان جدید</b> را وارد کنید (مثلاً: فنی، مالی، فروش):"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_support_router.message(AdminSupportStates.waiting_for_dept_name)
async def add_dept_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    name = message.text.strip()
    
    success = await db_manager.add_department(name)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به مدیریت پشتیبانی", callback_data="admin_support", style="danger")
    
    if success:
        await message.answer(f"✅ دپارتمان «<b>{name}</b>» با موفقیت اضافه شد.", reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer("❌ خطا در افزودن دپارتمان (ممکن است نام تکراری باشد).", reply_markup=builder.as_markup(), parse_mode="HTML")
        
    await state.clear()

# Remove department
@admin_support_router.callback_query(F.data == "admin_support_remove_dept")
async def remove_dept_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await callback.answer()
    await state.clear()
    
    depts = await db_manager.get_departments()
    
    builder = InlineKeyboardBuilder()
    for d in depts:
        builder.button(text=f"🗑 {d['name']}", callback_data=f"deldept_{d['id']}")
    builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
    builder.adjust(1)
    
    text = "🗑 کدام دپارتمان را می‌خواهید حذف کنید؟"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

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
    await callback.answer()
    await state.clear()
    
    depts = await db_manager.get_departments()
    if not depts:
        await db_manager.add_department("عمومی")
        depts = await db_manager.get_departments()
    
    # If there is only one department, auto-select it directly to avoid confusing UX
    if len(depts) == 1:
        d = depts[0]
        await state.update_data(target_dept_id=d['id'])
        await state.set_state(AdminSupportStates.waiting_for_agent_id)
        
        agent = d['support_user_id']
        status = f"<code>{agent}</code>" if agent else "تنظیم نشده (بدون پشتیبان اختصاصی)"
        
        builder = InlineKeyboardBuilder()
        if agent:
            builder.button(text="🗑 حذف پشتیبان فعلی (بدون پشتیبان)", callback_data="clear_agent")
        builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
        builder.adjust(1)
        
        text = (
            f"🏢 <b>تنظیم آیدی پشتیبان دپارتمان {d['name']}</b>\n\n"
            f"👤 <b>پشتیبان فعلی:</b> {status}\n\n"
            "⚠️ <b>توجه مهم:</b> قبل از تنظیم آیدی، مطمئن شوید که پشتیبان حداقل یک‌بار ربات را استارت کرده باشد.\n\n"
            "لطفاً <b>آیدی عددی (Chat ID)</b> پشتیبان را ارسال کنید:"
        )
        await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return
        
    # Multiple departments: show selection list
    builder = InlineKeyboardBuilder()
    for d in depts:
        agent = d['support_user_id']
        status = f"(تنظیم شده: {agent})" if agent else "(بدون پشتیبان)"
        builder.button(text=f"🏢 {d['name']} {status}", callback_data=f"setagentdept_{d['id']}")
    builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
    builder.adjust(1)
    
    text = "🏢 دپارتمان مورد نظر را برای تنظیم آیدی پشتیبان انتخاب کنید:"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_support_router.callback_query(F.data.startswith("setagentdept_"))
async def set_agent_dept_selected(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await callback.answer()
    dept_id = int(callback.data.split("_")[1])
    dept = await db_manager.get_department(dept_id)
    
    await state.update_data(target_dept_id=dept_id)
    await state.set_state(AdminSupportStates.waiting_for_agent_id)
    
    dept_name = dept['name'] if dept else "انتخاب‌شده"
    agent = dept['support_user_id'] if dept else None
    status = f"<code>{agent}</code>" if agent else "تنظیم نشده (بدون پشتیبان اختصاصی)"
    
    builder = InlineKeyboardBuilder()
    if agent:
        builder.button(text="🗑 حذف پشتیبان فعلی (بدون پشتیبان)", callback_data="clear_agent")
    builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
    builder.adjust(1)
    
    text = (
        f"🏢 <b>تنظیم آیدی پشتیبان دپارتمان {dept_name}</b>\n\n"
        f"👤 <b>پشتیبان فعلی:</b> {status}\n\n"
        "⚠️ <b>توجه مهم:</b> قبل از تنظیم آیدی، مطمئن شوید که پشتیبان حداقل یک‌بار ربات را استارت کرده باشد.\n\n"
        "لطفاً <b>آیدی عددی (Chat ID)</b> پشتیبان را ارسال کنید:"
    )
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_support_router.callback_query(F.data == "clear_agent")
async def clear_agent_process(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    data = await state.get_data()
    dept_id = data.get("target_dept_id")
    if dept_id:
        await db_manager.set_department_support_user(dept_id, None)
        await callback.answer("✅ پشتیبان اختصاصی این دپارتمان حذف شد.", show_alert=True)
    else:
        await callback.answer("❌ دپارتمان مشخص نیست.", show_alert=True)
    await admin_support(callback, state)

@admin_support_router.message(AdminSupportStates.waiting_for_agent_id)
async def set_agent_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    data = await state.get_data()
    dept_id = data.get("target_dept_id")
    
    if not dept_id:
        # Fallback to single department if available
        depts = await db_manager.get_departments()
        if depts:
            dept_id = depts[0]['id']
            
    if not dept_id:
        await message.answer("❌ خطای سیستمی: دپارتمان مشخص نیست. لطفاً مجدداً تلاش کنید.")
        await state.clear()
        return
        
    raw_text = message.text.strip() if message.text else ""
    try:
        user_id = int(raw_text)
        await db_manager.set_department_support_user(dept_id, user_id)
        dept = await db_manager.get_department(dept_id)
        dept_name = dept['name'] if dept else "مربوطه"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 بازگشت به مدیریت پشتیبانی", callback_data="admin_support", style="danger")
        
        await message.answer(
            f"✅ آیدی عددی <code>{user_id}</code> با موفقیت به‌عنوان پشتیبان دپارتمان «<b>{dept_name}</b>» ذخیره شد.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
        await message.answer("❌ لطفاً یک آیدی عددی معتبر ارسال کنید (فقط اعداد انگلیسی):", reply_markup=builder.as_markup())

# Set FAQ
@admin_support_router.callback_query(F.data == "admin_support_set_faq")
async def set_faq_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await callback.answer()
    await state.set_state(AdminSupportStates.waiting_for_faq_text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف", callback_data="admin_support", style="danger")
    
    text = "📝 متن جدید سوالات متداول (FAQ) را به صورت کامل تایپ کرده و ارسال کنید (پشتیبانی از فرمت‌های تلگرام مجاز است):"
    await send_bottom_message(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_support_router.message(AdminSupportStates.waiting_for_faq_text)
async def set_faq_process(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    faq_text = message.html_text or message.text or ""
    await db_manager.api_update_setting("faq_text", faq_text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به مدیریت پشتیبانی", callback_data="admin_support", style="danger")
    
    await message.answer("✅ متن سوالات متداول با موفقیت بروزرسانی شد.", reply_markup=builder.as_markup())
    await state.clear()
