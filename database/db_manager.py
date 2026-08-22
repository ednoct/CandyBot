"""
db_manager.py
-------------
Module containing functionalities for db_manager.
"""
# === IMPORTS AND CONFIG ===
# === IMPORTS ===
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'candy.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

# === DATABASE INITIALIZATION ===
async def init_db():
    """Handles init db."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = ON;')
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            await db.executescript(f.read())
            
        try:
            await db.execute("ALTER TABLE users ADD COLUMN agent TEXT DEFAULT 'f'")
            await db.execute("ALTER TABLE users ADD COLUMN expire INTEGER")
            await db.execute("ALTER TABLE users ADD COLUMN maxbuyagent INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE users ADD COLUMN pricediscount INTEGER DEFAULT 0")
        except Exception:
            pass # Ignore if columns already exist
            
        try:
            await db.execute("ALTER TABLE licenses_cargo ADD COLUMN is_free_test INTEGER DEFAULT 0")
        except Exception:
            pass
            
        # Legacy cleanup
        try:
            await db.execute("DROP TABLE IF EXISTS app")
        except Exception:
            pass

        # XUI integration migrations — safe ALTER TABLE (idempotent)
        for migration_sql in [
            "ALTER TABLE invoices ADD COLUMN license_note TEXT",
            "ALTER TABLE invoices ADD COLUMN panel_id INTEGER",
            "ALTER TABLE invoices ADD COLUMN renew_license_id INTEGER",
            "ALTER TABLE invoices ADD COLUMN last_error TEXT",
            "ALTER TABLE xui_licenses ADD COLUMN alert_sent INTEGER DEFAULT 0",
            "ALTER TABLE xui_panels ADD COLUMN name TEXT",
            "ALTER TABLE xui_panels ADD COLUMN sub_link TEXT",
            # Referral & CRM columns
            "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1",
            "ALTER TABLE payment_reports ADD COLUMN gateway_request_id TEXT",
        ]:
            try:
                await db.execute(migration_sql)
            except Exception:
                pass  # Column already exists

        # Seed default operating mode if not set
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('operating_mode', 'NORMAL')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('cashback_percent', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('free_test_enabled', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('free_test_gb', '1')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('free_test_days', '1')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('free_test_daily_limit', '50')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('free_test_panel_id', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_card_number', '1234-5678-9012-3456')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_enabled', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_commission_percent', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('feedback_enabled', '1')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('acquisition_survey_enabled', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('frenzyex_callback_secret', '')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('frenzyex_api_key', '')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('frenzyex_base_url', 'https://frenzy.fastsnap.info')"
        )
        await db.commit()

async def cleanup_miniapp_migration():
    """Migration to clean up old miniapp-specific settings from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key = 'webapp_theme'")
        await db.commit()

# === USER OPERATIONS ===
async def get_user(user_id: int):
    """Handles get user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def create_user(user_id: int, username: str):
    """Handles create user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)', (user_id, username))
        await db.commit()

async def update_user_step(user_id: int, step: str):
    """Handles update user step."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET step = ? WHERE id = ?', (step, user_id))
        await db.commit()

async def update_user_balance(user_id: int, amount_change: int):
    """Handles update user balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount_change, user_id))
        await db.commit()

# === GENERIC DB OPERATIONS ===
async def fetch_all(sql: str, params: tuple = ()):
    """Handles fetch all."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchall()

async def fetch_one(sql: str, params: tuple = ()):
    """Handles fetch one."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchone()

async def fetch_scalar(sql: str, params: tuple = ()):
    """Handles fetch scalar."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def execute(sql: str, params: tuple = ()):
    """Handles execute."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount

async def get_setting(key: str, default=None):
    """Handles get setting."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row['value'] if row else default

async def set_setting(key: str, value: str):
    """Handles set setting."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
        await db.commit()

# === AUTH DB OPERATIONS ===
async def user_from_token(token: str):
    """Handles user from token."""
    return await fetch_one("SELECT * FROM users WHERE token = ?", (token,))

