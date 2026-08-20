"""
admin_plans.py
--------------
Module containing functionalities for admin_plans.
"""
# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_plans_router = Router()


# ============================================================
# === ROUTER: MANAGE PLANS MAIN ===
# ============================================================

@admin_plans_router.callback_query(F.data == "admin_manage_plans")
async def manage_plans_menu(callback: types.CallbackQuery):
    """Handles manage plans menu."""
    if not is_admin(callback.message): return

    plans = await db_manager.get_plans()
    builder = InlineKeyboardBuilder()

    for p in plans:
        builder.button(text=f"📁 {p['name']}", callback_data=f"manageplan_{p['id']}")

    builder.button(text="➕ افزودن پلن جدید", callback_data="add_plan_start")
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "📁 <b>مدیریت پلن‌ها و لایسنس‌ها</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: ADD PLAN FSM ===
# ============================================================

@admin_plans_router.callback_query(F.data == "add_plan_start")
async def add_plan_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add plan start."""
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_plan_name)
    await callback.message.edit_text("لطفا نام پلن جدید را وارد کنید (مثلا: ویژه 💎):")


@admin_plans_router.message(AdminStates.waiting_for_plan_name)
async def add_plan_name(message: types.Message, state: FSMContext):
    """Handles add plan name."""
    if not is_admin(message): return
    await state.update_data(plan_name=message.text)
    await state.set_state(AdminStates.waiting_for_admin_description)
    await message.answer("لطفا توضیحات ادمین برای این پلن را وارد کنید (در پیش‌فاکتور کاربر نمایش داده می‌شود):")


@admin_plans_router.message(AdminStates.waiting_for_admin_description)
async def add_plan_desc(message: types.Message, state: FSMContext):
    """Handles add plan desc."""
    if not is_admin(message): return
    data = await state.get_data()

    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO plans (name, admin_description) VALUES (?, ?)', (data['plan_name'], message.text))
        await db.commit()

    await state.set_state(None)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به پلن‌ها", callback_data="admin_manage_plans")
    await message.answer(
        f"✅ پلن <b>{data['plan_name']}</b> با موفقیت ساخته شد.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: PLAN DASHBOARD ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("manageplan_"))
async def plan_dashboard(callback: types.CallbackQuery):
    """Handles plan dashboard."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    plan = await db_manager.get_plan(plan_id)
    if not plan:
        return await callback.answer("پلن یافت نشد.", show_alert=True)

    # Check if a panel is connected
    binding = await db_manager.get_plan_panel(plan_id)
    panel_info = "❌ متصل نشده"
    if binding:
        panel = await db_manager.get_xui_panel(binding["panel_id"])
        if panel:
            short_url = panel["url"].replace("https://", "").replace("http://", "")[:40]
            panel_info = f"✅ پنل #{panel['id']} — {short_url}"

    text = (
        f"📁 <b>مدیریت پلن:</b> {plan['name']}\n"
        f"📝 <b>توضیحات:</b> {plan['admin_description']}\n\n"
        f"💰 <b>قیمت پایه روزانه:</b> {plan['price_per_day']:,} تومان\n"
        f"💰 <b>قیمت پایه گیگابایت:</b> {plan['price_per_gb']:,} تومان\n\n"
        f"🖥 <b>پنل متصل:</b> {panel_info}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="⏱ پکیجهای زمان", callback_data=f"pkgtime_{plan_id}")
    builder.button(text="🔋 پکیجهای حجم", callback_data=f"pkgtraffic_{plan_id}")
    builder.button(text="💰 تنظیم قیمت سریع", callback_data=f"fastprice_{plan_id}")
    builder.button(text="📦 اتصال مخزن", callback_data=f"connect_panel_{plan_id}")
    builder.button(text="❌ حذف پلن", callback_data=f"delplan_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data="admin_manage_plans")
    builder.adjust(2, 2, 1, 1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============================================================
# === ROUTER: FAST PRICING ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("fastprice_"))
async def fast_price_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles fast price start."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(fast_price_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_fast_pricing)
    await callback.message.edit_text("لطفا قیمت روز و قیمت گیگ را با فاصله وارد کنید (مثلا: 1200 7000):")


@admin_plans_router.message(AdminStates.waiting_for_fast_pricing)
async def fast_price_save(message: types.Message, state: FSMContext):
    """Handles fast price save."""
    if not is_admin(message): return
    try:
        day_price, gb_price = map(int, message.text.split())
        data = await state.get_data()
        plan_id = data['fast_price_plan_id']

        from database.db_manager import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('UPDATE plans SET price_per_day = ?, price_per_gb = ? WHERE id = ?', (day_price, gb_price, plan_id))
            await db.commit()

        await state.set_state(None)

        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
        await message.answer("✅ قیمت‌های پایه با موفقیت بروزرسانی شد.", reply_markup=builder.as_markup())
    except Exception:
        await message.answer("❌ فرمت نامعتبر است. باید دو عدد با فاصله باشند (مثال: 1200 7000)")


# ============================================================
# === ROUTER: اتصال مخزن (Panel Connection) ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("connect_panel_"))
async def connect_panel_menu(callback: types.CallbackQuery):
    """Show list of available XUI panels for admin to bind to this plan."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[2])

    panels = await db_manager.get_xui_panels()

    if not panels:
        builder = InlineKeyboardBuilder()
        builder.button(text="🖥 رفتن به مدیریت ثنا", callback_data="admin_xui")
        builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
        builder.adjust(1)
        return await callback.message.edit_text(
            "❌ هیچ پنلی تعریف نشده است.\n"
            "ابتدا از بخش <b>مدیریت ثنا</b> یک پنل اضافه کنید.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    # Show current binding
    binding = await db_manager.get_plan_panel(plan_id)
    current_panel_id = binding["panel_id"] if binding else None

    builder = InlineKeyboardBuilder()
    for p in panels:
        short_url = p["url"].replace("https://", "").replace("http://", "")[:35]
        tick = " ✅" if p["id"] == current_panel_id else ""
        builder.button(
            text=f"🖥 پنل #{p['id']} — {short_url}{tick}",
            callback_data=f"bind_panel_{plan_id}_{p['id']}"
        )

    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📦 <b>اتصال مخزن به پلن #{plan_id}</b>\n\n"
        "یکی از پنل‌های زیر را برای اتصال به این پلن انتخاب کنید:\n"
        "<i>لایسنس‌های کاربران برای این پلن روی پنل انتخابی ساخته خواهند شد.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_plans_router.callback_query(F.data.startswith("bind_panel_"))
async def bind_panel_to_plan(callback: types.CallbackQuery):
    """Bind the chosen panel to the plan."""
    if not is_admin(callback.message): return

    parts = callback.data.split("_")
    plan_id = int(parts[2])
    panel_id = int(parts[3])

    await db_manager.set_plan_panel(plan_id, panel_id)
    panel = await db_manager.get_xui_panel(panel_id)
    panel_label = panel["url"] if panel else f"#{panel_id}"

    await callback.answer(f"✅ پنل {panel_label[:40]} به این پلن متصل شد.", show_alert=True)

    # Return to plan dashboard
    callback.data = f"manageplan_{plan_id}"
    await plan_dashboard(callback)


# ============================================================
# === ROUTER: MANAGE TIME PACKAGES (comma-separated input) ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("pkgtime_"))
async def manage_time_packages(callback: types.CallbackQuery, state: FSMContext):
    """Handles manage time packages."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    time_packages = await db_manager.get_time_packages(plan_id)

    existing = ", ".join(str(tp["days"]) for tp in time_packages) or "—"

    builder = InlineKeyboardBuilder()
    for tp in time_packages:
        builder.button(text=f"❌ {tp['days']} روز", callback_data=f"deltime_{tp['id']}_{plan_id}")

    builder.button(text="➕ افزودن / جایگزینی زمان‌ها", callback_data=f"addtime_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(2)

    await callback.message.edit_text(
        f"⏱ <b>پکیج‌های زمانی این پلن</b>\n\n"
        f"زمان‌های فعلی: <code>{existing}</code>\n\n"
        "برای حذف روی هرکدام کلیک کنید، یا زمان‌های جدید اضافه کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_plans_router.callback_query(F.data.startswith("deltime_"))
async def delete_time_package(callback: types.CallbackQuery):
    """Handles delete time package."""
    if not is_admin(callback.message): return
    tp_id = int(callback.data.split("_")[1])
    plan_id = int(callback.data.split("_")[2])

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM time_packages WHERE id=?', (tp_id,))
        await db.commit()

    await callback.answer("✅ پکیج زمان حذف شد.", show_alert=True)
    callback.data = f"pkgtime_{plan_id}"
    await manage_time_packages(callback, None)


@admin_plans_router.callback_query(F.data.startswith("addtime_"))
async def add_time_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add time start."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(add_time_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_time_days)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data=f"pkgtime_{plan_id}")
    await callback.message.edit_text(
        "⏱ <b>افزودن پکیج‌های زمان</b>\n\n"
        "تعداد روزها را با ویرگول جدا کنید:\n"
        "<i>مثال: <code>7,30,60,90</code></i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_plans_router.message(AdminStates.waiting_for_time_days)
async def add_time_save(message: types.Message, state: FSMContext):
    """Handles add time save."""
    if not is_admin(message): return

    # Accept comma-separated integers
    parts = [p.strip() for p in message.text.split(",") if p.strip()]
    valid = []
    invalid = []
    for p in parts:
        if p.isdigit() and int(p) > 0:
            valid.append(int(p))
        else:
            invalid.append(p)

    if invalid:
        return await message.answer(
            f"❌ مقادیر نامعتبر: <code>{', '.join(invalid)}</code>\n"
            "لطفاً فقط اعداد صحیح مثبت با ویرگول وارد کنید.",
            parse_mode="HTML"
        )
    if not valid:
        return await message.answer("❌ هیچ عدد معتبری وارد نشد.")

    data = await state.get_data()
    plan_id = data['add_time_plan_id']

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        for days in valid:
            # Avoid duplicates
            async with db.execute('SELECT id FROM time_packages WHERE plan_id=? AND days=?', (plan_id, days)) as c:
                if not await c.fetchone():
                    await db.execute('INSERT INTO time_packages (plan_id, days) VALUES (?, ?)', (plan_id, days))
        await db.commit()

    await state.set_state(None)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت پکیج‌های زمان", callback_data=f"pkgtime_{plan_id}")
    await message.answer(
        f"✅ پکیج‌های زمانی اضافه شدند: <code>{', '.join(str(d) + ' روز' for d in valid)}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: MANAGE TRAFFIC PACKAGES (comma-separated input) ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("pkgtraffic_"))
async def manage_traffic_packages(callback: types.CallbackQuery, state: FSMContext):
    """Handles manage traffic packages."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    traffic_packages = await db_manager.get_traffic_packages(plan_id)

    existing = ", ".join(str(tp["gb"]) for tp in traffic_packages) or "—"

    builder = InlineKeyboardBuilder()
    for tp in traffic_packages:
        builder.button(text=f"❌ {tp['gb']} گیگ", callback_data=f"deltraffic_{tp['id']}_{plan_id}")

    builder.button(text="➕ افزودن / جایگزینی حجم‌ها", callback_data=f"addtraffic_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(2)

    await callback.message.edit_text(
        f"🔋 <b>پکیج‌های حجم این پلن</b>\n\n"
        f"حجم‌های فعلی: <code>{existing}</code>\n\n"
        "برای حذف روی هرکدام کلیک کنید، یا حجم‌های جدید اضافه کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_plans_router.callback_query(F.data.startswith("deltraffic_"))
async def delete_traffic_package(callback: types.CallbackQuery):
    """Handles delete traffic package."""
    if not is_admin(callback.message): return
    tp_id = int(callback.data.split("_")[1])
    plan_id = int(callback.data.split("_")[2])

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM traffic_packages WHERE id=?', (tp_id,))
        await db.commit()

    await callback.answer("✅ پکیج حجم حذف شد.", show_alert=True)
    callback.data = f"pkgtraffic_{plan_id}"
    await manage_traffic_packages(callback, None)


@admin_plans_router.callback_query(F.data.startswith("addtraffic_"))
async def add_traffic_start(callback: types.CallbackQuery, state: FSMContext):
    """Handles add traffic start."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(add_traffic_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_traffic_gb)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data=f"pkgtraffic_{plan_id}")
    await callback.message.edit_text(
        "🔋 <b>افزودن پکیج‌های حجم</b>\n\n"
        "مقادیر حجم را به گیگابایت با ویرگول جدا کنید:\n"
        "<i>مثال: <code>10,20,50,100</code></i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_plans_router.message(AdminStates.waiting_for_traffic_gb)
async def add_traffic_save(message: types.Message, state: FSMContext):
    """Handles add traffic save."""
    if not is_admin(message): return

    parts = [p.strip() for p in message.text.split(",") if p.strip()]
    valid = []
    invalid = []
    for p in parts:
        if p.isdigit() and int(p) > 0:
            valid.append(int(p))
        else:
            invalid.append(p)

    if invalid:
        return await message.answer(
            f"❌ مقادیر نامعتبر: <code>{', '.join(invalid)}</code>\n"
            "لطفاً فقط اعداد صحیح مثبت با ویرگول وارد کنید.",
            parse_mode="HTML"
        )
    if not valid:
        return await message.answer("❌ هیچ عدد معتبری وارد نشد.")

    data = await state.get_data()
    plan_id = data['add_traffic_plan_id']

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        for gb in valid:
            async with db.execute('SELECT id FROM traffic_packages WHERE plan_id=? AND gb=?', (plan_id, gb)) as c:
                if not await c.fetchone():
                    await db.execute('INSERT INTO traffic_packages (plan_id, gb) VALUES (?, ?)', (plan_id, gb))
        await db.commit()

    await state.set_state(None)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 مدیریت پکیج‌های حجم", callback_data=f"pkgtraffic_{plan_id}")
    await message.answer(
        f"✅ پکیج‌های حجم اضافه شدند: <code>{', '.join(str(g) + ' گیگ' for g in valid)}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ============================================================
# === ROUTER: DELETE PLAN ===
# ============================================================

@admin_plans_router.callback_query(F.data.startswith("delplan_"))
async def delete_plan(callback: types.CallbackQuery):
    """Handles delete plan."""
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM plans WHERE id=?', (plan_id,))
        await db.commit()

    await callback.answer("✅ پلن و تمامی پکیج‌های مرتبط حذف شد.", show_alert=True)

    callback.data = "admin_manage_plans"
    await manage_plans_menu(callback)
