"""
db_manager.py
-------------
Module containing functionalities for db_manager.
"""

# === IMPORTS AND CONFIG ===
import aiosqlite
import os
import shutil
import logging
import random
import string

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "candy.db")
LEGACY_DB_PATH = os.path.join(BASE_DIR, "candy.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


# === DATABASE INITIALIZATION ===
async def init_db():
    """Handles init db."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if os.path.exists(LEGACY_DB_PATH):
        legacy_size = os.path.getsize(LEGACY_DB_PATH)
        db_exists = os.path.exists(DB_PATH)
        dest_size = os.path.getsize(DB_PATH) if db_exists else -1

        if not db_exists or legacy_size > dest_size:
            logging.info(
                f"[DB Migration] Migrating legacy database from {LEGACY_DB_PATH} "
                f"({legacy_size} bytes) to {DB_PATH} ({dest_size} bytes)..."
            )
            legacy_wal = LEGACY_DB_PATH + "-wal"
            legacy_shm = LEGACY_DB_PATH + "-shm"

            try:
                import sqlite3
                conn = sqlite3.connect(LEGACY_DB_PATH)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
            except Exception as e:
                logging.warning(f"[DB Migration] Legacy WAL checkpoint warning: {e}")

            shutil.copy2(LEGACY_DB_PATH, DB_PATH)
            if os.path.exists(legacy_wal) and os.path.getsize(legacy_wal) > 0:
                shutil.copy2(legacy_wal, DB_PATH + "-wal")
            if os.path.exists(legacy_shm) and os.path.getsize(legacy_shm) > 0:
                shutil.copy2(legacy_shm, DB_PATH + "-shm")

            backup_legacy = os.path.join(BASE_DIR, "candy.db.migrated_backup")
            if os.path.exists(backup_legacy):
                try:
                    os.remove(backup_legacy)
                except Exception:
                    pass
            try:
                os.rename(LEGACY_DB_PATH, backup_legacy)
                if os.path.exists(legacy_wal):
                    os.rename(legacy_wal, backup_legacy + "-wal")
                if os.path.exists(legacy_shm):
                    os.rename(legacy_shm, backup_legacy + "-shm")
                logging.info(f"[DB Migration] Successfully renamed legacy DB to {backup_legacy}")
            except Exception as e:
                logging.warning(f"[DB Migration] Could not rename legacy DB: {e}")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA journal_mode = WAL;')
        await db.execute('PRAGMA synchronous = NORMAL;')
        await db.execute('PRAGMA busy_timeout = 5000;')
        await db.execute('PRAGMA cache_size = -64000;')
        await db.execute('PRAGMA temp_store = MEMORY;')
        await db.execute('PRAGMA mmap_size = 268435456;')
        await db.execute('PRAGMA foreign_keys = ON;')

        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            await db.executescript(f.read())

        # Safe idempotent migrations for existing databases
        for migration_sql in [
            "ALTER TABLE users ADD COLUMN agent TEXT DEFAULT 'f'",
            "ALTER TABLE users ADD COLUMN expire INTEGER",
            "ALTER TABLE users ADD COLUMN maxbuyagent INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN pricediscount INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'",
            "ALTER TABLE users ADD COLUMN description TEXT",
            "ALTER TABLE users ADD COLUMN verify INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN token TEXT",
            "ALTER TABLE users ADD COLUMN agent_referrer_id INTEGER",
            "ALTER TABLE users ADD COLUMN agent_commission_balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN agent_settlement_active INTEGER DEFAULT 0",
            "ALTER TABLE licenses_cargo ADD COLUMN is_free_test INTEGER DEFAULT 0",
            "ALTER TABLE invoices ADD COLUMN license_note TEXT",
            "ALTER TABLE invoices ADD COLUMN panel_id INTEGER",
            "ALTER TABLE invoices ADD COLUMN renew_license_id INTEGER",
            "ALTER TABLE invoices ADD COLUMN last_error TEXT",
            "ALTER TABLE invoices ADD COLUMN payment_method TEXT",
            "ALTER TABLE invoices ADD COLUMN crypto_amount REAL",
            "ALTER TABLE invoices ADD COLUMN crypto_rate REAL",
            "ALTER TABLE invoices ADD COLUMN transfer_method TEXT",
            "ALTER TABLE xui_licenses ADD COLUMN alert_sent INTEGER DEFAULT 0",
            "ALTER TABLE xui_panels ADD COLUMN name TEXT",
            "ALTER TABLE xui_panels ADD COLUMN sub_link TEXT",
            "ALTER TABLE payment_reports ADD COLUMN gateway_request_id TEXT",
            "ALTER TABLE payment_reports ADD COLUMN crypto_amount REAL",
            "ALTER TABLE payment_reports ADD COLUMN transfer_method TEXT",
            "ALTER TABLE payment_reports ADD COLUMN receipt_time TEXT",
            "ALTER TABLE support_tickets ADD COLUMN user_message_id INTEGER",
            "ALTER TABLE support_tickets ADD COLUMN agent_message_id INTEGER",
            "ALTER TABLE support_tickets ADD COLUMN text_or_caption TEXT",
            "ALTER TABLE support_tickets ADD COLUMN subject TEXT",
            "ALTER TABLE departments ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        ]:
            try:
                await db.execute(migration_sql)
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remark TEXT,
                linkjoin TEXT,
                link TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs_api (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                header TEXT,
                data TEXT,
                time TEXT,
                ip TEXT,
                actions TEXT
            )
        """)

        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('operating_mode', 'NORMAL')")
        await db.execute("UPDATE settings SET value = 'NORMAL' WHERE key = 'operating_mode' AND value NOT IN ('NORMAL', 'SALES_PAUSED', 'MAINTENANCE')")

        async with db.execute("SELECT COUNT(*) FROM departments") as cursor:
            if (await cursor.fetchone())[0] == 0:
                await db.execute("INSERT INTO departments (name) VALUES ('پشتیبانی عمومی')")

        default_settings = [
            ('cashback_percent', '0'),
            ('free_test_enabled', '0'),
            ('free_test_gb', '1'),
            ('free_test_days', '1'),
            ('free_test_daily_limit', '50'),
            ('free_test_panel_id', '0'),
            ('referral_status', '0'),
            ('referral_reward_type', 'percent'),
            ('referral_reward_amount', '0'),
            ('feedback_enabled', '1'),
            ('acquisition_survey_enabled', '0'),
            ('frenzyex_callback_secret', ''),
            ('frenzyex_api_key', ''),
            ('frenzyex_base_url', 'https://frenzy.fastsnap.info'),
            ('plans_difference_text', ''),
            ('agent_default_text', 'به بخش نمایندگی خوش آمدید!\n\nبا اشتراک‌گذاری لینک اختصاصی خود پورسانت دریافت کنید.'),
            ('agent_commission_percent', '15'),
            ('agent_min_settlement_amount', '1000000'),
        ]
        for k, v in default_settings:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        await db.commit()