async def issue_token(user_id: int):
    """Handles issue token."""
    import secrets
    token = secrets.token_hex(20)
    await execute("UPDATE users SET token = ? WHERE id = ?", (token, user_id))
    return token


# === NEW API OPERATIONS ===
async def api_get_users_list(limit: int, offset: int, q: str):
    """Handles api get users list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = 'SELECT COUNT(*) FROM users WHERE id LIKE ? OR username LIKE ?'
        async with db.execute(count_query, (search, search)) as cursor:
            total = (await cursor.fetchone())[0]
            
        data_query = 'SELECT * FROM users WHERE id LIKE ? OR username LIKE ? LIMIT ? OFFSET ?'
        async with db.execute(data_query, (search, search, limit, offset)) as cursor:
            users = await cursor.fetchall()
            return users, total

async def api_get_user_details(user_id: int):
    """Handles api get user details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_user_status(user_id: int, status: str, description: str):
    """Handles update user status."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Assuming we have status and description_blocking columns
        await db.execute('UPDATE users SET status = ?, description = ? WHERE id = ?', (status, description, user_id))
        await db.commit()

async def update_user_verify(user_id: int, verify: int):
    """Handles update user verify."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET verify = ? WHERE id = ?', (verify, user_id))
        await db.commit()

async def zero_user_balance(user_id: int):
    """Handles zero user balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = 0 WHERE id = ?', (user_id,))
        await db.commit()

async def api_create_user_full(user_id: int):
    """Handles api create user full."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (id) VALUES (?)', (user_id,))
        await db.commit()

async def api_update_user_field(user_id: int, field: str, value):
    """Handles api update user field."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'UPDATE users SET {field} = ? WHERE id = ?', (value, user_id))
        await db.commit()

async def api_transfer_account(old_id: int, new_id: int):
    """Handles api transfer account."""
    async with aiosqlite.connect(DB_PATH, isolation_level=None) as db:
        await db.execute('BEGIN EXCLUSIVE')
        try:
            await db.execute('DELETE FROM users WHERE id = ?', (new_id,))
            await db.execute('UPDATE users SET id = ? WHERE id = ?', (new_id, old_id))
            # Wait, updating relations
            await db.execute('UPDATE invoices SET id_user = ? WHERE id_user = ?', (new_id, old_id))
            await db.execute('UPDATE Payment_report SET id_user = ? WHERE id_user = ?', (new_id, old_id))
            await db.commit()
        except Exception as e:
            await db.execute('ROLLBACK')
            raise e

async def api_get_affiliate_users(affiliate_id: int):
    """Handles api get affiliate users."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT id as user_id FROM users WHERE affiliates = ?', (affiliate_id,)) as cursor:
            return await cursor.fetchall()

async def api_remove_affiliates(affiliate_id: int):
    """Handles api remove affiliates."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET affiliates = 0 WHERE affiliates = ?', (affiliate_id,))
        await db.execute('UPDATE users SET affiliatescount = 0 WHERE id = ?', (affiliate_id,))
        await db.commit()

async def api_get_invoices_list(limit: int, offset: int, q: str):
    """Handles api get invoices list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = 'SELECT COUNT(*) FROM invoices WHERE id LIKE ? OR username LIKE ?'
        async with db.execute(count_query, (search, search)) as cursor:
            total = (await cursor.fetchone())[0]
            
        data_query = 'SELECT * FROM invoices WHERE id LIKE ? OR username LIKE ? LIMIT ? OFFSET ?'
        async with db.execute(data_query, (search, search, limit, offset)) as cursor:
            invoices = await cursor.fetchall()
            return invoices, total

