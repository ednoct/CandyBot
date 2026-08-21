"""
admin_free_trial.py
-------------------
Admin router for managing free trial settings.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_free_trial_router = Router()

# ============================================================
# === FREE TRIAL SETTINGS ===
# ============================================================

@admin_free_trial_router.callback_query(F.data == "admin_free_trial")
async def free_trial_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    # Fetch settings
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        async def get_s(k, default=""):
            async with db.execute("SELECT value FROM settings WHERE key=?", (k,)) as c:
                r = await c.fetchone()
                return r[0] if r else default
                
        enabled = await get_s("free_test_enabled", "0")
        gb = await get_s("free_test_gb", "1")
        days = await get_s("free_test_days", "1")
        limit = await get_s("free_test_daily_limit", "50")
        panel_id = await get_s("free_test_panel_id", "0")
        
    builder = InlineKeyboardBuilder()
    
    # Toggle button
    if enabled == "1":
        builder.button(text="🟢 وضعیت: فعال (کلیک برای غیرفعال‌سازی)", callback_data="ft_toggle")
    else:
        builder.button(text="🔴 وضعیت: غیرفعال (کلیک برای فعال‌سازی)", callback_data="ft_toggle")
        
    builder.button(text=f"حجم: {gb} گیگابایت", callback_data="ft_set_gb")
    builder.button(text=f"زمان: {days} روز", callback_data="ft_set_days")
    builder.button(text=f"ظرفیت روزانه: {limit} عدد", callback_data="ft_set_limit")
    builder.button(text=f"انتخاب پنل (ID: {panel_id})", callback_data="ft_select_panel")
    builder.button(text="🔙 بازگشت", callback_data="admin_settings")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "🆓 <b>مدیریت سرویس تست رایگان</b>\n\nتنظیمات تست رایگان را از گزینه‌های زیر تغییر دهید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@admin_free_trial_router.callback_query(F.data == "ft_toggle")
async def free_trial_toggle(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key='free_test_enabled'") as c:
            r = await c.fetchone()
            curr = r[0] if r else "0"
        new_val = "0" if curr == "1" else "1"
        await db.execute("UPDATE settings SET value=? WHERE key='free_test_enabled'", (new_val,))
        await db.commit()
    await free_trial_menu(callback)

@admin_free_trial_router.callback_query(F.data == "ft_set_gb")
async def free_trial_set_gb(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_free_trial_gb)
    await callback.message.edit_text("حجم تست رایگان را به گیگابایت وارد کنید (مثلا 1):")

@admin_free_trial_router.message(AdminStates.waiting_for_free_trial_gb)
async def free_trial_save_gb(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    await db_manager.update_setting("free_test_gb", message.text)
    await state.clear()
    await message.answer("✅ ذخیره شد.")

@admin_free_trial_router.callback_query(F.data == "ft_set_days")
async def free_trial_set_days(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_free_trial_days)
    await callback.message.edit_text("تعداد روز اعتبار تست رایگان را وارد کنید (مثلا 1):")

@admin_free_trial_router.message(AdminStates.waiting_for_free_trial_days)
async def free_trial_save_days(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    await db_manager.update_setting("free_test_days", message.text)
    await state.clear()
    await message.answer("✅ ذخیره شد.")

@admin_free_trial_router.callback_query(F.data == "ft_set_limit")
async def free_trial_set_limit(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_free_trial_daily_limit)
    await callback.message.edit_text("ظرفیت مجاز صدور تست رایگان در هر روز را وارد کنید (مثلا 50):")

@admin_free_trial_router.message(AdminStates.waiting_for_free_trial_daily_limit)
async def free_trial_save_limit(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    if not message.text.isdigit(): return await message.answer("لطفا فقط عدد وارد کنید.")
    await db_manager.update_setting("free_test_daily_limit", message.text)
    await state.clear()
    await message.answer("✅ ذخیره شد.")

@admin_free_trial_router.callback_query(F.data == "ft_select_panel")
async def free_trial_select_panel(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    panels = await db_manager.get_xui_panels()
    if not panels:
        return await callback.answer("هیچ پنل ثنا ثبت نشده است.", show_alert=True)
        
    builder = InlineKeyboardBuilder()
    for p in panels:
        builder.button(text=f"پنل {p['id']} - {p['url']}", callback_data=f"ft_set_panel_{p['id']}")
    builder.button(text="🔙 بازگشت", callback_data="admin_free_trial")
    builder.adjust(1)
    await callback.message.edit_text("لطفا پنلی که اکانت های تست روی آن ساخته میشوند را انتخاب کنید:", reply_markup=builder.as_markup())

@admin_free_trial_router.callback_query(F.data.startswith("ft_set_panel_"))
async def free_trial_save_panel(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    pid = callback.data.split("_")[3]
    await db_manager.update_setting("free_test_panel_id", pid)
    await callback.answer("✅ پنل تنظیم شد.", show_alert=True)
    await free_trial_menu(callback)
