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
            # Support system columns
            "ALTER TABLE support_tickets ADD COLUMN user_message_id INTEGER",
            "ALTER TABLE support_tickets ADD COLUMN agent_message_id INTEGER",
            "ALTER TABLE support_tickets ADD COLUMN text_or_caption TEXT",
            "ALTER TABLE support_tickets ADD COLUMN subject TEXT",
            "ALTER TABLE departments ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            # Commission Agency system columns
            "ALTER TABLE users ADD COLUMN agent_referrer_id INTEGER",
            "ALTER TABLE users ADD COLUMN agent_commission_balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN agent_settlement_active INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(migration_sql)
            except Exception:
                pass  # Column already exists

        # Ensure channels table exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remark TEXT,
                linkjoin TEXT,
                link TEXT
            )
        """)

        # Seed default operating mode if not set
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('operating_mode', 'api')")
        
        # Insert default department if none exist
        async with db.execute("SELECT COUNT(*) FROM departments") as cursor:
            if (await cursor.fetchone())[0] == 0:
                await db.execute("INSERT INTO departments (name) VALUES ('عمومی')")
                
        await db.commit()
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
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_status', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_reward_type', 'percent')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_reward_amount', '0')"
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
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('plans_difference_text', '')"
        )
        # Agency settings
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('agent_default_text', '💼 به بخش نمایندگی کندی کانکت خوش آمدید!\n\nبا دعوت دوستان و کاربران خود، از هر خرید آن‌ها کمیسیون نقدی دریافت کنید و درآمد پایدار داشته باشید.')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('agent_commission_percent', '15')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('agent_min_settlement_amount', '1000000')"
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

async def create_user(user_id: int, username: str) -> bool:
    """Handles create user. Returns True if a new user was inserted, False otherwise."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)', (user_id, username))
        await db.commit()
        return cursor.rowcount > 0

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

# === REPORTS DB OPERATIONS ===
async def set_report_setting(key: str, value: str):
    """Sets a report-related setting (group id or topic thread id)."""
    await set_setting(key, value)

async def get_report_setting(key: str):
    """Gets a report-related setting. Returns integer if exists, else None."""
    val = await get_setting(key)
    return int(val) if val and val.isdigit() else (int(val) if val else None)

async def delete_user_completely(user_id: int) -> dict:
    """
    Permanently removes a user and all their associated data from every table.
    Returns a summary dict of how many rows were deleted from each table.
    """
    summary = {}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = OFF')  # Manual cascade

        # Tables and their user_id column name
        deletions = [
            ("support_tickets",        "user_id"),
            ("wallet_transactions",     "user_id"),
            ("cashback_rewards",        "user_id"),
            ("customer_feedback",       "user_id"),
            ("user_acquisition",        "user_id"),
            ("free_trial_usage",        "user_id"),
            ("referral_codes",          "user_id"),
            ("referral_commissions",    "referrer_id"),
            ("referral_commissions",    "referred_id"),
            ("xui_licenses",            "user_id"),
            ("payment_reports",         "user_id"),
            ("invoices",                "user_id"),
            ("users",                   "id"),
        ]

        for table, col in deletions:
            try:
                cursor = await db.execute(f"DELETE FROM {table} WHERE {col} = ?", (user_id,))
                key = f"{table}.{col}"
                summary[key] = summary.get(key, 0) + cursor.rowcount
            except Exception:
                pass

        await db.execute('PRAGMA foreign_keys = ON')
        await db.commit()

    return summary


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