async def api_get_services_list(limit: int, offset: int, q: str):
    """Handles api get services list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = "SELECT COUNT(*) FROM service_other WHERE (id_user LIKE ? OR username LIKE ?) AND (status = 'paid' OR status IS NULL)"
        async with db.execute(count_query, (search, search)) as cursor:
            total = (await cursor.fetchone())[0]
            
        data_query = "SELECT * FROM service_other WHERE (id_user LIKE ? OR username LIKE ?) AND (status = 'paid' OR status IS NULL) ORDER BY time DESC LIMIT ? OFFSET ?"
        async with db.execute(data_query, (search, search, limit, offset)) as cursor:
            services = await cursor.fetchall()
            return services, total


# === PLAN OPERATIONS ===
async def get_plans():
    """Handles get plans."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM plans') as cursor:
            return await cursor.fetchall()

async def get_plan(plan_id: int):
    """Handles get plan."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM plans WHERE id = ?', (plan_id,)) as cursor:
            return await cursor.fetchone()

# === PACKAGE OPERATIONS ===
async def get_time_packages(plan_id: int):
    """Handles get time packages."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM time_packages WHERE plan_id = ?', (plan_id,)) as cursor:
            return await cursor.fetchall()

async def get_time_package(package_id: int):
    """Handles get time package."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM time_packages WHERE id = ?', (package_id,)) as cursor:
            return await cursor.fetchone()

async def get_traffic_packages(plan_id: int):
    """Handles get traffic packages."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM traffic_packages WHERE plan_id = ?', (plan_id,)) as cursor:
            return await cursor.fetchall()

async def get_traffic_package(package_id: int):
    """Handles get traffic package."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM traffic_packages WHERE id = ?', (package_id,)) as cursor:
            return await cursor.fetchone()

# === CARGO OPERATIONS ===
async def fetch_and_consume_cargo(plan_id: int, time_package_id: int, traffic_package_id: int):
    # ATOMIC TRANSACTION TO PREVENT RACE CONDITIONS
    """Handles fetch and consume cargo."""
    async with aiosqlite.connect(DB_PATH, isolation_level=None) as db:
        db.row_factory = aiosqlite.Row
        await db.execute('BEGIN EXCLUSIVE')
        try:
            async with db.execute(
                'SELECT * FROM licenses_cargo WHERE plan_id = ? AND time_package_id = ? AND traffic_package_id = ? LIMIT 1',
                (plan_id, time_package_id, traffic_package_id)
            ) as cursor:
                cargo = await cursor.fetchone()

            if cargo:
                await db.execute('DELETE FROM licenses_cargo WHERE id = ?', (cargo['id'],))
            await db.execute('COMMIT')
            return cargo
        except Exception as e:
            await db.execute('ROLLBACK')
            raise e

# === INVOICE OPERATIONS ===
async def create_invoice(invoice_data: dict):
    """Handles create invoice."""
    async with aiosqlite.connect(DB_PATH) as db:
        columns = ', '.join(invoice_data.keys())
        placeholders = ', '.join(['?'] * len(invoice_data))
        await db.execute(f'INSERT INTO invoices ({columns}) VALUES ({placeholders})', list(invoice_data.values()))
        await db.commit()

async def get_invoice(invoice_id: str):
    """Handles get invoice."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)) as cursor:
            return await cursor.fetchone()

# === DISCOUNT & GIFT OPERATIONS ===
async def get_discount_code(code: str):
    """Handles get discount code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM discount_codes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

async def get_gift_code(code: str):
    """Handles get gift code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gift_codes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

# === DISCOUNT DB OPERATIONS ===
async def api_get_discounts_list(limit: int, offset: int, q: str):
    """Handles api get discounts list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM Discount WHERE code LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM Discount WHERE code LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_discount(discount_id: int):
    """Handles api get discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Discount WHERE id = ?', (discount_id,)) as cursor:
            return await cursor.fetchone()

async def api_check_discount_exists(code: str):
    """Handles api check discount exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM Discount WHERE code = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0

async def api_add_discount(code: str, price: int, limit_use: int):
    """Handles api add discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO Discount (code, price, limituse, limitused) VALUES (?, ?, ?, 0)', (code, price, limit_use))
        await db.commit()

