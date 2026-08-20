"""
states.py
---------
Module containing functionalities for states.
"""
# === IMPORTS ===
from aiogram.fsm.state import State, StatesGroup

# === FSM STATES: ADMIN ===
class AdminStates(StatesGroup):
    """Class representing AdminStates."""
    waiting_for_plan_name = State()
    waiting_for_admin_description = State()
    waiting_for_time_days = State()
    waiting_for_traffic_gb = State()
    waiting_for_fast_pricing = State()
    waiting_for_cargo_stock = State()
    waiting_for_channel_remark = State()
    waiting_for_channel_url = State()
    waiting_for_admin_id = State()
    waiting_for_user_id = State()
    waiting_for_add_balance = State()
    waiting_for_reduce_balance = State()
    waiting_for_card_number = State()

    waiting_for_exclude_id = State()
    waiting_for_remove_exclude_id = State()
    waiting_for_min_max_limit = State()
    waiting_for_crypto_address = State()
    waiting_for_transfer_target_id = State()
    waiting_for_qr_background = State()
    waiting_for_app_name = State()
    waiting_for_app_url = State()
    # === XUI Panel Management (مدیریت ثنا) ===
    waiting_for_panel_url = State()
    waiting_for_panel_token = State()
    waiting_for_panel_inbound_ids = State()
    waiting_for_panel_ip_limit = State()

# === FSM STATES: CHECKOUT ===
class CheckoutStates(StatesGroup):
    """Class representing CheckoutStates."""
    waiting_for_license_note = State()  # User note before the time/traffic calculator
    waiting_for_discount_code = State()
    waiting_for_gift_code = State()

# === FSM STATES: USER ===
class UserStates(StatesGroup):
    """Class representing UserStates."""
    waiting_for_charge_amount = State()
    waiting_for_feedback_comment = State()

# === FSM STATES: SUPPORT ===
class SupportStates(StatesGroup):
    """Class representing SupportStates."""
    waiting_for_user_message = State()
    waiting_for_admin_reply = State()

