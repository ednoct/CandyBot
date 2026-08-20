"""
admin.py
--------
Module containing functionalities for admin.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import ADMIN_IDS # Fixed relative import for config to resolve startup crash

admin_router = Router()

# === ADMIN FILTER ===
def is_admin(message: types.Message):
    """Handles is admin."""
    return message.chat.id in ADMIN_IDS

# === HELPER: BUILD ADMIN KEYBOARD ===
def _admin_keyboard():
    """Handles  admin keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📁 مدیریت پلن‌ها", callback_data="admin_manage_plans")
    builder.button(text="👥 مدیریت کاربران", callback_data="admin_users")
    builder.button(text="💎 مالی و درگاه‌ها", callback_data="admin_finance")
    builder.button(text="⚙️ تنظیمات عمومی", callback_data="admin_settings")
    builder.button(text="🏬 تنظیمات فروشگاه", callback_data="admin_shop")
    builder.button(text="💬 پشتیبانی", callback_data="admin_support")
    builder.button(text="📈 آمار و گزارشات", callback_data="admin_reports")
    builder.button(text="🖥 مدیریت ثنا", callback_data="admin_xui")
    builder.adjust(2, 2, 2, 2)
    return builder

# === ROUTER: /sudo COMMAND — SECURE ADMIN ENTRY ===
@admin_router.message(Command("sudo"))
async def sudo_panel(message: types.Message):
    """
    Secure admin entry point. Only users listed in ADMIN_IDS can access the panel.
    The old /admin command has been removed. Admins must use /sudo.
    """
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ شما دسترسی به این بخش ندارید.")
        return

    builder = _admin_keyboard()
    text = "💎 <b>مدیریت پیشرفته کندی (Candy Admin)</b>\n\nلطفا بخش مورد نظر را انتخاب کنید:"
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# === ROUTER: ADMIN PANEL (callback from within admin menus only) ===
@admin_router.callback_query(F.data == "admin_panel_start")
async def admin_panel_callback(callback: types.CallbackQuery):
    """Handles admin panel callback."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    builder = _admin_keyboard()
    text = "💎 <b>مدیریت پیشرفته کندی (Candy Admin)</b>\n\nلطفا بخش مورد نظر را انتخاب کنید:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: types.CallbackQuery):
    """Handles admin back handler."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    builder = _admin_keyboard()
    text = "💎 <b>مدیریت پیشرفته کندی (Candy Admin)</b>\n\nلطفا بخش مورد نظر را انتخاب کنید:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