async def api_delete_discount(discount_id: int):
    """Handles api delete discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM Discount WHERE id = ?', (discount_id,))
        await db.commit()

async def api_get_discount_sell_lists(limit: int, offset: int, q: str):
    """Handles api get discount sell lists."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM DiscountSell WHERE codeDiscount LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM DiscountSell WHERE codeDiscount LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_discount_sell(discount_id: int):
    """Handles api get discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM DiscountSell WHERE id = ?', (discount_id,)) as cursor:
            return await cursor.fetchone()

async def api_check_discount_sell_exists(code: str):
    """Handles api check discount sell exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM DiscountSell WHERE codeDiscount = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0

async def api_add_discount_sell(code: str, percent: int, limit_use: int):
    """Handles api add discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Defaults dropped for panel/product
        await db.execute('INSERT INTO DiscountSell (codeDiscount, price, limitDiscount, usedDiscount) VALUES (?, ?, ?, 0)', (code, percent, limit_use))
        await db.commit()

async def api_delete_discount_sell(discount_id: int):
    """Handles api delete discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM DiscountSell WHERE id = ?', (discount_id,))
        await db.commit()

# === PAYMENT DB OPERATIONS ===
async def api_get_payments_list(limit: int, offset: int, q: str):
    """Handles api get payments list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM Payment_report WHERE id_user LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT id_order as id, id_user, time, price, payment_status, Payment_Method FROM Payment_report WHERE id_user LIKE ? OR id_order LIKE ? LIMIT ? OFFSET ?', (search, search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_payment(id_order: int):
    """Handles api get payment."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Payment_report WHERE id_order = ?', (id_order,)) as cursor:
            return await cursor.fetchone()

# === SETTING DB OPERATIONS ===
async def api_update_setting(key: str, value: str):
    """Handles api update setting."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'UPDATE setting SET {key} = ?', (value,))
        await db.commit()

async def api_get_settings():
    """Handles api get settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM setting LIMIT 1') as cursor:
            return await cursor.fetchone()

async def api_update_settings_batch(updates: dict):
    """Handles api update settings batch."""
    async with aiosqlite.connect(DB_PATH) as db:
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        await db.execute(f'UPDATE setting SET {set_clause}', values)
        await db.commit()

# === LOGGING OPERATIONS ===
async def api_insert_log(header: dict, data: dict, ip: str, actions: str):
    """Handles api insert log."""
    import json
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        header_json = json.dumps(header)
        data_json = json.dumps(data)
        time_str = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        await db.execute('INSERT INTO logs_api (header, data, time, ip, actions) VALUES (?, ?, ?, ?, ?)', 
                         (header_json, data_json, time_str, ip, actions))
        await db.commit()

# === STATS OPERATIONS ===
async def get_user_count():
    """Handles get user count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            return (await cursor.fetchone())[0]

async def get_agent_count():
    """Handles get agent count."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Assuming we have an agent column in users
        async with db.execute("SELECT COUNT(*) FROM users WHERE agent != 'f'") as cursor:
            try:
                return (await cursor.fetchone())[0]
            except:
                return 0

async def get_test_cargo_count():
    """Handles get test cargo count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1') as cursor:
            return (await cursor.fetchone())[0]

async def get_bot_stats(timeframe_clause: str = "", timeframe_params: tuple = ()):
    """Handles get bot stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Total Users
        async with db.execute(f"SELECT COUNT(*) FROM users {timeframe_clause}", timeframe_params) as cursor:
            users_count = (await cursor.fetchone())[0]
            
        # Total Orders
        order_timeframe = timeframe_clause.replace("created_at", "created_at") if timeframe_clause else ""
        async with db.execute(f"SELECT COUNT(*) FROM invoices WHERE status != 'pending' {order_timeframe.replace('WHERE', 'AND')}", timeframe_params) as cursor:
            orders_count = (await cursor.fetchone())[0]
            
        # Total Sales Sum
        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status != 'pending' {order_timeframe.replace('WHERE', 'AND')}", timeframe_params) as cursor:
            sales_sum = (await cursor.fetchone())[0] or 0
            
        # Test Licenses Used
        async with db.execute(f"SELECT COUNT(*) FROM invoices WHERE base_price = 0 {order_timeframe.replace('WHERE', 'AND')}", timeframe_params) as cursor:
            test_count = (await cursor.fetchone())[0]
            
        return {
            "users": users_count,
            "orders": orders_count,
            "sales": sales_sum,
            "tests": test_count
        }