async def get_advanced_bot_stats(timeframe_clause: str = "", timeframe_params: tuple = ()):
    """Handles get advanced bot stats."""
    import time
    async with aiosqlite.connect(DB_PATH) as db:
        # User Stats
        async with db.execute(f"SELECT COUNT(*) FROM users {timeframe_clause}", timeframe_params) as cursor:
            total_users = (await cursor.fetchone())[0]
            
        async with db.execute("SELECT COUNT(DISTINCT user_id) FROM invoices WHERE status IN ('paid', 'approved')") as cursor:
            users_with_purchase = (await cursor.fetchone())[0]
            
        async with db.execute(f"SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1") as cursor:
            test_accounts_cargo = (await cursor.fetchone())[0]
        
        async with db.execute(f"SELECT COUNT(*) FROM payment_reports WHERE payment_method = 'free_test'") as cursor:
            test_accounts_report = (await cursor.fetchone())[0]
            
        test_accounts = test_accounts_cargo + test_accounts_report
            
        async with db.execute("SELECT SUM(balance) FROM users") as cursor:
            total_balance = (await cursor.fetchone())[0] or 0
            
        async with db.execute("SELECT AVG(rating), COUNT(rating) FROM customer_feedback") as cursor:
            row = await cursor.fetchone()
            avg_poll_rating = round(row[0] or 0.0, 1)
            poll_count = row[1] or 0

        # Finance & Sales Stats
        order_timeframe = timeframe_clause.replace("WHERE ", "AND ") if timeframe_clause else ""
        
        async with db.execute(f"SELECT COUNT(id) FROM invoices WHERE status IN ('paid', 'approved') {order_timeframe}", timeframe_params) as cursor:
            total_sales_count = (await cursor.fetchone())[0] or 0
            
        async with db.execute(f"SELECT COUNT(id) FROM xui_licenses") as cursor:
            active_services_sales_count = (await cursor.fetchone())[0] or 0
            
        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') {order_timeframe}", timeframe_params) as cursor:
            total_sales_amount = (await cursor.fetchone())[0] or 0
            
        # Approximation for active services amount: total sales in last 30 days
        thirty_days_ago = time.time() - (30 * 24 * 3600)
        async with db.execute("SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND created_at >= datetime(?, 'unixepoch')", (thirty_days_ago,)) as cursor:
            active_services_sales_amount = (await cursor.fetchone())[0] or 0
            
        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND renew_license_id IS NOT NULL {order_timeframe}", timeframe_params) as cursor:
            total_renewal_amount = (await cursor.fetchone())[0] or 0
            
        async with db.execute(f"SELECT COUNT(id) FROM invoices WHERE status IN ('paid', 'approved') AND renew_license_id IS NOT NULL {order_timeframe}", timeframe_params) as cursor:
            renewals_count = (await cursor.fetchone())[0] or 0

        # Derived metrics
        conversion_rate = (users_with_purchase / total_users * 100) if total_users > 0 else 0
        avg_purchase = (total_sales_amount / users_with_purchase) if users_with_purchase > 0 else 0
        
        # Estimated monthly revenue (sales from last 30 days)
        # Using unix timestamp or datetime? invoices.created_at is TIMESTAMP DEFAULT CURRENT_TIMESTAMP (like '2023-10-01 12:00:00')
        async with db.execute("SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND created_at >= date('now', '-30 days')") as cursor:
            estimated_monthly_revenue = (await cursor.fetchone())[0] or 0
            
        # Recalculate active_services_sales_amount correctly since the previous approach used unixepoch
        async with db.execute("SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND created_at >= date('now', '-30 days')") as cursor:
            active_services_sales_amount = (await cursor.fetchone())[0] or 0
            
        renewal_percentage = (renewals_count / total_sales_count * 100) if total_sales_count > 0 else 0

        return {
            "total_users": total_users,
            "users_with_purchase": users_with_purchase,
            "test_accounts": test_accounts,
            "total_balance": total_balance,
            "avg_poll_rating": avg_poll_rating,
            "poll_count": poll_count,
            "total_sales_count": total_sales_count,
            "active_services_sales_count": active_services_sales_count,
            "total_sales_amount": total_sales_amount,
            "active_services_sales_amount": active_services_sales_amount,
            "total_renewal_amount": total_renewal_amount,
            "conversion_rate": round(conversion_rate, 2),
            "avg_purchase": round(avg_purchase, 0),
            "estimated_monthly_revenue": estimated_monthly_revenue,
            "renewal_percentage": round(renewal_percentage, 2)
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
    status = await get_setting('referral_status', '0')
    if status != '1':
        return None

    r_type = await get_setting('referral_reward_type', 'percent')
    val_str = await get_setting('referral_reward_amount', '0')
    try:
        val = float(val_str)
    except Exception:
        val = 0.0
    if val <= 0:
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
        
        if r_type == 'fixed':
            commission = int(val)
        else:
            commission = int(paid_amount * val / 100)
            
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
        f"پاداش بابت خرید کاربر {buyer_id} (فاکتور {invoice_id})",
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

# ============================================================
# USER LISTS & GLOBAL CHARGE
# ============================================================

async def get_all_users_detailed():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, username, balance FROM users ORDER BY created_at DESC") as cur:
            return await cur.fetchall()

async def get_users_positive_balance():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, username, balance FROM users WHERE balance > 0 ORDER BY balance DESC") as cur:
            return await cur.fetchall()

async def get_users_negative_balance():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, username, balance FROM users WHERE balance < 0 ORDER BY balance ASC") as cur:
            return await cur.fetchall()

async def get_users_with_referrals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # users who have affiliatescount > 0 OR exist as referrer in referral_commissions
        async with db.execute("""
            SELECT id, username, balance, affiliatescount 
            FROM users 
            WHERE affiliatescount > 0 
               OR id IN (SELECT referrer_id FROM referral_commissions)
            ORDER BY affiliatescount DESC
        """) as cur:
            return await cur.fetchall()

async def add_global_balance(amount: int) -> list:
    """Adds balance to all active users. Returns list of affected user IDs."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM users WHERE is_active = 1") as cur:
            user_ids = [row['id'] for row in await cur.fetchall()]
        if user_ids:
            await db.execute("UPDATE users SET balance = balance + ? WHERE is_active = 1", (amount,))
            await db.commit()
        return user_ids

async def get_invoice_details(invoice_id: str):
    """Fetch complete details of an invoice for search."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT i.*, u.username, x.sub_id, x.panel_id, p.url as panel_url
            FROM invoices i
            LEFT JOIN users u ON i.user_id = u.id
            LEFT JOIN xui_licenses x ON i.id = x.invoice_id
            LEFT JOIN xui_panels p ON x.panel_id = p.id
            WHERE i.id = ?
        """, (invoice_id,)) as cur:
            return await cur.fetchone()

async def get_all_active_xui_licenses_non_trial():
    """Get all active xui_licenses that are not free trials to add traffic/time."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT xl.id, xl.invoice_id, xl.user_id, xl.panel_id, xl.sub_id, xl.license_note,
                   p.url as panel_url, p.bearer_token, p.ip_limit
            FROM xui_licenses xl
            JOIN xui_panels p ON xl.panel_id = p.id
            JOIN invoices i ON xl.invoice_id = i.id
            WHERE i.status = 'approved' AND i.base_price > 0
        """) as cur:
            return await cur.fetchall()

async def get_users_with_active_licenses():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT DISTINCT u.id, u.username, u.balance
            FROM users u
            JOIN invoices i ON u.id = i.user_id
            JOIN xui_licenses xl ON i.id = xl.invoice_id
            WHERE i.status = 'approved'
            ORDER BY u.created_at DESC
        """) as cur:
            return await cur.fetchall()