async def cleanup_miniapp_migration():
    """Migration to clean up old miniapp-specific settings from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key = 'webapp_theme'")
        await db.commit()


# === USER OPERATIONS ===
async def get_user(user_id: int | str):
    """Handles get user by ID or username."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if isinstance(user_id, str):
            clean = user_id.lstrip('@').strip()
            if clean.isdigit():
                async with db.execute('SELECT * FROM users WHERE id = ?', (int(clean),)) as cursor:
                    res = await cursor.fetchone()
                    if res:
                        return res
            async with db.execute('SELECT * FROM users WHERE username = ? OR username = ?', (clean, f"@{clean}")) as cursor:
                return await cursor.fetchone()
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


async def adjust_user_commission_balance(user_id: int | str, delta: int) -> tuple[int, int] | None:
    """
    Adjusts user's agent_commission_balance by delta (+ to add, - to deduct).
    Floors at 0 so commission balance cannot become negative.
    Returns (old_balance, new_balance) on success, or None if user not found.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        target = int(user_id) if str(user_id).isdigit() else user_id
        async with db.execute("SELECT id, agent_commission_balance FROM users WHERE id = ?", (target,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            old_balance = int(row['agent_commission_balance']) if row['agent_commission_balance'] is not None else 0
        new_balance = max(0, old_balance + delta)
        await db.execute("UPDATE users SET agent_commission_balance = ? WHERE id = ?", (new_balance, row['id']))
        await db.commit()
        return old_balance, new_balance


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


async def get_setting(key: str, default: str = '') -> str:
    """Handles get setting."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return (row[0] if row and row[0] is not None else default)


async def set_setting(key: str, value: str):
    """Handles set setting."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value)
        )
        await db.commit()


async def update_setting(key: str, value: str):
    """Updates or inserts a setting value (calls set_setting)."""
    await set_setting(key, value)


# === REPORTS DB OPERATIONS ===
async def set_report_setting(key: str, value: str):
    """Sets a report-related setting (group id or topic thread id)."""
    await set_setting(key, value)


async def get_report_setting(key: str):
    """Gets a report-related setting. Returns integer if exists, else None."""
    val = await get_setting(key, None)
    if val is None or val == '':
        return None
    try:
        return int(val)
    except ValueError:
        return None


async def delete_user_completely(user_id: int) -> dict:
    """
    Permanently removes a user and all their associated data from every table.
    Fixes BUG-08 by cleaning up support_messages, agency tables, and referral links.
    """
    summary = {}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = OFF')

        # 1. Delete support_messages belonging to tickets owned by this user
        try:
            cur_tmsg = await db.execute(
                "DELETE FROM support_messages WHERE ticket_id IN (SELECT id FROM support_tickets WHERE user_id = ?)",
                (user_id,)
            )
            summary["support_messages.ticket_id"] = cur_tmsg.rowcount
        except Exception:
            pass

        # 2. Delete direct rows across all user-related & agency tables
        deletions = [
            ("support_messages",          "sender_id"),
            ("support_tickets",           "user_id"),
            ("wallet_transactions",       "user_id"),
            ("cashback_rewards",          "user_id"),
            ("customer_feedback",         "user_id"),
            ("user_acquisition",          "user_id"),
            ("free_trial_usage",          "user_id"),
            ("referral_codes",            "user_id"),
            ("referral_commissions",      "referrer_id"),
            ("referral_commissions",      "referred_id"),
            ("agent_commissions",         "agent_id"),
            ("agent_commissions",         "buyer_id"),
            ("agent_activation_requests", "user_id"),
            ("agent_settlements",         "agent_id"),
            ("xui_licenses",              "user_id"),
            ("payment_reports",           "user_id"),
            ("invoices",                  "user_id"),
            ("users",                     "id"),
        ]
        for table, col in deletions:
            try:
                cursor = await db.execute(f"DELETE FROM {table} WHERE {col} = ?", (user_id,))
                key = f"{table}.{col}"
                summary[key] = summary.get(key, 0) + max(0, cursor.rowcount)
            except Exception:
                pass

        # 3. Nullify referrer references pointing to the deleted user
        try:
            await db.execute("UPDATE users SET referred_by = NULL WHERE referred_by = ?", (user_id,))
            await db.execute("UPDATE users SET agent_referrer_id = NULL WHERE agent_referrer_id = ?", (user_id,))
        except Exception:
            pass

        await db.execute('PRAGMA foreign_keys = ON')
        await db.commit()
    return summary


# === AUTH & API OPERATIONS (FIXED FOR BUG-02, BUG-03, BUG-06) ===
async def user_from_token(token: str):
    """Handles user from token."""
    if not token:
        return None
    return await fetch_one("SELECT * FROM users WHERE token = ?", (token,))


async def issue_token(user_id: int):
    """Handles issue token."""
    import secrets
    token = secrets.token_hex(20)
    await execute("UPDATE users SET token = ? WHERE id = ?", (token, user_id))
    return token


async def api_get_users_list(limit: int, offset: int, q: str):
    """Handles api get users list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = 'SELECT COUNT(*) FROM users WHERE CAST(id AS TEXT) LIKE ? OR username LIKE ?'
        async with db.execute(count_query, (search, search)) as cursor:
            total = (await cursor.fetchone())[0]

        data_query = 'SELECT * FROM users WHERE CAST(id AS TEXT) LIKE ? OR username LIKE ? LIMIT ? OFFSET ?'
        async with db.execute(data_query, (search, search, limit, offset)) as cursor:
            users = await cursor.fetchall()
            return users, total


async def api_get_user_details(user_id: int):
    """Handles api get user details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()


async def update_user_status(user_id: int, status: str, description: str = ""):
    """Updates both is_active and status/description columns safely (Fixes BUG-02 & BUG-06)."""
    is_active = 0 if status in ('banned', 'ban', 'blocked', 'inactive', '0') else 1
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET is_active = ?, status = ?, description = ? WHERE id = ?',
            (is_active, status, description, user_id)
        )
        await db.commit()


async def update_user_verify(user_id: int, verify: int):
    """Handles update user verify (Fixes BUG-06)."""
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
    allowed_fields = {
        'username', 'balance', 'score', 'namecustom', 'number', 'step',
        'message_count', 'affiliatescount', 'affiliates', 'joinchannel',
        'agent', 'expire', 'maxbuyagent', 'pricediscount', 'referred_by',
        'is_active', 'status', 'description', 'verify', 'agent_referrer_id',
        'agent_commission_balance', 'agent_settlement_active'
    }
    if field not in allowed_fields:
        raise ValueError(f"Invalid user field: {field}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'UPDATE users SET {field} = ? WHERE id = ?', (value, user_id))
        await db.commit()


async def api_transfer_account(old_id: int, new_id: int):
    """Transfers user account and all related records from old_id to new_id (Fixes BUG-03)."""
    async with aiosqlite.connect(DB_PATH, isolation_level=None) as db:
        await db.execute('PRAGMA foreign_keys = OFF')
        await db.execute('BEGIN EXCLUSIVE')
        try:
            await db.execute('DELETE FROM users WHERE id = ?', (new_id,))
            await db.execute('UPDATE users SET id = ? WHERE id = ?', (new_id, old_id))
            await db.execute('UPDATE invoices SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE payment_reports SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE xui_licenses SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE wallet_transactions SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE support_tickets SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE support_messages SET sender_id = ? WHERE sender_id = ?', (new_id, old_id))
            await db.execute('UPDATE referral_codes SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE referral_commissions SET referrer_id = ? WHERE referrer_id = ?', (new_id, old_id))
            await db.execute('UPDATE referral_commissions SET referred_id = ? WHERE referred_id = ?', (new_id, old_id))
            await db.execute('UPDATE agent_commissions SET agent_id = ? WHERE agent_id = ?', (new_id, old_id))
            await db.execute('UPDATE agent_commissions SET buyer_id = ? WHERE buyer_id = ?', (new_id, old_id))
            await db.execute('UPDATE agent_settlements SET agent_id = ? WHERE agent_id = ?', (new_id, old_id))
            await db.execute('UPDATE agent_activation_requests SET user_id = ? WHERE user_id = ?', (new_id, old_id))
            await db.execute('UPDATE users SET referred_by = ? WHERE referred_by = ?', (new_id, old_id))
            await db.execute('UPDATE users SET agent_referrer_id = ? WHERE agent_referrer_id = ?', (new_id, old_id))
            await db.execute('COMMIT')
        except Exception as e:
            await db.execute('ROLLBACK')
            raise e
        finally:
            await db.execute('PRAGMA foreign_keys = ON')


async def api_get_affiliate_users(affiliate_id: int):
    """Handles api get affiliate users."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT id as user_id FROM users WHERE affiliates = ? OR referred_by = ?',
            (str(affiliate_id), affiliate_id)
        ) as cursor:
            return await cursor.fetchall()


async def api_remove_affiliates(affiliate_id: int):
    """Handles api remove affiliates."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET affiliates = 0 WHERE affiliates = ?', (str(affiliate_id),))
        await db.execute('UPDATE users SET referred_by = NULL WHERE referred_by = ?', (affiliate_id,))
        await db.execute('UPDATE users SET affiliatescount = 0 WHERE id = ?', (affiliate_id,))
        await db.commit()


async def api_get_invoices_list(limit: int, offset: int, q: str):
    """Handles api get invoices list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = '''
            SELECT COUNT(*) FROM invoices i
            LEFT JOIN users u ON i.user_id = u.id
            WHERE i.id LIKE ? OR CAST(i.user_id AS TEXT) LIKE ? OR u.username LIKE ?
        '''
        async with db.execute(count_query, (search, search, search)) as cursor:
            total = (await cursor.fetchone())[0]

        data_query = '''
            SELECT i.*, u.username FROM invoices i
            LEFT JOIN users u ON i.user_id = u.id
            WHERE i.id LIKE ? OR CAST(i.user_id AS TEXT) LIKE ? OR u.username LIKE ?
            ORDER BY i.created_at DESC LIMIT ? OFFSET ?
        '''
        async with db.execute(data_query, (search, search, search, limit, offset)) as cursor:
            invoices = await cursor.fetchall()
            return invoices, total