async def get_invoice_count():
    """Handles get invoice count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM invoices') as cursor:
            return (await cursor.fetchone())[0]

# === DISCOUNTS & GIFTS ===
async def get_discount_code(code: str, user_id: int):
    """Handles get discount code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM discount_codes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"error": "کد تخفیف یافت نشد یا نامعتبر است."}
            row = dict(row)
            
            # Validations
            if row['expiration_date']:
                from datetime import datetime
                # basic string compare works for YYYY-MM-DD HH:MM:SS
                if datetime.now().strftime('%Y-%m-%d %H:%M:%S') > row['expiration_date']:
                    return {"error": "مهلت استفاده از این کد تخفیف به پایان رسیده است."}
                    
            if row['max_uses'] and row['used_count'] >= row['max_uses']:
                return {"error": "ظرفیت استفاده از این کد تخفیف تکمیل شده است."}
                
            if row['user_id_restriction'] and str(row['user_id_restriction']) != '0' and str(row['user_id_restriction']) != str(user_id):
                return {"error": "این کد تخفیف اختصاصی است و برای حساب کاربری شما قابل استفاده نمی‌باشد."}
                
            return row

# ============================================================
# === XUI PANEL DB OPERATIONS ===
# ============================================================

async def add_xui_panel(name: str, url: str, sub_link: str, bearer_token: str, inbound_ids: str, ip_limit: int, label: str = None) -> int:
    """Insert a new XUI panel definition and return its generated id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO xui_panels (name, url, sub_link, bearer_token, inbound_ids, ip_limit, label) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (name, url.rstrip('/'), sub_link, bearer_token, inbound_ids, ip_limit, label)
        )
        await db.commit()
        return cursor.lastrowid

async def get_xui_panels():
    """Return all defined XUI panels ordered by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM xui_panels ORDER BY id') as cursor:
            return await cursor.fetchall()

async def get_xui_panel(panel_id: int):
    """Return a single XUI panel by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM xui_panels WHERE id = ?', (panel_id,)) as cursor:
            return await cursor.fetchone()

async def delete_xui_panel(panel_id: int):
    """Delete a panel and its bindings (CASCADE)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM xui_panels WHERE id = ?', (panel_id,))
        await db.commit()

# ============================================================
# === PLAN ↔ PANEL BINDING ===
# ============================================================

async def set_plan_panel(plan_id: int, panel_id: int):
    """Bind (or rebind) a plan to a panel using upsert."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO plan_panel (plan_id, panel_id) VALUES (?, ?)'
            ' ON CONFLICT(plan_id) DO UPDATE SET panel_id = excluded.panel_id',
            (plan_id, panel_id)
        )
        await db.commit()

async def get_plan_panel(plan_id: int):
    """Return the panel binding row for a plan, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM plan_panel WHERE plan_id = ?', (plan_id,)) as cursor:
            return await cursor.fetchone()

async def remove_plan_panel(plan_id: int):
    """Remove the panel binding for a plan."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM plan_panel WHERE plan_id = ?', (plan_id,))
        await db.commit()

# ============================================================
# === XUI LICENSE OPERATIONS ===
# ============================================================

async def create_xui_license(invoice_id: str, user_id: int, panel_id: int, sub_id: str, license_note: str = None):
    """Record a newly issued license after successful XUI provisioning."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO xui_licenses (invoice_id, user_id, panel_id, sub_id, license_note) VALUES (?, ?, ?, ?, ?)',
            (invoice_id, user_id, panel_id, sub_id, license_note or '')
        )
        await db.commit()