async def add_trial_users_balance(amount: int) -> list:
    """Adds balance to users who received a free trial but didn't buy anything. Returns list of affected user IDs."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id FROM users
            WHERE is_active = 1
            AND id IN (
                SELECT user_id FROM free_trial_usage
                UNION
                SELECT user_id FROM invoices WHERE base_price = 0
            )
            AND id NOT IN (
                SELECT user_id FROM invoices WHERE base_price > 0 AND status = 'approved'
            )
        """) as cur:
            user_ids = [row['id'] for row in await cur.fetchall()]
        if user_ids:
            await db.execute("""
                UPDATE users SET balance = balance + ?
                WHERE is_active = 1
                AND id IN (
                    SELECT user_id FROM free_trial_usage
                    UNION
                    SELECT user_id FROM invoices WHERE base_price = 0
                )
                AND id NOT IN (
                    SELECT user_id FROM invoices WHERE base_price > 0 AND status = 'approved'
                )
            """, (amount,))
            await db.commit()
        return user_ids

# ============================================================
# DEPARTMENT MANAGEMENT
# ============================================================

async def get_departments(active_only: bool = False):
    """Returns all departments (or only active ones)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM departments"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id ASC"
        async with db.execute(query) as cur:
            return await cur.fetchall()

async def get_department(dept_id: int):
    """Returns a single department by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM departments WHERE id = ?", (dept_id,)) as cur:
            return await cur.fetchone()

