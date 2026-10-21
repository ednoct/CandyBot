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
    agent TEXT DEFAULT 'f',
    expire INTEGER,
    maxbuyagent INTEGER DEFAULT 0,
    pricediscount INTEGER DEFAULT 0,
    referred_by INTEGER,
    is_active INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    description TEXT,
    verify INTEGER DEFAULT 0,
    token TEXT,
    agent_referrer_id INTEGER,
    agent_commission_balance INTEGER DEFAULT 0,
    agent_settlement_active INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    support_user_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    department_id INTEGER,
    user_message_id INTEGER,
    agent_message_id INTEGER,
    subject TEXT,
    status TEXT DEFAULT 'unanswered',
    text_or_caption TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(department_id) REFERENCES departments(id)
);

CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_role TEXT NOT NULL,
    message_id INTEGER,
    text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE
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
    panel_id INTEGER,
    days INTEGER,
    gb INTEGER,
    base_price INTEGER,
    wallet_deduction INTEGER,
    discount_code TEXT,
    discount_deduction INTEGER,
    gift_code TEXT,
    gift_deduction INTEGER,
    final_amount INTEGER,
    license_note TEXT,
    status TEXT DEFAULT 'pending',
    renew_license_id INTEGER,
    renew_mode TEXT,
    last_error TEXT,
    payment_method TEXT,
    crypto_amount REAL,
    crypto_rate REAL,
    transfer_method TEXT,
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
    gateway_request_id TEXT,
    crypto_amount REAL,
    transfer_method TEXT,
    receipt_time TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remark TEXT,
    linkjoin TEXT,
    link TEXT
);

CREATE TABLE IF NOT EXISTS logs_api (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    header TEXT,
    data TEXT,
    time TEXT,
    ip TEXT,
    actions TEXT
);

-- Indices mapped from legacy migrate_indexes.php
CREATE INDEX IF NOT EXISTS idx_users_affiliates ON users(affiliates);
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_payment_reports_user_id ON payment_reports(user_id);

-- ============================================================
-- XUI PANEL INTEGRATION TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS xui_panels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    label TEXT,
    url TEXT NOT NULL,
    sub_link TEXT,
    bearer_token TEXT NOT NULL,
    inbound_ids TEXT NOT NULL,
    ip_limit INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_panel (
    plan_id INTEGER PRIMARY KEY,
    panel_id INTEGER NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    FOREIGN KEY(panel_id) REFERENCES xui_panels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS xui_licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    panel_id INTEGER NOT NULL,
    sub_id TEXT NOT NULL,
    license_note TEXT,
    alert_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(panel_id) REFERENCES xui_panels(id)
);

CREATE INDEX IF NOT EXISTS idx_xui_licenses_user_id ON xui_licenses(user_id);

-- ============================================================
-- REFERRAL / AFFILIATE SYSTEM
-- ============================================================

CREATE TABLE IF NOT EXISTS referral_codes (
    user_id INTEGER PRIMARY KEY,
    code    TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS referral_commissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id         INTEGER NOT NULL,
    referred_id         INTEGER NOT NULL,
    purchase_invoice_id TEXT NOT NULL UNIQUE,
    commission_amount   INTEGER NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ref_commissions_referrer ON referral_commissions(referrer_id);

-- ============================================================
-- WALLET LEDGER
-- ============================================================

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    amount          INTEGER NOT NULL,
    balance_after   INTEGER NOT NULL,
    type            TEXT NOT NULL,
    description     TEXT,
    related_invoice_id TEXT,
    unique_key      TEXT UNIQUE,
    created_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wallet_tx_user ON wallet_transactions(user_id);

-- ============================================================
-- CASHBACK REWARDS
-- ============================================================

CREATE TABLE IF NOT EXISTS cashback_rewards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  TEXT NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    amount      INTEGER NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- CUSTOMER FEEDBACK (1-5 stars)
-- ============================================================

CREATE TABLE IF NOT EXISTS customer_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    invoice_id  TEXT,
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_user ON customer_feedback(user_id);

-- ============================================================
-- ACQUISITION SURVEY
-- ============================================================

CREATE TABLE IF NOT EXISTS user_acquisition (
    user_id     INTEGER PRIMARY KEY,
    source      TEXT,
    detail      TEXT,
    asked_at    INTEGER,
    answered_at INTEGER
);

-- ============================================================
-- FREE TRIAL USAGE
-- ============================================================

CREATE TABLE IF NOT EXISTS free_trial_usage (
    user_id     INTEGER PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- COMMISSION AGENT / AGENCY SYSTEM
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_commissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id            INTEGER NOT NULL,
    buyer_id            INTEGER NOT NULL,
    invoice_id          TEXT NOT NULL UNIQUE,
    order_amount        INTEGER NOT NULL,
    commission_percent  REAL NOT NULL,
    commission_amount   INTEGER NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_commissions_agent ON agent_commissions(agent_id);

CREATE TABLE IF NOT EXISTS agent_activation_requests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    commission_balance  INTEGER NOT NULL,
    sub_users_count     INTEGER NOT NULL,
    status              TEXT DEFAULT 'pending',
    reject_reason       TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_act_user ON agent_activation_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_act_status ON agent_activation_requests(status);

CREATE TABLE IF NOT EXISTS agent_settlements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id            INTEGER NOT NULL,
    amount_irt          INTEGER NOT NULL,
    amount_gram         REAL NOT NULL,
    gram_price          INTEGER NOT NULL,
    wallet_address      TEXT NOT NULL,
    status              TEXT DEFAULT 'pending',
    tx_hash             TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at          TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_settlements_agent ON agent_settlements(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_settlements_status ON agent_settlements(status);