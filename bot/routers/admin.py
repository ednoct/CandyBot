# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .config import ADMIN_IDS

admin_router = Router()

# === ADMIN FILTER ===
def is_admin(message: types.Message):
    return message.from_user.id in ADMIN_IDS

# === ROUTER: ADMIN PANEL ===
@admin_router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📁 مدیریت پلن‌ها", callback_data="admin_manage_plans")
    builder.button(text="👥 مدیریت کاربران", callback_data="admin_users")
    builder.button(text="💎 مالی و درگاه‌ها", callback_data="admin_finance")
    builder.button(text="⚙️ تنظیمات عمومی", callback_data="admin_settings")
    builder.button(text="🏬 تنظیمات فروشگاه", callback_data="admin_shop")
    builder.button(text="📚 آموزش و پشتیبانی", callback_data="admin_support")
    builder.button(text="📈 آمار و گزارشات", callback_data="admin_reports")
    builder.adjust(2, 2, 2, 1)
    
    text = "💎 **مدیریت پیشرفته کندی (Candy Admin)**\n\nلطفا بخش مورد نظر را انتخاب کنید:"
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_router.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📁 مدیریت پلن‌ها", callback_data="admin_manage_plans")
    builder.button(text="👥 مدیریت کاربران", callback_data="admin_users")
    builder.button(text="💎 مالی و درگاه‌ها", callback_data="admin_finance")
    builder.button(text="⚙️ تنظیمات عمومی", callback_data="admin_settings")
    builder.button(text="🏬 تنظیمات فروشگاه", callback_data="admin_shop")
    builder.button(text="📚 آموزش و پشتیبانی", callback_data="admin_support")
    builder.button(text="📈 آمار و گزارشات", callback_data="admin_reports")
    builder.adjust(2, 2, 2, 1)
    
    text = "💎 **مدیریت پیشرفته کندی (Candy Admin)**\n\nلطفا بخش مورد نظر را انتخاب کنید:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