async def add_department(name: str) -> bool:
    """Adds a new department. Returns True on success, False if name already exists."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO departments (name) VALUES (?)", (name,)
            )
            await db.commit()
        return True
    except Exception:
        return False

async def remove_department(dept_id: int):
    """Removes a department by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
        await db.commit()

async def get_department_by_name(name: str):
    """Returns a single department by name."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM departments WHERE name = ?", (name,)) as cur:
            return await cur.fetchone()

async def set_department_support_user(dept_id: int, agent_id):
    """Sets the support agent (user_id) for a department. Pass None to clear."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE departments SET support_user_id = ? WHERE id = ?",
            (agent_id, dept_id)
        )
        await db.commit()

set_department_agent = set_department_support_user

async def toggle_department_active(dept_id: int, is_active: bool):
    """Activates or deactivates a department."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE departments SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, dept_id)
        )
        await db.commit()

# ============================================================
# SUPPORT TICKETS
# ============================================================

async def create_support_ticket(
    user_id: int,
    department_id: int = None,
    user_message_id: int = None,
    text_or_caption: str = None,
    subject: str = None,
    status: str = 'unanswered'
) -> int:
    """Creates a new support ticket and returns its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO support_tickets 
               (user_id, department_id, user_message_id, text_or_caption, subject, status) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, department_id, user_message_id, text_or_caption, subject, status)
        )
        await db.commit()
        return cur.lastrowid

async def update_support_ticket_answered(ticket_id: int, agent_message_id: int = None):
    """Marks a support ticket as answered and records the agent's response message ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE support_tickets SET status = 'answered', agent_message_id = ? WHERE id = ?",
            (agent_message_id, ticket_id)
        )
        await db.commit()

async def get_support_ticket(ticket_id: int):
    """Returns a single support ticket by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)) as cur:
            return await cur.fetchone()

async def get_open_tickets_for_dept(department_id: int):
    """Returns all open or unanswered tickets for a given department."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM support_tickets WHERE department_id = ? AND status IN ('open', 'unanswered') ORDER BY created_at ASC",
            (department_id,)
        ) as cur:
            return await cur.fetchall()

async def get_user_open_ticket(user_id: int):
    """Returns the user's latest open or unanswered ticket, if any."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM support_tickets WHERE user_id = ? AND status IN ('open', 'unanswered') ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ) as cur:
            return await cur.fetchone()

async def close_support_ticket(ticket_id: int):
    """Closes a support ticket."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,)
        )
        await db.commit()

async def add_support_message(ticket_id: int, sender_id: int, sender_role: str, message_id: int = None, text: str = None):
    """Appends a message to a support ticket."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO support_messages (ticket_id, sender_id, sender_role, message_id, text) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, sender_id, sender_role, message_id, text)
        )
        await db.commit()

# Alias for backward compatibility with admin_support.py
set_department_support_user = set_department_agent


