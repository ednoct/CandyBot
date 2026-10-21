# === FIX BUG-02: USER BAN & UNBAN HANDLERS ===
@admin_users_router.callback_query(F.data.startswith("user_ban_"))
async def user_ban(callback: types.CallbackQuery):
    if not is_admin(callback):
        return
    user_id = int(callback.data.split("_")[2])
    await db_manager.disable_user(user_id)
    await callback.answer("🚫 کاربر با موفقیت مسدود شد.", show_alert=True)
    # Refresh user management view
    callback.data = f"manage_user_{user_id}"
    await manage_user_detail(callback)


@admin_users_router.callback_query(F.data.startswith("user_unban_"))
async def user_unban(callback: types.CallbackQuery):
    if not is_admin(callback):
        return
    user_id = int(callback.data.split("_")[2])
    await db_manager.enable_user(user_id)
    await callback.answer("✅ مسدودیت کاربر رفع شد.", show_alert=True)
    # Refresh user management view
    callback.data = f"manage_user_{user_id}"
    await manage_user_detail(callback)


# === FIX BUG-07: BROADCAST INACTIVE DAYS & UNPIN ALL HANDLERS ===
@admin_users_router.callback_query(F.data == "bcast_inactive_days")
async def bcast_inactive_days_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    await state.set_state(BroadcastStates.waiting_for_inactive_days)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_broadcast", style="danger")
    await safe_edit_message(
        callback,
        "⏳ لطفاً تعداد روزهایی که کاربران فعالیت یا خریدی نداشته‌اند را به صورت عدد وارد کنید (مثلاً 30):",
        reply_markup=builder.as_markup()
    )


@admin_users_router.message(BroadcastStates.waiting_for_inactive_days)
async def bcast_inactive_days_process(message: types.Message, state: FSMContext):
    if not is_admin(message):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        return await message.answer("❌ لطفاً یک عدد صحیح و بزرگ‌تر از صفر وارد کنید:")

    days = int(raw)
    user_ids = await db_manager.get_inactive_users_for_broadcast(days)
    if not user_ids:
        await state.clear()
        return await message.answer(f"ℹ️ هیچ کاربری که بیش از {days} روز غیرفعال باشد یافت نشد.")

    await state.update_data(target_user_ids=user_ids, audience_type=f"inactive_{days}_days")
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        f"✅ تعداد <b>{len(user_ids)}</b> کاربر غیرفعال (بیش از {days} روز) شناسایی شد.\n\n"
        "📝 اکنون پیام خود را جهت ارسال همگانی بفرستید:",
        parse_mode="HTML"
    )


@admin_users_router.callback_query(F.data == "bcast_unpin_all")
async def bcast_unpin_all_handler(callback: types.CallbackQuery):
    if not is_admin(callback):
        return
    await callback.answer("در حال شروع عملیات لغو پین پیام‌ها...", show_alert=False)

    user_ids = await db_manager.get_all_users_for_broadcast()
    if not user_ids:
        return await callback.message.answer("ℹ️ هیچ کاربر فعالی یافت نشد.")

    async def _unpin_worker():
        import asyncio
        unpinned = 0
        for uid in user_ids:
            try:
                await callback.bot.unpin_all_chat_messages(chat_id=uid)
                unpinned += 1
            except Exception:
                pass
            await asyncio.sleep(0.05)
        try:
            await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=f"📌 عملیات لغو پین پیام‌ها به پایان رسید.\nتعداد چت‌های پاکسازی‌شده: <b>{unpinned}</b> از <b>{len(user_ids)}</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    import asyncio
    asyncio.create_task(_unpin_worker())
    await callback.message.answer(f"⏳ عملیات لغو پین پیام‌ها برای {len(user_ids)} کاربر در پس‌زمینه آغاز شد.")