async def get_licenses_for_user(user_id: int):
    """
    Return all licenses for a user, newest first,
    joined with the panel URL and invoice metadata.
    """
    sql = '''
        SELECT
            l.id, l.invoice_id, l.sub_id, l.license_note, l.created_at,
            p.url AS panel_url, p.label AS panel_label,
            i.days, i.gb, i.plan_id
        FROM xui_licenses l
        LEFT JOIN xui_panels p ON p.id = l.panel_id
        LEFT JOIN invoices i ON i.id = l.invoice_id
        WHERE l.user_id = ?
        ORDER BY l.created_at DESC
    '''
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_license_by_invoice(invoice_id: str):
    """Return the xui_license row for a given invoice, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM xui_licenses WHERE invoice_id = ?', (invoice_id,)) as cursor:
            return await cursor.fetchone()

# ============================================================
# === INVOICE UPDATE HELPERS (XUI-SPECIFIC) ===
# ============================================================

async def update_invoice_license_note(invoice_id: str, note: str):
    """Persist the user's config note on the invoice row."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE invoices SET license_note = ? WHERE id = ?', (note, invoice_id))
        await db.commit()

async def update_invoice_panel_id(invoice_id: str, panel_id: int):
    """Record which panel was used to provision this invoice."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE invoices SET panel_id = ? WHERE id = ?', (panel_id, invoice_id))
        await db.commit()

async def get_invoice_by_id(invoice_id: str):
    """Fetch a full invoice row including new XUI columns."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)) as cursor:
            return await cursor.fetchone()

async def get_gift_code(code: str, user_id: int):
    """Handles get gift code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM gift_codes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"error": "کد هدیه یافت نشد یا نامعتبر است."}
            row = dict(row)
            
            # Validations
            if row['expiration_date']:
                from datetime import datetime
                if datetime.now().strftime('%Y-%m-%d %H:%M:%S') > row['expiration_date']:
                    return {"error": "مهلت استفاده از این کد هدیه به پایان رسیده است."}
                    
            if row['max_uses'] and row['used_count'] >= row['max_uses']:
                return {"error": "ظرفیت استفاده از این کد هدیه تکمیل شده است."}
                
            if row['user_id_restriction'] and str(row['user_id_restriction']) != '0' and str(row['user_id_restriction']) != str(user_id):
                return {"error": "این کد هدیه اختصاصی است و برای حساب کاربری شما قابل استفاده نمی‌باشد."}
                
            return row


# ============================================================
# === OPERATING MODE ===
# ============================================================

async def get_operating_mode() -> str:
    """Return current operating mode: NORMAL | SALES_PAUSED | MAINTENANCE"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'operating_mode'") as cursor:
            row = await cursor.fetchone()
            return (row[0] if row else 'NORMAL') or 'NORMAL'

async def set_operating_mode(mode: str):
    """Set operating mode. mode must be NORMAL, SALES_PAUSED, or MAINTENANCE."""
    assert mode in ('NORMAL', 'SALES_PAUSED', 'MAINTENANCE')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('operating_mode', ?)", (mode,))
        await db.commit()

async def get_setting(key: str, default: str = '') -> str:
    """Generic settings getter (used in various places)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return (row[0] if row else default) or default


# ============================================================
# === WALLET LEDGER ===
# ============================================================

async def wallet_adjust(user_id: int, amount: int, tx_type: str, description: str,
                        related_invoice_id: str = None, unique_key: str = None) -> tuple:
    """
    Atomically adjust a user's wallet balance and record a ledger entry.
    - amount: positive = credit, negative = debit
    - Returns (ok: bool, new_balance: int)
    - Idempotent: if unique_key already exists, returns (True, current_balance) without re-applying.
    """
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Idempotency check
        if unique_key:
            async with db.execute(
                "SELECT id FROM wallet_transactions WHERE unique_key = ?", (unique_key,)
            ) as cur:
                if await cur.fetchone():
                    # Already applied — return current balance
                    async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as c2:
                        row = await c2.fetchone()
                        return (True, int(row['balance']) if row else 0)

        # Fetch current balance
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return (False, 0)

        current = int(row['balance'])
        new_balance = current + amount

        # Prevent negative balance on debit
        if new_balance < 0:
            return (False, current)

        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
        await db.execute(
            """INSERT INTO wallet_transactions
               (user_id, amount, balance_after, type, description, related_invoice_id, unique_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, amount, new_balance, tx_type, description, related_invoice_id, unique_key,
             int(_time.time()))
        )
        await db.commit()
        return (True, new_balance)


async def get_wallet_history(user_id: int, limit: int = 15):
    """Return the last N wallet transaction rows for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()


# ============================================================
# === CASHBACK ===
# ============================================================

async def get_cashback_percent() -> float:
    """Return cashback percentage from settings (0–100)."""
    val = await get_setting('cashback_percent', '0')
    try:
        return float(val)
    except Exception:
        return 0.0

async def credit_cashback(invoice_id: str, user_id: int, paid_amount: int) -> dict | None:
    """
    Credit cashback to the buyer's wallet after an approved invoice.
    Idempotent — one cashback per invoice_id.
    Returns {'user_id', 'amount', 'balance'} or None.
    """
    percent = await get_cashback_percent()
    if percent <= 0 or paid_amount <= 0:
        return None

    cashback_amount = int(paid_amount * percent / 100)
    if cashback_amount <= 0:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO cashback_rewards (invoice_id, user_id, amount) VALUES (?, ?, ?)",
                (invoice_id, user_id, cashback_amount)
            )
            await db.commit()
        except Exception:
            # Duplicate — cashback already credited
            return None

    ok, new_balance = await wallet_adjust(
        user_id, cashback_amount, 'CASHBACK',
        f"کش‌بک خرید (فاکتور {invoice_id})",
        related_invoice_id=invoice_id,
        unique_key=f"cashback:{invoice_id}"
    )
    if not ok:
        return None
    return {'user_id': user_id, 'amount': cashback_amount, 'balance': new_balance}


# ============================================================
# === REFERRAL / AFFILIATE ===
# ============================================================

import random
import string

def _gen_ref_code(user_id: int) -> str:
    """Handles  gen ref code."""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"REF{user_id}{suffix}"

async def get_or_create_referral_code(user_id: int) -> str:
    """Return the user's unique referral code, creating one if needed."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT code FROM referral_codes WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        code = _gen_ref_code(user_id)
        await db.execute(
            "INSERT OR IGNORE INTO referral_codes (user_id, code) VALUES (?, ?)", (user_id, code)
        )
        await db.commit()
        return code

