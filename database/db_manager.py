# === IMPORTS AND CONFIG ===
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'candy.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

# === DATABASE INITIALIZATION ===
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = ON;')
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            await db.executescript(f.read())
        await db.commit()

async def cleanup_miniapp_migration():
    """Migration to clean up old miniapp-specific settings from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key = 'webapp_theme'")
        await db.commit()

# === USER OPERATIONS ===
async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def create_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)', (user_id, username))
        await db.commit()

async def update_user_step(user_id: int, step: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET step = ? WHERE id = ?', (step, user_id))
        await db.commit()

async def update_user_balance(user_id: int, amount_change: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount_change, user_id))
        await db.commit()

# === GENERIC DB OPERATIONS ===
async def fetch_all(sql: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchall()

async def fetch_one(sql: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchone()

async def fetch_scalar(sql: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def execute(sql: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount

async def get_setting(key: str, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row['value'] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
        await db.commit()

# === AUTH DB OPERATIONS ===
async def user_from_token(token: str):
    return await fetch_one("SELECT * FROM users WHERE token = ?", (token,))

async def issue_token(user_id: int):
    import secrets
    token = secrets.token_hex(20)
    await execute("UPDATE users SET token = ? WHERE id = ?", (token, user_id))
    return token


# === NEW API OPERATIONS ===
async def api_get_users_list(limit: int, offset: int, q: str):
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_user_status(user_id: int, status: str, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # Assuming we have status and description_blocking columns
        await db.execute('UPDATE users SET status = ?, description = ? WHERE id = ?', (status, description, user_id))
        await db.commit()

async def update_user_verify(user_id: int, verify: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET verify = ? WHERE id = ?', (verify, user_id))
        await db.commit()

async def zero_user_balance(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = 0 WHERE id = ?', (user_id,))
        await db.commit()

async def api_create_user_full(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (id) VALUES (?)', (user_id,))
        await db.commit()

async def api_update_user_field(user_id: int, field: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'UPDATE users SET {field} = ? WHERE id = ?', (value, user_id))
        await db.commit()

async def api_transfer_account(old_id: int, new_id: int):
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT id as user_id FROM users WHERE affiliates = ?', (affiliate_id,)) as cursor:
            return await cursor.fetchall()

async def api_remove_affiliates(affiliate_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET affiliates = 0 WHERE affiliates = ?', (affiliate_id,))
        await db.execute('UPDATE users SET affiliatescount = 0 WHERE id = ?', (affiliate_id,))
        await db.commit()

async def api_get_invoices_list(limit: int, offset: int, q: str):
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM plans') as cursor:
            return await cursor.fetchall()

async def get_plan(plan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM plans WHERE id = ?', (plan_id,)) as cursor:
            return await cursor.fetchone()

# === PACKAGE OPERATIONS ===
async def get_time_packages(plan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM time_packages WHERE plan_id = ?', (plan_id,)) as cursor:
            return await cursor.fetchall()

async def get_time_package(package_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM time_packages WHERE id = ?', (package_id,)) as cursor:
            return await cursor.fetchone()

async def get_traffic_packages(plan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM traffic_packages WHERE plan_id = ?', (plan_id,)) as cursor:
            return await cursor.fetchall()

async def get_traffic_package(package_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM traffic_packages WHERE id = ?', (package_id,)) as cursor:
            return await cursor.fetchone()

# === CARGO OPERATIONS ===
async def fetch_and_consume_cargo(plan_id: int, time_package_id: int, traffic_package_id: int):
    # ATOMIC TRANSACTION TO PREVENT RACE CONDITIONS
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
    async with aiosqlite.connect(DB_PATH) as db:
        columns = ', '.join(invoice_data.keys())
        placeholders = ', '.join(['?'] * len(invoice_data))
        await db.execute(f'INSERT INTO invoices ({columns}) VALUES ({placeholders})', list(invoice_data.values()))
        await db.commit()

async def get_invoice(invoice_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)) as cursor:
            return await cursor.fetchone()

# === DISCOUNT & GIFT OPERATIONS ===
async def get_discount_code(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM discount_codes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

async def get_gift_code(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gift_codes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

# === DISCOUNT DB OPERATIONS ===
async def api_get_discounts_list(limit: int, offset: int, q: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM Discount WHERE code LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM Discount WHERE code LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_discount(discount_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Discount WHERE id = ?', (discount_id,)) as cursor:
            return await cursor.fetchone()

async def api_check_discount_exists(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM Discount WHERE code = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0

async def api_add_discount(code: str, price: int, limit_use: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO Discount (code, price, limituse, limitused) VALUES (?, ?, ?, 0)', (code, price, limit_use))
        await db.commit()

async def api_delete_discount(discount_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM Discount WHERE id = ?', (discount_id,))
        await db.commit()

async def api_get_discount_sell_lists(limit: int, offset: int, q: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM DiscountSell WHERE codeDiscount LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM DiscountSell WHERE codeDiscount LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_discount_sell(discount_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM DiscountSell WHERE id = ?', (discount_id,)) as cursor:
            return await cursor.fetchone()

async def api_check_discount_sell_exists(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM DiscountSell WHERE codeDiscount = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0

async def api_add_discount_sell(code: str, percent: int, limit_use: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Defaults dropped for panel/product
        await db.execute('INSERT INTO DiscountSell (codeDiscount, price, limitDiscount, usedDiscount) VALUES (?, ?, ?, 0)', (code, percent, limit_use))
        await db.commit()

async def api_delete_discount_sell(discount_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM DiscountSell WHERE id = ?', (discount_id,))
        await db.commit()

# === PAYMENT DB OPERATIONS ===
async def api_get_payments_list(limit: int, offset: int, q: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM Payment_report WHERE id_user LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT id_order as id, id_user, time, price, payment_status, Payment_Method FROM Payment_report WHERE id_user LIKE ? OR id_order LIKE ? LIMIT ? OFFSET ?', (search, search, limit, offset)) as cursor:
            return await cursor.fetchall(), total

async def api_get_payment(id_order: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Payment_report WHERE id_order = ?', (id_order,)) as cursor:
            return await cursor.fetchone()

# === SETTING DB OPERATIONS ===
async def api_update_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'UPDATE setting SET {key} = ?', (value,))
        await db.commit()

async def api_get_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM setting LIMIT 1') as cursor:
            return await cursor.fetchone()

async def api_update_settings_batch(updates: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        await db.execute(f'UPDATE setting SET {set_clause}', values)
        await db.commit()

# === LOGGING OPERATIONS ===
async def api_insert_log(header: dict, data: dict, ip: str, actions: str):
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            return (await cursor.fetchone())[0]

async def get_agent_count():
    async with aiosqlite.connect(DB_PATH) as db:
        # Assuming we have an agent column in users
        async with db.execute("SELECT COUNT(*) FROM users WHERE agent != 'f'") as cursor:
            try:
                return (await cursor.fetchone())[0]
            except:
                return 0

async def get_test_cargo_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1') as cursor:
            return (await cursor.fetchone())[0]

async def get_bot_stats(timeframe_clause: str = "", timeframe_params: tuple = ()):
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM invoices') as cursor:
            return (await cursor.fetchone())[0]

# === DISCOUNTS & GIFTS ===
async def get_discount_code(code: str, user_id: int):
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

async def get_gift_code(code: str, user_id: int):
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
