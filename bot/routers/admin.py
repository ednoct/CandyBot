"""
admin.py
--------
Admin panel entry point with Live Action Center dashboard.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import ADMIN_IDS
from database import db_manager

admin_router = Router()

# === ADMIN FILTER ===
def is_admin(message: types.Message):
    """Handles is admin."""
    return message.chat.id in ADMIN_IDS


# === HELPER: BUILD LIVE ADMIN DASHBOARD TEXT ===
async def _build_admin_dashboard_text(counts: dict) -> str:
    """
    Builds the 'Live Action Center' header shown above the admin menu.
    """
    op_mode = counts.get('op_mode', 'NORMAL')
    mode_icons = {
        'NORMAL':        '🟢 فعال',
        'SALES_PAUSED':  '🟡 فروش متوقف',
        'MAINTENANCE':   '🔴 تعمیرات',
    }
    mode_label = mode_icons.get(op_mode, op_mode)

    pending_receipts    = counts.get('pending_receipts', 0)
    pending_settlements = counts.get('pending_settlements', 0)
    pending_activations = counts.get('pending_activations', 0)
    open_tickets        = counts.get('open_tickets', 0)
    today_count         = counts.get('today_count', 0)
    today_amount        = counts.get('today_amount', 0)

    # Action Required section — only show non-zero items
    action_lines = []
    if pending_receipts > 0:
        action_lines.append(f"  💳 فیش‌های کارت‌به‌کارت: <b>{pending_receipts}</b> مورد منتظر تایید")
    if pending_settlements > 0:
        action_lines.append(f"  💸 تسویه‌های نماینده: <b>{pending_settlements}</b> مورد منتظر پرداخت")
    if pending_activations > 0:
        action_lines.append(f"  🔓 فعالسازی تسویه: <b>{pending_activations}</b> درخواست جدید")
    if open_tickets > 0:
        action_lines.append(f"  🎫 تیکت‌های پشتیبانی: <b>{open_tickets}</b> مورد بی‌پاسخ")

    if action_lines:
        action_block = "🔔 <b>صف اقدام (Action Required):</b>\n" + "\n".join(action_lines)
    else:
        action_block = "✅ <b>صف اقدام:</b> موردی برای رسیدگی وجود ندارد."

    text = (
        f"🎛 <b>مرکز فرماندهی کندی (Admin Cockpit)</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🚦 <b>وضعیت فروش:</b> {mode_label}\n\n"
        f"{action_block}\n\n"
        f"💰 <b>فروش امروز:</b> <b>{today_amount:,}</b> تومان"
        f" ({today_count} تراکنش)\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"بخش مورد نظر را انتخاب کنید:"
    )
    return text


def _badge(label: str, count: int) -> str:
    """Appends a red-circle badge to button label when count > 0."""
    if count > 0:
        return f"{label} ({count} 🔴)"
    return label


# === HELPER: BUILD ADMIN KEYBOARD WITH BADGES ===
async def _admin_keyboard(counts: dict | None = None):
    """Builds admin keyboard with smart notification badges."""
    if counts is None:
        counts = {}

    pending_receipts    = counts.get('pending_receipts', 0)
    pending_settlements = counts.get('pending_settlements', 0)
    pending_activations = counts.get('pending_activations', 0)
    open_tickets        = counts.get('open_tickets', 0)

    builder = InlineKeyboardBuilder()
    builder.button(text="📁 مدیریت پلن‌ها",      callback_data="admin_manage_plans")
    builder.button(text="👥 مدیریت کاربران",      callback_data="admin_users")
    builder.button(text="💎 مالی و درگاه‌ها",      callback_data="admin_finance")
    builder.button(text="⚙️ تنظیمات عمومی",       callback_data="admin_settings")
    builder.button(text="🏬 تنظیمات نمایندگان",   callback_data="admin_agent")
    builder.button(
        text=_badge("🎫 پشتیبانی", open_tickets),
        callback_data="admin_support"
    )
    builder.button(text="📈 آمار و گزارشات",       callback_data="admin_reports")
    builder.button(text="🖥 مدیریت ثنا",           callback_data="admin_xui")
    builder.adjust(2, 2, 2, 2)
    return builder


# === ROUTER: /sudo COMMAND — SECURE ADMIN ENTRY ===
@admin_router.message(Command("sudo"))
async def sudo_panel(message: types.Message):
    """
    Secure admin entry point. Only users listed in ADMIN_IDS can access the panel.
    Shows a live Action Center header with pending counters and smart badges.
    """
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ شما دسترسی به این بخش ندارید.")
        return

    try:
        counts = await db_manager.get_admin_dashboard_counts()
    except Exception:
        counts = {}

    text = await _build_admin_dashboard_text(counts)
    builder = await _admin_keyboard(counts)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === ROUTER: ADMIN PANEL (callback from within admin menus) ===
@admin_router.callback_query(F.data == "admin_panel_start")
async def admin_panel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Returns to admin panel with refreshed live counters."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    await state.clear()

    try:
        counts = await db_manager.get_admin_dashboard_counts()
    except Exception:
        counts = {}

    text = await _build_admin_dashboard_text(counts)
    builder = await _admin_keyboard(counts)
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            await callback.answer()
    await callback.answer()


@admin_router.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handles admin back — refreshes dashboard counters on return."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    await state.clear()

    try:
        counts = await db_manager.get_admin_dashboard_counts()
    except Exception:
        counts = {}

    text = await _build_admin_dashboard_text(counts)
    builder = await _admin_keyboard(counts)
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise
    await callback.answer()


# === NEUTRAL BUTTONS HANDLER (PREVENTS "QUERY IS TOO OLD") ===
@admin_router.callback_query(F.data.in_(["noop", "none"]))
async def handle_noop(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