async def get_user_id_by_referral_code(code: str) -> int | None:
    """Look up who owns a referral code."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM referral_codes WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None

async def set_referred_by(user_id: int, referrer_id: int) -> bool:
    """
    Set referred_by on a user atomically — only if not already set and not self-referral.
    Returns True if successfully set, False otherwise.
    """
    if user_id == referrer_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row['referred_by'] is not None:
            return False  # User doesn't exist or already has a referrer
        await db.execute("UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL",
                         (referrer_id, user_id))
        await db.commit()
        return True

async def get_referral_stats(user_id: int) -> dict:
    """Return referral stats for the user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE referred_by = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            invited = int(row['cnt']) if row else 0
        async with db.execute(
            """SELECT COUNT(DISTINCT rc.referred_id) AS buyers,
                      COALESCE(SUM(rc.commission_amount), 0) AS earned
               FROM referral_commissions rc WHERE rc.referrer_id = ?""",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            buyers = int(row['buyers']) if row else 0
            earned = int(row['earned']) if row else 0
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            balance = int(row['balance']) if row else 0
    return {'invited': invited, 'buyers': buyers, 'earned': earned, 'balance': balance}

async def credit_referral_commission(invoice_id: str) -> dict | None:
    """
    Credit the referrer's wallet for a purchase.
    Idempotent — one commission per invoice_id (enforced by UNIQUE constraint).
    Returns {'referrer_id', 'amount', 'balance'} or None.
    """
    # Check if referral enabled
    enabled = await get_setting('referral_enabled', '0')
    if enabled != '1':
        return None

    percent_str = await get_setting('referral_commission_percent', '0')
    try:
        percent = float(percent_str)
    except Exception:
        percent = 0.0
    if percent <= 0:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, final_amount FROM invoices WHERE id = ?", (invoice_id,)
        ) as cur:
            inv = await cur.fetchone()
        if not inv:
            return None

        buyer_id = int(inv['user_id'])
        paid_amount = int(inv['final_amount'] or 0)
        if paid_amount <= 0:
            return None

        async with db.execute("SELECT referred_by FROM users WHERE id = ?", (buyer_id,)) as cur:
            user_row = await cur.fetchone()
        if not user_row or not user_row['referred_by']:
            return None

        referrer_id = int(user_row['referred_by'])
        commission = int(paid_amount * percent / 100)
        if commission <= 0:
            return None

        # Insert — UNIQUE on purchase_invoice_id prevents duplicates
        try:
            await db.execute(
                """INSERT INTO referral_commissions
                   (referrer_id, referred_id, purchase_invoice_id, commission_amount)
                   VALUES (?, ?, ?, ?)""",
                (referrer_id, buyer_id, invoice_id, commission)
            )
            await db.commit()
        except Exception:
            return None  # Already credited

    ok, new_balance = await wallet_adjust(
        referrer_id, commission, 'COMMISSION',
        f"پورسانت از خرید کاربر {buyer_id} (فاکتور {invoice_id})",
        related_invoice_id=invoice_id,
        unique_key=f"commission:{invoice_id}"
    )
    if not ok:
        return None
    return {'referrer_id': referrer_id, 'amount': commission, 'balance': new_balance}


# ============================================================
# === CUSTOMER FEEDBACK ===
# ============================================================

async def save_feedback(user_id: int, invoice_id: str, rating: int, comment: str = None):
    """Save a 1-5 star rating (+ optional comment) for a purchase."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO customer_feedback (user_id, invoice_id, rating, comment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, invoice_id, max(1, min(5, rating)), comment, int(_time.time()))
        )
        await db.commit()


# ============================================================
# === ACQUISITION SURVEY ===
# ============================================================

async def maybe_mark_acquisition_asked(user_id: int) -> bool:
    """
    Insert a row in user_acquisition (asked_at = now) if not already there.
    Returns True if the row was newly created (survey should be sent), False if already asked.
    """
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO user_acquisition (user_id, asked_at) VALUES (?, ?)",
                (user_id, int(_time.time()))
            )
            await db.commit()
            return True
        except Exception:
            return False  # Row already exists

async def save_acquisition_source(user_id: int, source: str, detail: str = None):
    """Save the acquisition survey answer."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE user_acquisition
               SET source = ?, detail = ?, answered_at = ?
               WHERE user_id = ?""",
            (source, detail, int(_time.time()), user_id)
        )
        await db.commit()


# ============================================================
# === INVOICE STATUS HELPERS ===
# ============================================================

async def mark_invoice_processing(invoice_id: str):
    """Mark invoice as processing (admin approved, provisioning started)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE invoices SET status = 'processing' WHERE id = ? AND status = 'pending'",
            (invoice_id,)
        )
        await db.commit()

async def mark_invoice_approved(invoice_id: str):
    """Mark invoice as approved (provisioning succeeded)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE invoices SET status = 'approved' WHERE id = ? AND status IN ('processing', 'issue')",
            (invoice_id,)
        )
        await db.commit()

async def mark_invoice_issue(invoice_id: str, error: str):
    """Mark invoice as issue (provisioning failed)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE invoices SET status = 'issue', last_error = ? WHERE id = ?",
            (error[:1000], invoice_id)
        )
        await db.commit()

async def get_processing_invoices():
    """Return all invoices stuck in 'processing' status (for startup recovery)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM invoices WHERE status = 'processing' ORDER BY created_at ASC LIMIT 50"
        ) as cur:
            return await cur.fetchall()
