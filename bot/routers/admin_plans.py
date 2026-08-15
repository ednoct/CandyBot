# === IMPORTS ===
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .admin import is_admin
from ..states import AdminStates
from database import db_manager
import aiosqlite

admin_plans_router = Router()

# === ROUTER: MANAGE PLANS MAIN ===
@admin_plans_router.callback_query(F.data == "admin_manage_plans")
async def manage_plans_menu(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    
    plans = await db_manager.get_plans()
    builder = InlineKeyboardBuilder()
    
    for p in plans:
        builder.button(text=f"📁 {p['name']}", callback_data=f"manageplan_{p['id']}")
        
    builder.button(text="➕ افزودن پلن جدید", callback_data="add_plan_start")
    builder.button(text="🔙 بازگشت", callback_data="admin_back")
    builder.adjust(1)
    
    await callback.message.edit_text("📁 **مدیریت پلن‌ها و لایسنس‌ها**", reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: ADD PLAN FSM ===
@admin_plans_router.callback_query(F.data == "add_plan_start")
async def add_plan_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    await state.set_state(AdminStates.waiting_for_plan_name)
    await callback.message.edit_text("لطفا نام پلن جدید را وارد کنید (مثلا: ویژه 💎):")

@admin_plans_router.message(AdminStates.waiting_for_plan_name)
async def add_plan_name(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    await state.update_data(plan_name=message.text)
    await state.set_state(AdminStates.waiting_for_admin_description)
    await message.answer("لطفا توضیحات ادمین برای این پلن را وارد کنید (در پیش‌فاکتور کاربر نمایش داده می‌شود):")

@admin_plans_router.message(AdminStates.waiting_for_admin_description)
async def add_plan_desc(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    data = await state.get_data()
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO plans (name, admin_description) VALUES (?, ?)', (data['plan_name'], message.text))
        await db.commit()
        
    await state.set_state(None)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به پلن‌ها", callback_data="admin_manage_plans")
    await message.answer(f"✅ پلن **{data['plan_name']}** با موفقیت ساخته شد.", reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: PLAN DASHBOARD ===
@admin_plans_router.callback_query(F.data.startswith("manageplan_"))
async def plan_dashboard(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    plan = await db_manager.get_plan(plan_id)
    if not plan:
        return await callback.answer("پلن یافت نشد.", show_alert=True)
        
    text = (
        f"📁 **مدیریت پلن:** {plan['name']}\n"
        f"📝 **توضیحات:** {plan['admin_description']}\n\n"
        f"💰 **قیمت پایه روزانه:** {plan['price_per_day']} تومان\n"
        f"💰 **قیمت پایه گیگابایت:** {plan['price_per_gb']} تومان"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏱ پکیج‌های زمان", callback_data=f"pkgtime_{plan_id}")
    builder.button(text="🔋 پکیج‌های حجم", callback_data=f"pkgtraffic_{plan_id}")
    builder.button(text="💰 تنظیم قیمت سریع", callback_data=f"fastprice_{plan_id}")
    builder.button(text="📦 مخزن لایسنس‌ها", callback_data=f"cargo_plan_{plan_id}")
    builder.button(text="❌ حذف پلن", callback_data=f"delplan_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data="admin_manage_plans")
    builder.adjust(2, 2, 1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# === ROUTER: FAST PRICING ===
@admin_plans_router.callback_query(F.data.startswith("fastprice_"))
async def fast_price_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(fast_price_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_fast_pricing)
    
    await callback.message.edit_text("لطفا قیمت روز و قیمت گیگ را با فاصله وارد کنید (مثلا: 1200 7000):")

@admin_plans_router.message(AdminStates.waiting_for_fast_pricing)
async def fast_price_save(message: types.Message, state: FSMContext):
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

# === ROUTER: CARGO ===
@admin_plans_router.callback_query(F.data.startswith("cargo_plan_"))
async def cargo_select_time(callback: types.CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[2])
    await state.update_data(cargo_plan_id=plan_id)
    time_packages = await db_manager.get_time_packages(plan_id)
    
    builder = InlineKeyboardBuilder()
    for tp in time_packages:
        builder.button(text=f"{tp['days']} روز", callback_data=f"cargotime_{tp['id']}")
    builder.button(text="🎁 مخزن تست رایگان", callback_data="cargo_free_test")
    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(2)
    
    await callback.message.edit_text("📦 زمان مورد نظر برای مخزن را انتخاب کنید:", reply_markup=builder.as_markup())

@admin_plans_router.callback_query(F.data.startswith("cargotime_"))
async def cargo_select_traffic(callback: types.CallbackQuery, state: FSMContext):
    time_id = int(callback.data.split("_")[1])
    await state.update_data(cargo_time_id=time_id)
    data = await state.get_data()
    plan_id = data['cargo_plan_id']
    
    traffic_packages = await db_manager.get_traffic_packages(plan_id)
    builder = InlineKeyboardBuilder()
    for tp in traffic_packages:
        builder.button(text=f"{tp['gb']} گیگ", callback_data=f"cargotraffic_{tp['id']}")
    builder.button(text="🔙 بازگشت", callback_data=f"cargo_plan_{plan_id}")
    builder.adjust(3)
    
    await callback.message.edit_text("📦 حجم مورد نظر برای مخزن را انتخاب کنید:", reply_markup=builder.as_markup())

@admin_plans_router.callback_query(F.data.startswith("cargotraffic_"))
async def cargo_stock_prompt(callback: types.CallbackQuery, state: FSMContext):
    traffic_id = int(callback.data.split("_")[1])
    await state.update_data(cargo_traffic_id=traffic_id)
    data = await state.get_data()
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM licenses_cargo WHERE plan_id=? AND time_package_id=? AND traffic_package_id=?', 
            (data['cargo_plan_id'], data['cargo_time_id'], traffic_id)) as cursor:
            count = (await cursor.fetchone())[0]
            
    await state.set_state(AdminStates.waiting_for_cargo_stock)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف و بازگشت", callback_data="cancel_cargo_add")
    await callback.message.edit_text(f"📦 موجودی فعلی این کامبو: **{count} لایسنس**\n\nبرای شارژ مخزن، لایسنس‌ها را بفرستید (هر خط یک لایسنس):", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_plans_router.message(AdminStates.waiting_for_cargo_stock)
async def cargo_stock_save(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    lines = [line.strip() for line in message.text.split('\n') if line.strip()]
    data = await state.get_data()
    
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        if data.get('cargo_free_test', False):
            for line in lines:
                try:
                    await db.execute('INSERT INTO licenses_cargo (license_key, is_free_test) VALUES (?, 1)', (line,))
                except aiosqlite.OperationalError as e:
                    return await message.reply(f"❌ خطای دیتابیس در ثبت لایسنس (ستون‌های مخزن ناقص است): {e}")
        else:
            for line in lines:
                await db.execute('INSERT INTO licenses_cargo (plan_id, time_package_id, traffic_package_id, license_key) VALUES (?, ?, ?, ?)',
                    (data['cargo_plan_id'], data['cargo_time_id'], data['cargo_traffic_id'], line))
        await db.commit()
        
    await state.set_state(None)
    await message.answer(f"✅ تعداد **{len(lines)}** لایسنس با موفقیت به این مخزن اضافه شد.", parse_mode="Markdown")

@admin_plans_router.callback_query(F.data == "cargo_free_test")
async def cargo_free_test_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cargo_free_test=True)
    from database.db_manager import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1') as cursor:
            count = (await cursor.fetchone())[0]
            
    await state.set_state(AdminStates.waiting_for_cargo_stock)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 انصراف و بازگشت", callback_data="cancel_cargo_add")
    await callback.message.edit_text(f"🎁 موجودی فعلی تست رایگان: **{count} لایسنس**\n\nبرای شارژ مخزن، لایسنس‌ها را بفرستید (هر خط یک لایسنس):", reply_markup=builder.as_markup(), parse_mode="Markdown")
    
@admin_plans_router.callback_query(F.data == "cancel_cargo_add")
async def cancel_cargo_add(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await manage_plans_menu(callback)

# === ROUTER: MANAGE TIME PACKAGES ===
@admin_plans_router.callback_query(F.data.startswith("pkgtime_"))
async def manage_time_packages(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    time_packages = await db_manager.get_time_packages(plan_id)
    
    builder = InlineKeyboardBuilder()
    for tp in time_packages:
        builder.button(text=f"❌ {tp['days']} روز", callback_data=f"deltime_{tp['id']}_{plan_id}")
        
    builder.button(text="➕ افزودن زمان", callback_data=f"addtime_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(2)
    
    await callback.message.edit_text("⏱ **پکیج‌های زمانی این پلن**\n\nبرای حذف روی هرکدام کلیک کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_plans_router.callback_query(F.data.startswith("deltime_"))
async def delete_time_package(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    tp_id = int(callback.data.split("_")[1])
    plan_id = int(callback.data.split("_")[2])
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM time_packages WHERE id=?', (tp_id,))
        await db.commit()
        
    await callback.answer("✅ پکیج زمان حذف شد.", show_alert=True)
    
    # Reload menu
    callback.data = f"pkgtime_{plan_id}"
    await manage_time_packages(callback, None)

@admin_plans_router.callback_query(F.data.startswith("addtime_"))
async def add_time_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(add_time_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_time_days)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data=f"pkgtime_{plan_id}")
    await callback.message.edit_text("لطفا تعداد روز را به صورت عدد وارد کنید (مثلا: 30):", reply_markup=builder.as_markup())

@admin_plans_router.message(AdminStates.waiting_for_time_days)
async def add_time_save(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    try:
        days = int(message.text.strip())
        data = await state.get_data()
        plan_id = data['add_time_plan_id']
        
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute('INSERT INTO time_packages (plan_id, days) VALUES (?, ?)', (plan_id, days))
            await db.commit()
            
        await state.set_state(None)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 مدیریت پکیج‌های زمان", callback_data=f"pkgtime_{plan_id}")
        await message.answer(f"✅ پکیج {days} روز با موفقیت اضافه شد.", reply_markup=builder.as_markup())
    except ValueError:
        await message.answer("❌ لطفا فقط عدد وارد کنید.")

# === ROUTER: MANAGE TRAFFIC PACKAGES ===
@admin_plans_router.callback_query(F.data.startswith("pkgtraffic_"))
async def manage_traffic_packages(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    traffic_packages = await db_manager.get_traffic_packages(plan_id)
    
    builder = InlineKeyboardBuilder()
    for tp in traffic_packages:
        builder.button(text=f"❌ {tp['gb']} گیگ", callback_data=f"deltraffic_{tp['id']}_{plan_id}")
        
    builder.button(text="➕ افزودن حجم", callback_data=f"addtraffic_{plan_id}")
    builder.button(text="🔙 بازگشت", callback_data=f"manageplan_{plan_id}")
    builder.adjust(2)
    
    await callback.message.edit_text("🔋 **پکیج‌های حجم این پلن**\n\nبرای حذف روی هرکدام کلیک کنید:", reply_markup=builder.as_markup(), parse_mode="Markdown")

@admin_plans_router.callback_query(F.data.startswith("deltraffic_"))
async def delete_traffic_package(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    tp_id = int(callback.data.split("_")[1])
    plan_id = int(callback.data.split("_")[2])
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM traffic_packages WHERE id=?', (tp_id,))
        await db.commit()
        
    await callback.answer("✅ پکیج حجم حذف شد.", show_alert=True)
    
    # Reload menu
    callback.data = f"pkgtraffic_{plan_id}"
    await manage_traffic_packages(callback, None)

@admin_plans_router.callback_query(F.data.startswith("addtraffic_"))
async def add_traffic_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    await state.update_data(add_traffic_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_traffic_gb)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو", callback_data=f"pkgtraffic_{plan_id}")
    await callback.message.edit_text("لطفا مقدار حجم را به گیگابایت (عدد) وارد کنید (مثلا: 50):", reply_markup=builder.as_markup())

@admin_plans_router.message(AdminStates.waiting_for_traffic_gb)
async def add_traffic_save(message: types.Message, state: FSMContext):
    if not is_admin(message): return
    try:
        gb = int(message.text.strip())
        data = await state.get_data()
        plan_id = data['add_traffic_plan_id']
        
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute('INSERT INTO traffic_packages (plan_id, gb) VALUES (?, ?)', (plan_id, gb))
            await db.commit()
            
        await state.set_state(None)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 مدیریت پکیج‌های حجم", callback_data=f"pkgtraffic_{plan_id}")
        await message.answer(f"✅ پکیج {gb} گیگابایت با موفقیت اضافه شد.", reply_markup=builder.as_markup())
    except ValueError:
        await message.answer("❌ لطفا فقط عدد وارد کنید.")

# === ROUTER: DELETE PLAN ===
@admin_plans_router.callback_query(F.data.startswith("delplan_"))
async def delete_plan(callback: types.CallbackQuery):
    if not is_admin(callback.message): return
    plan_id = int(callback.data.split("_")[1])
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute('DELETE FROM plans WHERE id=?', (plan_id,))
        await db.commit()
        
    await callback.answer("✅ پلن و تمامی مخازن و پکیج‌های مرتبط حذف شد.", show_alert=True)
    
    # Send user back to manage plans
    callback.data = "admin_manage_plans"
    await manage_plans_menu(callback)