async def api_get_services_list(limit: int, offset: int, q: str):
    """Handles api get services list using xui_licenses."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        count_query = """
            SELECT COUNT(*) FROM xui_licenses l
            LEFT JOIN users u ON l.user_id = u.id
            WHERE CAST(l.user_id AS TEXT) LIKE ? OR u.username LIKE ? OR l.sub_id LIKE ?
        """
        async with db.execute(count_query, (search, search, search)) as cursor:
            total = (await cursor.fetchone())[0]

        data_query = """
            SELECT l.*, u.username FROM xui_licenses l
            LEFT JOIN users u ON l.user_id = u.id
            WHERE CAST(l.user_id AS TEXT) LIKE ? OR u.username LIKE ? OR l.sub_id LIKE ?
            ORDER BY l.created_at DESC LIMIT ? OFFSET ?
        """
        async with db.execute(data_query, (search, search, search, limit, offset)) as cursor:
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
    """Handles fetch and consume cargo atomically."""
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


# === DISCOUNT DB OPERATIONS (FIXED FOR CURRENT SCHEMA) ===
async def api_get_discounts_list(limit: int, offset: int, q: str):
    """Handles api get discounts list."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM gift_codes WHERE code LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM gift_codes WHERE code LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total


async def api_get_discount(discount_id: str | int):
    """Handles api get discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gift_codes WHERE code = ? OR rowid = ?', (str(discount_id), discount_id)) as cursor:
            return await cursor.fetchone()


async def api_check_discount_exists(code: str):
    """Handles api check discount exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM gift_codes WHERE code = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0


async def api_add_discount(code: str, price: int, limit_use: int):
    """Handles api add discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO gift_codes (code, value, max_uses, used_count) VALUES (?, ?, ?, 0)',
            (code, price, limit_use)
        )
        await db.commit()


async def api_delete_discount(discount_id: str | int):
    """Handles api delete discount."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM gift_codes WHERE code = ? OR rowid = ?', (str(discount_id), discount_id))
        await db.commit()


async def api_get_discount_sell_lists(limit: int, offset: int, q: str):
    """Handles api get discount sell lists."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute('SELECT COUNT(*) FROM discount_codes WHERE code LIKE ?', (search,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute('SELECT * FROM discount_codes WHERE code LIKE ? LIMIT ? OFFSET ?', (search, limit, offset)) as cursor:
            return await cursor.fetchall(), total


async def api_get_discount_sell(discount_id: str | int):
    """Handles api get discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM discount_codes WHERE code = ? OR rowid = ?', (str(discount_id), discount_id)) as cursor:
            return await cursor.fetchone()


async def api_check_discount_sell_exists(code: str):
    """Handles api check discount sell exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM discount_codes WHERE code = ?', (code,)) as cursor:
            return (await cursor.fetchone())[0] > 0


async def api_add_discount_sell(code: str, percent: int, limit_use: int):
    """Handles api add discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO discount_codes (code, type, value, max_uses, used_count) VALUES (?, 'percent', ?, ?, 0)",
            (code, percent, limit_use)
        )
        await db.commit()


async def api_delete_discount_sell(discount_id: str | int):
    """Handles api delete discount sell."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM discount_codes WHERE code = ? OR rowid = ?', (str(discount_id), discount_id))
        await db.commit()


# === PAYMENT DB OPERATIONS (FIXED FOR BUG-06) ===
async def api_get_payments_list(limit: int, offset: int, q: str):
    """Handles api get payments list using payment_reports table."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{q}%"
        async with db.execute(
            'SELECT COUNT(*) FROM payment_reports WHERE CAST(user_id AS TEXT) LIKE ? OR invoice_id LIKE ?',
            (search, search)
        ) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute(
            '''SELECT id, invoice_id AS id_order, user_id, user_id AS id_user,
                      created_at AS time, amount AS price, status AS payment_status,
                      payment_method AS Payment_Method
               FROM payment_reports
               WHERE CAST(user_id AS TEXT) LIKE ? OR invoice_id LIKE ?
               ORDER BY created_at DESC LIMIT ? OFFSET ?''',
            (search, search, limit, offset)
        ) as cursor:
            return await cursor.fetchall(), total


async def api_get_payment(id_order: str | int):
    """Handles api get payment using payment_reports table."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM payment_reports WHERE invoice_id = ? OR id = ?',
            (str(id_order), id_order)
        ) as cursor:
            return await cursor.fetchone()


# === SETTING DB OPERATIONS ===
async def api_update_setting(key: str, value: str):
    """Handles api update setting."""
    await set_setting(key, value)


async def api_get_settings():
    """Handles api get settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT key, value FROM settings') as cursor:
            rows = await cursor.fetchall()
            return {row['key']: row['value'] for row in rows}


async def api_update_settings_batch(updates: dict):
    """Handles api update settings batch."""
    for k, v in updates.items():
        await set_setting(k, str(v))


# === LOGGING OPERATIONS (FIXED FOR BUG-06) ===
async def api_insert_log(header: dict, data: dict, ip: str, actions: str):
    """Handles api insert log."""
    import json
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        header_json = json.dumps(header, ensure_ascii=False)
        data_json = json.dumps(data, ensure_ascii=False)
        time_str = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        await db.execute(
            'INSERT INTO logs_api (header, data, time, ip, actions) VALUES (?, ?, ?, ?, ?)',
            (header_json, data_json, time_str, ip, actions)
        )
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
        async with db.execute("SELECT COUNT(*) FROM users WHERE agent != 'f'") as cursor:
            try:
                return (await cursor.fetchone())[0]
            except Exception:
                return 0


async def get_test_cargo_count():
    """Handles get test cargo count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1') as cursor:
            return (await cursor.fetchone())[0]


async def get_bot_stats(timeframe_clause: str = "", timeframe_params: tuple = ()):
    """Handles get bot stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT COUNT(*) FROM users {timeframe_clause}", timeframe_params) as cursor:
            users_count = (await cursor.fetchone())[0]

        order_timeframe = timeframe_clause.replace("WHERE", "AND") if timeframe_clause else ""
        async with db.execute(f"SELECT COUNT(*) FROM invoices WHERE status != 'pending' {order_timeframe}", timeframe_params) as cursor:
            orders_count = (await cursor.fetchone())[0]

        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status != 'pending' {order_timeframe}", timeframe_params) as cursor:
            sales_sum = (await cursor.fetchone())[0] or 0

        async with db.execute(f"SELECT COUNT(*) FROM invoices WHERE base_price = 0 {order_timeframe}", timeframe_params) as cursor:
            test_count = (await cursor.fetchone())[0]

        return {
            "users": users_count,
            "orders": orders_count,
            "sales": sales_sum,
            "tests": test_count
        }


async def get_advanced_bot_stats(timeframe_clause: str = "", timeframe_params: tuple = ()):
    """Handles get advanced bot stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        order_timeframe = timeframe_clause.replace("WHERE ", "AND ") if timeframe_clause else ""

        async with db.execute(f"SELECT COUNT(*) FROM users {timeframe_clause}", timeframe_params) as cursor:
            total_users = (await cursor.fetchone())[0]

        async with db.execute(f"SELECT COUNT(DISTINCT user_id) FROM invoices WHERE status IN ('paid', 'approved') {order_timeframe}", timeframe_params) as cursor:
            users_with_purchase = (await cursor.fetchone())[0] or 0

        async with db.execute("SELECT COUNT(*) FROM licenses_cargo WHERE is_free_test=1") as cursor:
            test_accounts_cargo = (await cursor.fetchone())[0]

        async with db.execute(f"SELECT COUNT(*) FROM payment_reports WHERE payment_method = 'free_test' {order_timeframe}", timeframe_params) as cursor:
            test_accounts_report = (await cursor.fetchone())[0] or 0

        test_accounts = test_accounts_report if timeframe_clause else (test_accounts_cargo + test_accounts_report)

        async with db.execute("SELECT SUM(balance) FROM users") as cursor:
            total_balance = (await cursor.fetchone())[0] or 0

        async with db.execute("SELECT AVG(rating), COUNT(rating) FROM customer_feedback") as cursor:
            row = await cursor.fetchone()
            avg_poll_rating = round(row[0] or 0.0, 1)
            poll_count = row[1] or 0

        async with db.execute(f"SELECT COUNT(id) FROM invoices WHERE status IN ('paid', 'approved') {order_timeframe}", timeframe_params) as cursor:
            total_sales_count = (await cursor.fetchone())[0] or 0

        async with db.execute("SELECT COUNT(id) FROM xui_licenses") as cursor:
            active_services_sales_count = (await cursor.fetchone())[0] or 0

        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') {order_timeframe}", timeframe_params) as cursor:
            total_sales_amount = (await cursor.fetchone())[0] or 0

        async with db.execute(f"""
            SELECT SUM(final_amount) FROM invoices 
            WHERE status IN ('paid', 'approved') 
              AND (
                  LOWER(COALESCE(payment_method, '')) LIKE '%frenzy%' 
                  OR id IN (
                      SELECT invoice_id FROM payment_reports 
                      WHERE LOWER(COALESCE(payment_method, '')) LIKE '%frenzy%'
                         OR (gateway_request_id IS NOT NULL AND gateway_request_id != '')
                  )
              )
              {order_timeframe}
        """, timeframe_params) as cursor:
            frenzyex_sales_amount = (await cursor.fetchone())[0] or 0

        async with db.execute(f"SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND renew_license_id IS NOT NULL {order_timeframe}", timeframe_params) as cursor:
            total_renewal_amount = (await cursor.fetchone())[0] or 0

        async with db.execute(f"SELECT COUNT(id) FROM invoices WHERE status IN ('paid', 'approved') AND renew_license_id IS NOT NULL {order_timeframe}", timeframe_params) as cursor:
            renewals_count = (await cursor.fetchone())[0] or 0

        conversion_rate = (users_with_purchase / total_users * 100) if total_users > 0 else 0
        avg_purchase = (total_sales_amount / users_with_purchase) if users_with_purchase > 0 else 0

        async with db.execute("SELECT SUM(final_amount) FROM invoices WHERE status IN ('paid', 'approved') AND created_at >= date('now', '-30 days')") as cursor:
            estimated_monthly_revenue = (await cursor.fetchone())[0] or 0

        active_services_sales_amount = estimated_monthly_revenue
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
            "frenzyex_sales_amount": frenzyex_sales_amount,
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


async def get_orders_in_timeframe(start_str: str, end_str: str):
    """Fetch invoices/orders in a specific datetime range for reporting/exporting."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT i.id, i.user_id, u.username, i.plan_id, p.name AS plan_name,
                   i.days, i.gb, i.final_amount, i.status, i.renew_license_id, i.created_at
            FROM invoices i
            LEFT JOIN users u ON i.user_id = u.id
            LEFT JOIN plans p ON i.plan_id = p.id
            WHERE i.status IN ('paid', 'approved') AND i.created_at BETWEEN ? AND ?
            ORDER BY i.created_at DESC
        """
        async with db.execute(sql, (start_str, end_str)) as cursor:
            return await cursor.fetchall()


# === DISCOUNTS & GIFTS ===
async def get_discount_code(code: str, user_id: int = None):
    """Handles get discount code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM discount_codes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"error": "کد تخفیف یافت نشد."}
            row = dict(row)

            if row['expiration_date']:
                from datetime import datetime
                if datetime.now().strftime('%Y-%m-%d %H:%M:%S') > row['expiration_date']:
                    return {"error": "مهلت استفاده از این کد تخفیف به پایان رسیده است."}

            if row['max_uses'] and row['used_count'] >= row['max_uses']:
                return {"error": "ظرفیت استفاده از این کد تخفیف تکمیل شده است."}

            if user_id is not None and row['user_id_restriction'] and str(row['user_id_restriction']) != '0' and str(row['user_id_restriction']) != str(user_id):
                return {"error": "این کد تخفیف متعلق به حساب کاربری شما نیست."}

            return row


async def get_gift_code(code: str, user_id: int = None):
    """Handles get gift code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM gift_codes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"error": "کد هدیه یافت نشد."}
            row = dict(row)

            if row['expiration_date']:
                from datetime import datetime
                if datetime.now().strftime('%Y-%m-%d %H:%M:%S') > row['expiration_date']:
                    return {"error": "مهلت استفاده از این کد هدیه به پایان رسیده است."}

            if row['max_uses'] and row['used_count'] >= row['max_uses']:
                return {"error": "ظرفیت استفاده از این کد هدیه تکمیل شده است."}

            if user_id is not None and row['user_id_restriction'] and str(row['user_id_restriction']) != '0' and str(row['user_id_restriction']) != str(user_id):
                return {"error": "این کد هدیه متعلق به حساب کاربری شما نیست."}

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
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_xui_panel(panel_id: int):
    """Return a single XUI panel by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM xui_panels WHERE id = ?', (panel_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_xui_panel(panel_id: int):
    """Delete a panel and its bindings (CASCADE)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM xui_panels WHERE id = ?', (panel_id,))
        await db.commit()


# ============================================================
# === PLAN - PANEL BINDING ===
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
    """Return all licenses for a user, newest first, joined with panel URL and invoice metadata."""
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


# ============================================================
# === OPERATING MODE ===
# ============================================================
async def get_operating_mode() -> str:
    """Return current operating mode: NORMAL | SALES_PAUSED | MAINTENANCE"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'operating_mode'") as cursor:
            row = await cursor.fetchone()
            val = (row[0] if row else 'NORMAL') or 'NORMAL'
            if val not in ('NORMAL', 'SALES_PAUSED', 'MAINTENANCE'):
                await db.execute("UPDATE settings SET value = 'NORMAL' WHERE key = 'operating_mode'")
                await db.commit()
                return 'NORMAL'
            return val


async def set_operating_mode(mode: str):
    """Set operating mode. mode must be NORMAL, SALES_PAUSED, or MAINTENANCE."""
    if mode not in ('NORMAL', 'SALES_PAUSED', 'MAINTENANCE'):
        mode = 'NORMAL'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('operating_mode', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (mode,)
        )
        await db.commit()


# ============================================================
# === WALLET LEDGER ===
# ============================================================
async def wallet_adjust(user_id: int, amount: int, tx_type: str, description: str,
                        related_invoice_id: str = None, unique_key: str = None) -> tuple:
    """Atomically adjust a user's wallet balance and record a ledger entry."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if unique_key:
            async with db.execute("SELECT id FROM wallet_transactions WHERE unique_key = ?", (unique_key,)) as cur:
                if await cur.fetchone():
                    async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as c2:
                        row = await c2.fetchone()
                        return (True, int(row['balance']) if row else 0)
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return (False, 0)
        current = int(row['balance'])
        new_balance = current + amount
        if new_balance < 0:
            return (False, current)
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
        await db.execute(
            """INSERT INTO wallet_transactions
               (user_id, amount, balance_after, type, description, related_invoice_id, unique_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, amount, new_balance, tx_type, description, related_invoice_id, unique_key, int(_time.time()))
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
    """Return cashback percentage from settings (0-100)."""
    val = await get_setting('cashback_percent', '0')
    try:
        return float(val)
    except Exception:
        return 0.0


async def credit_cashback(invoice_id: str, user_id: int, paid_amount: int) -> dict | None:
    """Credit cashback to the buyer's wallet after an approved invoice."""
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
def _gen_ref_code(user_id: int) -> str:
    """Handles _gen_ref_code."""
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
    """Set referred_by on a user atomically - only if not already set and not self-referral."""
    if user_id == referrer_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row['referred_by'] is not None:
            return False
        await db.execute(
            "UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL",
            (referrer_id, user_id)
        )
        await db.commit()
        return True