# === EXPIRED DATA CLEANUP (TICKETS, LICENSES, INVOICES) ===
async def cleanup_expired_data(retention_days: int = 14) -> dict:
    """
    Cleans up expired data from the bot's database (every 2 weeks or on demand)
    for storage and performance optimization:
    1. Support tickets (closed, or answered older than retention_days) and their messages.
    2. Expired licenses (checked via XUI sub-link stats or invoice validity).
    3. Expired invoices (status='expired', pending > retention_days, failed/canceled > retention_days)
       and their payment reports.
    4. Executes SQLite VACUUM and PRAGMA optimize to defragment and shrink candy.db on disk.
    
    NOTE: Operates strictly within the bot's database/memory; no messages in user PVs are deleted.
    """
    import os
    import time
    import logging
    import asyncio
    from utils.date_formatter import get_current_jalali
    
    logger = logging.getLogger(__name__)
    
    db_size_before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    
    deleted_tickets = 0
    deleted_ticket_messages = 0
    deleted_licenses = 0
    deleted_invoices = 0
    deleted_payment_reports = 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # -------------------------------------------------------------
        # 1. CLEANUP SUPPORT TICKETS & MESSAGES
        # -------------------------------------------------------------
        try:
            async with db.execute(f"""
                SELECT id FROM support_tickets 
                WHERE status = 'closed'
                   OR (status = 'answered' AND created_at < datetime('now', '-{retention_days} days'))
            """) as cur:
                ticket_rows = await cur.fetchall()
            
            ticket_ids = [row['id'] for row in ticket_rows]
            if ticket_ids:
                placeholders = ",".join("?" for _ in ticket_ids)
                cur_msg = await db.execute(
                    f"DELETE FROM support_messages WHERE ticket_id IN ({placeholders})", 
                    ticket_ids
                )
                deleted_ticket_messages = cur_msg.rowcount if cur_msg.rowcount > 0 else 0
                
                cur_tkt = await db.execute(
                    f"DELETE FROM support_tickets WHERE id IN ({placeholders})", 
                    ticket_ids
                )
                deleted_tickets = cur_tkt.rowcount if cur_tkt.rowcount > 0 else 0
        except Exception as e:
            logger.error(f"Error cleaning support tickets: {e}")

        # -------------------------------------------------------------
        # 2. IDENTIFY AND CLEANUP EXPIRED LICENSES (xui_licenses)
        # -------------------------------------------------------------
        expired_license_ids = set()
        try:
            async with db.execute("""
                SELECT l.id, l.user_id, l.sub_id, l.invoice_id, l.created_at,
                       p.sub_link, p.url as panel_url,
                       i.days as invoice_days, i.status as invoice_status, i.created_at as invoice_created_at
                FROM xui_licenses l
                LEFT JOIN xui_panels p ON l.panel_id = p.id
                LEFT JOIN invoices i ON l.invoice_id = i.id
            """) as cur:
                license_rows = await cur.fetchall()

            from bot.services.sub_stats import fetch_sub_stats
            
            async def check_single_license(lic_row):
                lic_id = lic_row['id']
                inv_status = lic_row['invoice_status']
                sub_link = lic_row['sub_link']
                sub_id = lic_row['sub_id']
                
                if inv_status in ('expired', 'canceled', 'failed'):
                    return lic_id

                if sub_link and sub_id:
                    try:
                        stats = await asyncio.wait_for(fetch_sub_stats(sub_link, sub_id), timeout=8.0)
                        if stats:
                            if stats.get('is_expired'):
                                return lic_id
                            if not stats.get('is_unlimited_time') and stats.get('days_left', 1) <= 0:
                                return lic_id
                            if not stats.get('is_unlimited_traffic') and stats.get('remaining_gb', 1) <= 0:
                                return lic_id
                    except Exception:
                        pass
                return None

            sem = asyncio.Semaphore(10)
            async def bounded_check(row):
                async with sem:
                    return await check_single_license(row)

            if license_rows:
                tasks = [bounded_check(row) for row in license_rows]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, int):
                        expired_license_ids.add(res)

            # Date-based expiration check for remaining licenses
            async with db.execute(f"""
                SELECT l.id FROM xui_licenses l
                JOIN invoices i ON l.invoice_id = i.id
                WHERE i.days > 0 
                  AND datetime(l.created_at, '+' || (i.days + {retention_days}) || ' days') < datetime('now')
            """) as cur:
                date_expired = await cur.fetchall()
                for r in date_expired:
                    expired_license_ids.add(r[0])

            # Orphaned licenses older than retention period
            async with db.execute(f"""
                SELECT l.id FROM xui_licenses l
                LEFT JOIN invoices i ON l.invoice_id = i.id
                WHERE i.id IS NULL AND l.created_at < datetime('now', '-{retention_days} days')
            """) as cur:
                orphan_lics = await cur.fetchall()
                for r in orphan_lics:
                    expired_license_ids.add(r[0])

            if expired_license_ids:
                lic_id_list = list(expired_license_ids)
                placeholders = ",".join("?" for _ in lic_id_list)
                cur_lic = await db.execute(
                    f"DELETE FROM xui_licenses WHERE id IN ({placeholders})", 
                    lic_id_list
                )
                deleted_licenses = cur_lic.rowcount if cur_lic.rowcount > 0 else 0
        except Exception as e:
            logger.error(f"Error cleaning expired licenses: {e}")

        # -------------------------------------------------------------
        # 3. CLEANUP EXPIRED INVOICES & PAYMENT REPORTS
        # -------------------------------------------------------------
        try:
            async with db.execute(f"""
                SELECT id FROM invoices 
                WHERE status = 'expired'
                   OR (status = 'pending' AND created_at < datetime('now', '-{retention_days} days'))
                   OR (status IN ('canceled', 'failed') AND created_at < datetime('now', '-{retention_days} days'))
            """) as cur:
                inv_rows = await cur.fetchall()
                
            expired_inv_ids = [row['id'] for row in inv_rows]
            
            if expired_inv_ids:
                placeholders = ",".join("?" for _ in expired_inv_ids)
                # First delete any remaining xui_licenses referencing these invoices
                await db.execute(f"DELETE FROM xui_licenses WHERE invoice_id IN ({placeholders})", expired_inv_ids)
                
                # Delete payment reports related to these invoices
                cur_pr = await db.execute(
                    f"DELETE FROM payment_reports WHERE invoice_id IN ({placeholders})", 
                    expired_inv_ids
                )
                deleted_payment_reports += cur_pr.rowcount if cur_pr.rowcount > 0 else 0
                
                # Delete from invoices
                cur_inv = await db.execute(
                    f"DELETE FROM invoices WHERE id IN ({placeholders})", 
                    expired_inv_ids
                )
                deleted_invoices = cur_inv.rowcount if cur_inv.rowcount > 0 else 0

            # Delete any expired offline reports or abandoned unpaid payment reports
            cur_pr_extra = await db.execute(f"""
                DELETE FROM payment_reports 
                WHERE status = 'expire' 
                   OR (status = 'Unpaid' AND created_at < datetime('now', '-{retention_days} days'))
            """)
            deleted_payment_reports += cur_pr_extra.rowcount if cur_pr_extra.rowcount > 0 else 0

        except Exception as e:
            logger.error(f"Error cleaning expired invoices: {e}")

        await db.commit()

        # -------------------------------------------------------------
        # 4. OPTIMIZATION & VACUUM (Reclaim storage & optimize queries)
        # -------------------------------------------------------------
        try:
            await db.execute("PRAGMA optimize;")
            await db.execute("VACUUM;")
        except Exception as e:
            logger.error(f"Error executing VACUUM/optimize: {e}")

    db_size_after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    freed_bytes = max(0, db_size_before - db_size_after)

    summary = {
        "deleted_tickets": deleted_tickets,
        "deleted_ticket_messages": deleted_ticket_messages,
        "deleted_licenses": deleted_licenses,
        "deleted_invoices": deleted_invoices,
        "deleted_payment_reports": deleted_payment_reports,
        "db_size_before_bytes": db_size_before,
        "db_size_after_bytes": db_size_after,
        "freed_bytes": freed_bytes,
        "timestamp": int(time.time()),
        "jalali_date": get_current_jalali()
    }
    
    logger.info(f"Database cleanup finished: {summary}")
    return summary


