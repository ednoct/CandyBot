# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ...database import db_manager

admin_shop_router = Router()

# === ROUTER: SHOP MENU ===
@admin_shop_router.callback_query(F.data == "admin_shop")
async def shop_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    status_on = "✅"
    status_off = "❌"
    
    builder = InlineKeyboardBuilder()
    
    builder.button(text="وضعیت خرید عمده:", callback_data="none")
    builder.button(text=status_off, callback_data="toggle_bulk_buy")
    
    builder.button(text="کپی شماره کارت:", callback_data="none")
    builder.button(text=status_on, callback_data="toggle_copy_cart")
    
    builder.button(text="تسویه بدهی:", callback_data="none")
    builder.button(text=status_off, callback_data="toggle_debt")
    
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 1)
    
    await callback.message.edit_text("🏬 **تنظیمات فروشگاه**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_shop_router.callback_query(F.data.startswith("toggle_"))
async def handle_shop_toggles(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    # Skip if it is a finance toggle
    if "fin_" in callback.data: return
    
    await callback.answer("🏬 وضعیت فروشگاه تغییر کرد (Mock).", show_alert=True)
    await shop_menu(callback)
