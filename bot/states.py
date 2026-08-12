# === IMPORTS ===
from aiogram.fsm.state import State, StatesGroup

# === FSM STATES: ADMIN ===
class AdminStates(StatesGroup):
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
    waiting_for_app_name = State()
    waiting_for_app_url = State()
    waiting_for_exclude_id = State()
    waiting_for_remove_exclude_id = State()
    waiting_for_min_max_limit = State()
    waiting_for_tutorial_content = State()
    waiting_for_crypto_address = State()
    waiting_for_transfer_target_id = State()
    waiting_for_qr_background = State()
    waiting_for_lottery_prize = State()

# === FSM STATES: CHECKOUT ===
class CheckoutStates(StatesGroup):
    waiting_for_discount_code = State()
    waiting_for_gift_code = State()

# === FSM STATES: USER ===
class UserStates(StatesGroup):
    waiting_for_charge_amount = State()

# === FSM STATES: SUPPORT ===
class SupportStates(StatesGroup):
    waiting_for_user_message = State()
    waiting_for_admin_reply = State()
