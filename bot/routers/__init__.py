"""
__init__.py
-----------
Module containing functionalities for __init__.
"""
# === IMPORTS EXPORTS ===
# === IMPORTS ===
from .admin import admin_router
from .admin_settings import admin_settings_router
from .admin_finance import admin_finance_router
from .admin_users import admin_users_router
from .admin_shop import admin_shop_router
from .admin_plans import admin_plans_router
from .admin_reports import admin_reports_router
from .admin_xui import admin_xui_router
from .checkout import checkout_router
from .payment import payment_router
from .support import support_router
from .user import user_router

__all__ = [
    "admin_router",
    "admin_settings_router",
    "admin_finance_router",
    "admin_users_router",
    "admin_shop_router",
    "admin_plans_router",
    "admin_reports_router",
    "admin_xui_router",
    "checkout_router",
    "payment_router",
    "support_router",
    "user_router"
]