async def get_referral_stats(user_id: int) -> dict:
    """Return referral stats for the user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) AS cnt FROM users WHERE referred_by = ?", (user_id,)) as cur:
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
    """Credit the referrer's wallet for a purchase."""
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
        async with db.execute("SELECT user_id, final_amount FROM invoices WHERE id = ?", (invoice_id,)) as cur:
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

        try:
            await db.execute(
                """INSERT INTO referral_commissions
                   (referrer_id, referred_id, purchase_invoice_id, commission_amount)
                   VALUES (?, ?, ?, ?)""",
                (referrer_id, buyer_id, invoice_id, commission)
            )
            await db.commit()
        except Exception:
            return None

    ok, new_balance = await wallet_adjust(
        referrer_id, commission, 'COMMISSION',
        f"پورسانت معرفی کاربر {buyer_id} (فاکتور {invoice_id})",
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
    """Insert a row in user_acquisition (asked_at = now) if not already there."""
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
            return False


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
# === INVOICE STATUS HELPERS (FIXED FOR BUG-01) ===
# ============================================================
async def mark_invoice_processing(invoice_id: str):
    """Mark invoice as processing (supports transitioning from both 'pending' and 'paid')."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE invoices SET status = 'processing' WHERE id = ? AND status IN ('pending', 'paid')",
            (invoice_id,)
        )
        await db.commit()


async def mark_invoice_approved(invoice_id: str):
    """Mark invoice as approved (supports transitioning from 'processing', 'issue', or 'paid')."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE invoices SET status = 'approved' WHERE id = ? AND status IN ('processing', 'issue', 'paid')",
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
    """
    Return all product invoices stuck in 'processing' or 'paid' without an issued license
    (for startup recovery - Fixes BUG-01).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM invoices
               WHERE (status = 'processing' OR (status = 'paid' AND COALESCE(plan_id, 0) != 0))
                 AND id NOT IN (SELECT invoice_id FROM xui_licenses)
               ORDER BY created_at ASC LIMIT 50"""
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


async def disable_user(user_id: int):
    """Deactivates a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_active = 0, status = 'banned' WHERE id = ?", (user_id,))
        await db.commit()


async def enable_user(user_id: int):
    """Re-activates a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_active = 1, status = 'active' WHERE id = ?", (user_id,))
        await db.commit()


async def get_all_users_for_broadcast() -> list[int]:
    """Gets list of all active user IDs for broadcasting."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE is_active = 1") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_users_with_purchase() -> list[int]:
    """Gets list of active user IDs who have completed purchases (includes 'approved')."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT DISTINCT user_id FROM invoices 
            WHERE status IN ('paid', 'approved', 'completed')
              AND user_id IN (SELECT id FROM users WHERE is_active = 1)
        """) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_users_without_purchase() -> list[int]:
    """Gets list of active user IDs who have not made any purchases (includes 'approved')."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id FROM users 
            WHERE is_active = 1
              AND id NOT IN (
                  SELECT DISTINCT user_id FROM invoices WHERE status IN ('paid', 'approved', 'completed')
              )
        """) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_inactive_users_for_broadcast(days: int) -> list[int]:
    """Gets active users who have not had any invoice or activity within the last `days` days."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id FROM users
            WHERE is_active = 1
              AND created_at <= datetime('now', ?)
              AND id NOT IN (
                  SELECT DISTINCT user_id FROM invoices
                  WHERE created_at >= datetime('now', ?)
              )
        """, (f'-{days} days', f'-{days} days')) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_all_channels() -> list[dict]:
    """Gets all registered channels."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, remark, linkjoin, link FROM channels ORDER BY id ASC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


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
            WHERE i.status IN ('approved', 'paid') AND i.base_price > 0
        """) as cur:
            return await cur.fetchall()


async def get_users_with_active_licenses():
    """Returns users who currently have at least one active, non-trial subscription."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT 
                u.id, 
                u.username, 
                u.balance,
                u.created_at,
                COUNT(DISTINCT xl.id) AS sub_count
            FROM users u
            JOIN invoices i ON u.id = i.user_id
            JOIN xui_licenses xl ON i.id = xl.invoice_id
            WHERE i.status IN ('approved', 'paid')
              AND i.base_price > 0
              AND (i.plan_id IS NULL OR i.plan_id > 0)
              AND (xl.license_note IS NULL OR LOWER(xl.license_note) NOT LIKE '%trial%')
              AND (i.license_note IS NULL OR LOWER(i.license_note) NOT LIKE '%trial%')
              AND (i.payment_method IS NULL OR (LOWER(i.payment_method) NOT LIKE '%test%' AND LOWER(i.payment_method) NOT LIKE '%trial%'))
              AND (
                  i.days IS NULL 
                  OR i.days <= 0 
                  OR datetime(COALESCE(i.created_at, xl.created_at), '+' || i.days || ' days') >= datetime('now')
              )
            GROUP BY u.id, u.username, u.balance, u.created_at
            ORDER BY u.created_at DESC
        """) as cur:
            return await cur.fetchall()


async def add_trial_users_balance(amount: int) -> list:
    """Adds balance to users who received a free trial but didn't buy anything."""
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
                SELECT user_id FROM invoices WHERE base_price > 0 AND status IN ('approved', 'paid')
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
                    SELECT user_id FROM invoices WHERE base_price > 0 AND status IN ('approved', 'paid')
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
            await db.execute("INSERT INTO departments (name) VALUES (?)", (name,))
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
        await db.execute("UPDATE departments SET support_user_id = ? WHERE id = ?", (agent_id, dept_id))
        await db.commit()


set_department_agent = set_department_support_user


async def toggle_department_active(dept_id: int, is_active: bool):
    """Activates or deactivates a department."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE departments SET is_active = ? WHERE id = ?", (1 if is_active else 0, dept_id))
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
        await db.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        await db.commit()


async def add_support_message(ticket_id: int, sender_id: int, sender_role: str, message_id: int = None, text: str = None):
    """Appends a message to a support ticket."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO support_messages (ticket_id, sender_id, sender_role, message_id, text) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, sender_id, sender_role, message_id, text)
        )
        await db.commit()


