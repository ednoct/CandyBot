# === FIX BUG-03: CRM TRIAL FOLLOW-UP HANDLER ===
@admin_reports_router.callback_query(F.data == "crm_trial_followup")
async def crm_trial_followup(callback: types.CallbackQuery):
    if not is_admin(callback):
        return

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Fixed JOIN condition: removed invalid `OR pr.id_user = u.id`
        query = """
            SELECT DISTINCT u.id, u.username, u.created_at
            FROM users u
            LEFT JOIN free_trial_usage ftu ON ftu.user_id = u.id
            LEFT JOIN payment_reports pr ON pr.user_id = u.id AND pr.payment_method = 'free_test'
            LEFT JOIN invoices inv_test ON inv_test.user_id = u.id AND inv_test.base_price = 0
            WHERE (ftu.user_id IS NOT NULL OR pr.id IS NOT NULL OR inv_test.id IS NOT NULL)
              AND u.id NOT IN (
                  SELECT DISTINCT user_id FROM invoices
                  WHERE base_price > 0 AND status IN ('paid', 'approved', 'completed')
              )
            ORDER BY u.created_at DESC
            LIMIT 50
        """
        async with db.execute(query) as cursor:
            trial_only_users = await cursor.fetchall()

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data="admin_reports", style="danger")

    if not trial_only_users:
        return await safe_edit_message(
            callback,
            "✅ هیچ کاربری که صرفاً تست رایگان گرفته و خریدی نکرده باشد یافت نشد.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    lines = ["📊 <b>لیست کاربران تست رایگان بدون خرید (۵۰ نفر اخیر):</b>\n"]
    for idx, u in enumerate(trial_only_users, start=1):
        uname = f"@{u['username']}" if u['username'] else "بدون نام کاربری"
        lines.append(f"{idx}. <code>{u['id']}</code> ({uname})")

    await safe_edit_message(
        callback,
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )