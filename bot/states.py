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
    waiting_for_min_max_limit = State()
    waiting_for_crypto_address = State()
    waiting_for_transfer_target_id = State()
    waiting_for_qr_background = State()
    
    # === User Management (New Features) ===
    waiting_for_global_charge_amount = State()
    waiting_for_trial_charge_amount = State()
    waiting_for_order_id = State()
    waiting_for_global_traffic_days = State()
    waiting_for_global_traffic_gb = State()
    
    waiting_for_admin_user_msg = State()
    waiting_for_fast_gift_value = State()
    # === XUI Panel Management (مدیریت ثنا) ===
    waiting_for_panel_name = State()
    waiting_for_panel_url = State()
    waiting_for_panel_sub_link = State()
    waiting_for_panel_token = State()
    waiting_for_panel_inbound_ids = State()
    waiting_for_panel_ip_limit = State()

    # === Admin Discounts & Gifts ===
    waiting_for_admin_discount_code = State()
    waiting_for_admin_discount_type = State()
    waiting_for_admin_discount_value = State()
    waiting_for_admin_discount_max_uses = State()
    waiting_for_admin_discount_expiry = State()
    waiting_for_admin_discount_user_id = State()
    
    waiting_for_admin_gift_code = State()
    waiting_for_admin_gift_value = State()
    waiting_for_admin_gift_max_uses = State()
    waiting_for_admin_gift_expiry = State()
    waiting_for_admin_gift_user_id = State()

    # === Free Trial ===
    waiting_for_free_trial_gb = State()
    waiting_for_free_trial_days = State()
    waiting_for_free_trial_daily_limit = State()

    # === Referral System ===
    waiting_for_referral_value = State()

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
    waiting_for_department = State()
    waiting_for_user_message = State()
    waiting_for_admin_reply = State()

# === FSM STATES: ADMIN SUPPORT ===
class AdminSupportStates(StatesGroup):
    waiting_for_dept_name = State()
    waiting_for_agent_id_dept = State()
    waiting_for_agent_id = State()
    waiting_for_faq_text = State()
    waiting_for_remove_dept = State()

# === FSM STATES: AGENT ===
class AgentStates(StatesGroup):
    waiting_for_reply = State()

# === FSM STATES: BROADCAST ===
class BroadcastStates(StatesGroup):
    waiting_for_audience = State()
    waiting_for_message = State()
    waiting_for_pin_decision = State()