# === EXPIRED DATA CLEANUP (TICKETS, LICENSES, INVOICES) ===
async def cleanup_expired_data(retention_days: int = 14) -> dict:
    """Cleans up expired data from the bot's database for storage and performance optimization."""
    import time
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
                cur_msg = await db.execute(f"DELETE FROM support_messages WHERE ticket_id IN ({placeholders})", ticket_ids)
                deleted_ticket_messages = max(0, cur_msg.rowcount)

                cur_tkt = await db.execute(f"DELETE FROM support_tickets WHERE id IN ({placeholders})", ticket_ids)
                deleted_tickets = max(0, cur_tkt.rowcount)
        except Exception as e:
            logger.error(f"Error cleaning support tickets: {e}")

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

            async with db.execute(f"""
                SELECT l.id FROM xui_licenses l
                JOIN invoices i ON l.invoice_id = i.id
                WHERE i.days > 0 
                  AND datetime(l.created_at, '+' || (i.days + {retention_days}) || ' days') < datetime('now')
            """) as cur:
                date_expired = await cur.fetchall()
                for r in date_expired:
                    expired_license_ids.add(r[0])

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
                cur_lic = await db.execute(f"DELETE FROM xui_licenses WHERE id IN ({placeholders})", lic_id_list)
                deleted_licenses = max(0, cur_lic.rowcount)
        except Exception as e:
            logger.error(f"Error cleaning expired licenses: {e}")

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
                await db.execute(f"DELETE FROM xui_licenses WHERE invoice_id IN ({placeholders})", expired_inv_ids)

                cur_pr = await db.execute(f"DELETE FROM payment_reports WHERE invoice_id IN ({placeholders})", expired_inv_ids)
                deleted_payment_reports += max(0, cur_pr.rowcount)

                cur_inv = await db.execute(f"DELETE FROM invoices WHERE id IN ({placeholders})", expired_inv_ids)
                deleted_invoices = max(0, cur_inv.rowcount)

            cur_pr_extra = await db.execute(f"""
                DELETE FROM payment_reports 
                WHERE status = 'expire' 
                   OR (status = 'Unpaid' AND created_at < datetime('now', '-{retention_days} days'))
            """)
            deleted_payment_reports += max(0, cur_pr_extra.rowcount)
        except Exception as e:
            logger.error(f"Error cleaning expired invoices: {e}")

        await db.commit()

        try:
            await db.execute("PRAGMA optimize;")
        except Exception as e:
            logger.error(f"Error executing PRAGMA optimize: {e}")

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
# COMMISSION AGENT / AGENCY
# ============================================================
async def set_agent_referrer(user_id: int, agent_id: int) -> bool:
    """Set agent_referrer_id on a user atomically - only if not already set and not self-referral."""
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
    """Fetch comprehensive agent statistics."""
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
    """Credit the agent's commission balance for a purchase made by their sub-user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, final_amount, status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
            inv = await cur.fetchone()
        if not inv or inv['status'] not in ('paid', 'approved', 'processing'):
            return None
        buyer_id = inv['user_id']
        paid_amount = int(inv['final_amount'])
        if paid_amount <= 0:
            return None

        async with db.execute("SELECT agent_referrer_id FROM users WHERE id = ?", (buyer_id,)) as cur:
            u = await cur.fetchone()
        if not u or not u['agent_referrer_id']:
            return None
        agent_id = int(u['agent_referrer_id'])
        if agent_id == buyer_id:
            return None

        async with db.execute("SELECT id FROM agent_commissions WHERE invoice_id = ?", (invoice_id,)) as cur:
            if await cur.fetchone():
                return None

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
        await db.execute("UPDATE users SET agent_settlement_active = 1 WHERE id = ?", (user_id,))
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
    """Atomically deducts amount_irt from agent_commission_balance and creates a settlement record."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE users 
            SET agent_commission_balance = agent_commission_balance - ? 
            WHERE id = ? AND agent_commission_balance >= ?
        """, (amount_irt, agent_id, amount_irt))
        if cursor.rowcount == 0:
            return None

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
    """Fetch unsettled (pending or waiting) settlements, sorted by amount_irt descending."""
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
    """Mark a settlement as settled with tx_hash and timestamp."""
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
    """Fetch all settled records from day 1 for reporting and CSV exports."""
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


# ============================================================
# === ADMIN DASHBOARD LIVE COUNTERS ===
# ============================================================
async def get_admin_dashboard_counts() -> dict:
    """Returns pending-action counters for the admin live dashboard."""
    import time as _time
    today_ts = int(_time.mktime(_time.strptime(_time.strftime('%Y-%m-%d'), '%Y-%m-%d')))
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("SELECT COUNT(*) FROM payment_reports WHERE status IN ('pending', 'pending_receipt')") as cur:
                pending_receipts = (await cur.fetchone())[0]
        except Exception:
            pending_receipts = 0

        try:
            async with db.execute("SELECT COUNT(*) FROM agent_settlements WHERE status IN ('pending','waiting')") as cur:
                pending_settlements = (await cur.fetchone())[0]
        except Exception:
            pending_settlements = 0

        try:
            async with db.execute("SELECT COUNT(*) FROM agent_activation_requests WHERE status = 'pending'") as cur:
                pending_activations = (await cur.fetchone())[0]
        except Exception:
            pending_activations = 0

        try:
            async with db.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'unanswered')") as cur:
                open_tickets = (await cur.fetchone())[0]
        except Exception:
            open_tickets = 0

        try:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(final_amount),0) FROM invoices "
                "WHERE status IN ('paid','approved') AND created_at >= datetime(?,'unixepoch')",
                (today_ts,)
            ) as cur:
                row = await cur.fetchone()
                today_count = row[0] or 0
                today_amount = row[1] or 0
        except Exception:
            today_count = today_amount = 0

        try:
            async with db.execute("SELECT value FROM settings WHERE key='operating_mode'") as cur:
                row = await cur.fetchone()
                op_mode = row[0] if row else 'NORMAL'
        except Exception:
            op_mode = 'NORMAL'

    return {
        'pending_receipts': pending_receipts,
        'pending_settlements': pending_settlements,
        'pending_activations': pending_activations,
        'open_tickets': open_tickets,
        'today_count': today_count,
        'today_amount': today_amount,
        'op_mode': op_mode,
    }


async def get_active_payment_gateways() -> list:
    """Returns list of (label, callback_data) for active payment gateways."""
    gateway_map = [
        ('gram_status',     'پرداخت با گرام (TON)',       'pay_gram'),
        ('usdt_status',     'پرداخت با تتر (BSC)',        'pay_usdt'),
        ('frenzyex_status', 'درگاه آنلاین (FrenzyEx)',    'pay_frenzyex'),
    ]
    result = []
    async with aiosqlite.connect(DB_PATH) as db:
        for key, name, cb_data in gateway_map:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
            if row and row[0] == '1':
                result.append((name, cb_data))
    return result


async def create_free_invoice(
    invoice_id: str,
    user_id: int,
    plan_id: int,
    days: int,
    gb: int,
    base_price: int,
    wallet_deduction: int,
    discount_code,
    discount_amount: int,
    gift_code,
    gift_amount: int,
    license_note: str,
    renew_license_id,
) -> bool:
    """Atomically validates wallet balance and inserts a zero-cost invoice."""
    async with aiosqlite.connect(DB_PATH) as db:
        if wallet_deduction > 0:
            async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
            if not row or row[0] < wallet_deduction:
                return False
        await db.execute(
            """
            INSERT INTO invoices
              (id, user_id, plan_id, days, gb, base_price, wallet_deduction,
               discount_code, discount_deduction, gift_code, gift_deduction,
               final_amount, license_note, status, renew_license_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'pending', ?)
            """,
            (
                invoice_id, user_id, plan_id, days, gb,
                base_price, wallet_deduction,
                discount_code, discount_amount,
                gift_code, gift_amount,
                license_note, renew_license_id,
            ),
        )
        await db.commit()
    return True


async def get_db_admin_ids() -> list[int]:
    """Returns list of admin IDs stored in the admins table."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM admins") as cur:
            rows = await cur.fetchall()
            return [int(r[0]) for r in rows if r[0] is not None and str(r[0]).isdigit()]