# ============================================================
# COMMISSION AGENT / AGENCY (نمایندگی کمیسیونی)
# ============================================================

async def set_agent_referrer(user_id: int, agent_id: int) -> bool:
    """
    Set agent_referrer_id on a user atomically — only if not already set and not self-referral.
    Returns True if successfully set, False otherwise.
    """
    if user_id == agent_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT agent_referrer_id FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row['agent_referrer_id'] is not None:
            return False
        await db.execute(
            "UPDATE users SET agent_referrer_id = ? WHERE id = ? AND agent_referrer_id IS NULL",
            (agent_id, user_id)
        )
        await db.commit()
        return True


async def get_agent_stats(user_id: int) -> dict:
    """
    Fetch comprehensive agent statistics:
    - invited: total users referred via agent link
    - buyers: unique referred users who purchased
    - total_earned: total commissions ever credited
    - commission_balance: current spendable/withdrawable commission balance
    - settlement_active: whether settlement button is permanently activated
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) AS cnt FROM users WHERE agent_referrer_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            invited = int(row['cnt']) if row else 0

        async with db.execute("""
            SELECT COUNT(DISTINCT buyer_id) AS buyers,
                   COALESCE(SUM(commission_amount), 0) AS earned
            FROM agent_commissions WHERE agent_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()
            buyers = int(row['buyers']) if row else 0
            earned = int(row['earned']) if row else 0

        async with db.execute(
            "SELECT agent_commission_balance, agent_settlement_active FROM users WHERE id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            balance = int(row['agent_commission_balance']) if row and row['agent_commission_balance'] is not None else 0
            settlement_active = int(row['agent_settlement_active']) if row and row['agent_settlement_active'] is not None else 0

    return {
        'invited': invited,
        'buyers': buyers,
        'total_earned': earned,
        'commission_balance': balance,
        'settlement_active': settlement_active
    }


async def credit_agent_commission(invoice_id: str) -> dict | None:
    """
    Credit the agent's commission balance for a purchase made by their sub-user.
    Idempotent — one commission per invoice_id (enforced by UNIQUE constraint).
    Returns {'agent_id', 'buyer_id', 'order_amount', 'commission_amount', 'commission_percent', 'new_balance'} or None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, final_amount, status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
        if not inv or inv['status'] not in ('paid', 'approved'):
            return None

        buyer_id = inv['user_id']
        paid_amount = int(inv['final_amount'])
        if paid_amount <= 0:
            return None

        # Check if buyer has an agent referrer
        async with db.execute("SELECT agent_referrer_id FROM users WHERE id = ?", (buyer_id,)) as cur:
            u = await cur.fetchone()
        if not u or not u['agent_referrer_id']:
            return None

        agent_id = int(u['agent_referrer_id'])
        if agent_id == buyer_id:
            return None

        # Idempotency check: already credited?
        async with db.execute("SELECT id FROM agent_commissions WHERE invoice_id = ?", (invoice_id,)) as cur:
            if await cur.fetchone():
                return None

        # Fetch commission percentage
        async with db.execute("SELECT value FROM settings WHERE key = 'agent_commission_percent'") as cur:
            pct_row = await cur.fetchone()
        try:
            percent = float(pct_row['value']) if pct_row and pct_row['value'] else 15.0
        except ValueError:
            percent = 15.0

        if percent <= 0:
            return None

        commission_amount = int(paid_amount * (percent / 100.0))
        if commission_amount <= 0:
            return None

        await db.execute("""
            INSERT INTO agent_commissions (agent_id, buyer_id, invoice_id, order_amount, commission_percent, commission_amount)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_id, buyer_id, invoice_id, paid_amount, percent, commission_amount))

        await db.execute("""
            UPDATE users SET agent_commission_balance = COALESCE(agent_commission_balance, 0) + ? WHERE id = ?
        """, (commission_amount, agent_id))

        async with db.execute("SELECT agent_commission_balance FROM users WHERE id = ?", (agent_id,)) as cur:
            bal_row = await cur.fetchone()
            new_balance = int(bal_row['agent_commission_balance']) if bal_row else commission_amount

        await db.commit()
        return {
            'agent_id': agent_id,
            'buyer_id': buyer_id,
            'order_amount': paid_amount,
            'commission_amount': commission_amount,
            'commission_percent': percent,
            'new_balance': new_balance
        }


