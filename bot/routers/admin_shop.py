"""
admin_shop.py
-------------
Module containing functionalities for admin_shop.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from database import db_manager

admin_shop_router = Router()

# === ROUTER: SHOP MENU ===
@admin_shop_router.callback_query(F.data == "admin_shop")
async def shop_menu(callback: types.CallbackQuery):
    """Handles shop menu."""
    if not is_admin(callback.message): return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1)
    
    await callback.message.edit_text("🏬 **تنظیمات فروشگاه**", reply_markup=builder.as_markup(), parse_mode="Markdown")


