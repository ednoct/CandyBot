PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    namecustom TEXT,
    number TEXT,
    step TEXT,
    message_count INTEGER DEFAULT 0,
    affiliatescount INTEGER DEFAULT 0,
    affiliates TEXT,
    joinchannel INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY,
    username TEXT,
    password TEXT,
    role TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    admin_description TEXT,
    price_per_day INTEGER DEFAULT 0,
    price_per_gb INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS time_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER,
    days INTEGER NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS traffic_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER,
    gb INTEGER NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS licenses_cargo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER,
    time_package_id INTEGER,
    traffic_package_id INTEGER,
    license_key TEXT NOT NULL,
    is_free_test INTEGER DEFAULT 0,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    FOREIGN KEY(time_package_id) REFERENCES time_packages(id) ON DELETE CASCADE,
    FOREIGN KEY(traffic_package_id) REFERENCES traffic_packages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS discount_codes (
    code TEXT PRIMARY KEY,
    type TEXT, -- 'fixed' or 'percent'
    value INTEGER,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    expiration_date TIMESTAMP,
    user_id_restriction INTEGER
);

CREATE TABLE IF NOT EXISTS gift_codes (
    code TEXT PRIMARY KEY,
    value INTEGER,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    expiration_date TIMESTAMP,
    user_id_restriction INTEGER
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    plan_id INTEGER,
    days INTEGER,
    gb INTEGER,
    base_price INTEGER,
    wallet_deduction INTEGER,
    discount_code TEXT,
    discount_deduction INTEGER,
    gift_code TEXT,
    gift_deduction INTEGER,
    final_amount INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payment_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    invoice_id TEXT,
    amount INTEGER,
    payment_method TEXT,
    status TEXT,
    message_id INTEGER,
    crypto_hash TEXT,
    crypto_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remark TEXT,
    linkjoin TEXT,
    link TEXT
);

-- Indices mapped from legacy migrate_indexes.php
CREATE INDEX IF NOT EXISTS idx_users_affiliates ON users(affiliates);
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_payment_reports_user_id ON payment_reports(user_id);