async def create_agent_activation_request(user_id: int, commission_balance: int, sub_users_count: int) -> int:
    """Creates a new agent settlement activation request."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO agent_activation_requests (user_id, commission_balance, sub_users_count, status)
            VALUES (?, ?, ?, 'pending')
        """, (user_id, commission_balance, sub_users_count))
        await db.commit()
        return cursor.lastrowid


async def has_pending_activation_request(user_id: int) -> bool:
    """Returns True if the user already has a pending activation request."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM agent_activation_requests WHERE user_id = ? AND status = 'pending'",
            (user_id,)
        ) as cur:
            return bool(await cur.fetchone())


async def get_agent_activation_request(req_id: int) -> dict | None:
    """Fetch an activation request by ID with user info."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT r.*, u.username
            FROM agent_activation_requests r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.id = ?
        """, (req_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_pending_activation_requests(limit: int = 5, offset: int = 0) -> list[dict]:
    """Fetch pending activation requests ordered by commission balance descending."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT r.*, u.username
            FROM agent_activation_requests r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.status = 'pending'
            ORDER BY r.commission_balance DESC, r.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_pending_activation_requests() -> int:
    """Count pending activation requests."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM agent_activation_requests WHERE status = 'pending'") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def approve_agent_activation_request(req_id: int) -> dict | None:
    """Approve activation request and permanently activate settlement button for agent."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_activation_requests WHERE id = ?", (req_id,)) as cur:
            req = await cur.fetchone()
        if not req:
            return None
        user_id = req['user_id']
        await db.execute(
            "UPDATE agent_activation_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (req_id,)
        )
        await db.execute(
            "UPDATE users SET agent_settlement_active = 1 WHERE id = ?",
            (user_id,)
        )
        await db.commit()
        return dict(req)


async def reject_agent_activation_request(req_id: int, reason: str) -> dict | None:
    """Reject activation request with admin reason."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_activation_requests WHERE id = ?", (req_id,)) as cur:
            req = await cur.fetchone()
        if not req:
            return None
        await db.execute("""
            UPDATE agent_activation_requests 
            SET status = 'rejected', reject_reason = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (reason, req_id))
        await db.commit()
        return dict(req)


async def create_agent_settlement(agent_id: int, amount_irt: int, amount_gram: float, gram_price: int, wallet_address: str) -> int | None:
    """
    Atomically deducts amount_irt from agent_commission_balance and creates a settlement record.
    Returns settlement ID on success, None if balance is insufficient.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE users 
            SET agent_commission_balance = agent_commission_balance - ? 
            WHERE id = ? AND agent_commission_balance >= ?
        """, (amount_irt, agent_id, amount_irt))
        if cursor.rowcount == 0:
            return None  # Insufficient balance or race condition

        cur = await db.execute("""
            INSERT INTO agent_settlements (agent_id, amount_irt, amount_gram, gram_price, wallet_address, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (agent_id, amount_irt, amount_gram, gram_price, wallet_address))
        await db.commit()
        return cur.lastrowid


async def get_agent_settlement(settlement_id: int) -> dict | None:
    """Fetch settlement record with agent user details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, u.username
            FROM agent_settlements s
            LEFT JOIN users u ON s.agent_id = u.id
            WHERE s.id = ?
        """, (settlement_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_unsettled_settlements(limit: int = 5, offset: int = 0) -> list[dict]:
    """
    Fetch unsettled (pending or waiting) settlements,
    sorted by amount_irt from highest to lowest.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, u.username
            FROM agent_settlements s
            LEFT JOIN users u ON s.agent_id = u.id
            WHERE s.status IN ('pending', 'waiting')
            ORDER BY s.amount_irt DESC, s.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_unsettled_settlements() -> int:
    """Count unsettled settlements."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM agent_settlements WHERE status IN ('pending', 'waiting')") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def set_settlement_waiting(settlement_id: int) -> bool:
    """Mark a settlement as waiting."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE agent_settlements SET status = 'waiting' WHERE id = ? AND status != 'settled'",
            (settlement_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_settlement_done(settlement_id: int, tx_hash: str) -> dict | None:
    """
    Mark a settlement as settled with tx_hash and timestamp.
    Returns updated settlement dictionary.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_settlements WHERE id = ?", (settlement_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        if row['status'] == 'settled':
            return dict(row)

        await db.execute("""
            UPDATE agent_settlements 
            SET status = 'settled', tx_hash = ?, settled_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (tx_hash, settlement_id))
        await db.commit()

        async with db.execute("""
            SELECT s.*, u.username
            FROM agent_settlements s
            LEFT JOIN users u ON s.agent_id = u.id
            WHERE s.id = ?
        """, (settlement_id,)) as cur:
            updated = await cur.fetchone()
            return dict(updated) if updated else None


async def get_all_settled_settlements() -> list[dict]:
    """
    Fetch all settled records from day 1 for reporting and CSV exports.
    This table is immune from periodic cleanups.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.id,
                   s.agent_id,
                   u.username,
                   s.amount_irt,
                   s.amount_gram,
                   s.gram_price,
                   s.wallet_address,
                   s.tx_hash,
                   s.created_at,
                   s.settled_at
            FROM agent_settlements s
            LEFT JOIN users u ON s.agent_id = u.id
            WHERE s.status = 'settled'
            ORDER BY s.id ASC
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


