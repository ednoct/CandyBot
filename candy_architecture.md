# Candy Architecture Map

```text
/CandyBot/
├── bot/
│   ├── config.py
│   ├── main.py
│   ├── states.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── admin_finance.py
│   │   ├── admin_plans.py
│   │   ├── admin_reports.py
│   │   ├── admin_settings.py
│   │   ├── admin_shop.py
│   │   ├── admin_users.py
│   │   ├── admin_xui.py
│   │   ├── checkout.py
│   │   ├── payment.py
│   │   ├── support.py
│   │   └── user.py
│   └── services/
│       ├── __init__.py
│       ├── broadcast.py
│       └── xui_client.py
├── cron/
│   └── tasks.py
├── database/
│   ├── db_manager.py
│   └── schema.sql
├── payment/
│   ├── confirm.py
│   ├── gateways.py
│   └── verifiers.py
├── utils/
│   ├── __init__.py
│   ├── auth.py
│   ├── backup.py
│   ├── date_formatter.py
│   ├── error_handler.py
│   ├── exchange.py
│   ├── i18n.py
│   ├── logger.py
│   ├── response.py
│   └── validator.py
├── web/
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── broadcast.py
│   │   ├── dashboard.py
│   │   ├── discounts.py
│   │   ├── finance.py
│   │   ├── licenses.py
│   │   ├── plans.py
│   │   ├── settings.py
│   │   └── users.py
│   ├── static/
│   ├── templates/
│   ├── discount_api.py
│   ├── invoice_api.py
│   ├── misc_api.py
│   ├── panel_api.py
│   ├── payment_api.py
│   ├── settings_api.py
│   └── users_api.py
├── install.sh
├── locales_fa.json
├── requirements.txt
└── run.py
```

## Branch Briefings

### `run.py`
* `# === IMPORTS ===`

> New absolute root entry point script. Imports the main async function from `bot.main` and runs the event loop, avoiding relative import traps when executing the bot.

### `bot/config.py`
* `# === IMPORTS AND ENV LOAD ===`
* `# === IMPORTS ===`
* `# === BOT CONFIGURATION ===`
* `# === WEB CONFIGURATION ===`

> Handles environment variable loading and sets up configuration constants. Explicitly defines `WEBHOOK_DOMAIN` to prevent import errors.

### `bot/main.py`
* `# === IMPORTS ===`
* `# === LOGGING CONFIG ===`
* `# === WEBHOOK PATH ===`
* `# === STARTUP / SHUTDOWN HANDLERS ===`
* `# === MAIN ASYNC INITIALIZATION ===`
* `# === INIT DATABASE ===`
* `# === BOT SETUP ===`
* `# === ROUTER REGISTRATION ===`
* `# === CRON TASKS ===`
* `# === WEB SERVER START ===`
* `# === ENTRY POINT ===`

> Main entry point for initializing the database, configuring the bot, registering routers, starting background tasks, and launching the web server. Refactored to use absolute imports targeting the root (e.g., `from bot.routers`) to prevent `ImportError`.

### `bot/states.py`
* `# === IMPORTS ===`
* `# === FSM STATES: ADMIN ===`
* `# === XUI Panel Management (مدیریت ثنا) ===`
* `# === FSM STATES: CHECKOUT ===`
* `# === FSM STATES: USER ===`
* `# === FSM STATES: SUPPORT ===`

> Defines finite state machine (FSM) states used by aiogram to manage conversation flows.

### `bot/routers/__init__.py`
* `# === IMPORTS EXPORTS ===`
* `# === IMPORTS ===`

> Exports all the registered routers for easier import in the main application.

### `bot/routers/admin.py`
* `# === IMPORTS ===`
* `# === ADMIN FILTER ===`
* `# === HELPER: BUILD ADMIN KEYBOARD ===`
* `# === ROUTER: /sudo COMMAND — SECURE ADMIN ENTRY ===`
* `# === ROUTER: ADMIN PANEL (callback from within admin menus only) ===`

> Streamlined entry point for Telegram Administrators. The `/admin` command serves the master inline keyboard pointing to Users, Finance, Settings, and Shop. Banned legacy features (e.g., Fast Pricing, Manual Renewals) have been purged. Fixed module import paths to use absolute imports (e.g., `bot.config`).

### `bot/routers/admin_settings.py`
* `# === IMPORTS ===`
* `# === ROUTER: SETTINGS MENU ===`
* `# === ROUTER: CHANNELS MANAGEMENT ===`
* `# === ROUTER: ADMIN MANAGEMENT ===`
* `# === ROUTER: MANAGE APPS ===`
* `# === ROUTER: QR BACKGROUND ===`

- **Settings Dashboard:** Base toggle points for bot switches.
- **Channels Management:** Add, remove forced join channels.
- **Admins Management:** Manage active admins and their IDs.
- **App Management:** Manage external VPN application download links (ported from maintenance.php).

### `bot/routers/admin_finance.py`
* `# === IMPORTS ===`
* `# === ROUTER: FINANCE MENU ===`
* `# === ROUTER: CRYPTO WALLETS ===`
* `# === ROUTER: AUTO CONFIRM EXCEPTIONS ===`
* `# === ROUTER: GLOBAL AUTO CONFIRM ===`
* `# === ROUTER: PENDING RECEIPTS ===`
* `# === ROUTER: LIMITS MENU ===`

- **Finance Menu:** Gateways toggles (Card-to-card, NowPayments, Zarinpal, AqayePardakht). Now actively read and write direct `gateway_status_*` to the SQLite `settings` table.
- **Card-to-card System:** Card number setup.
- **Auto-Confirm Exceptions:** Manage user IDs excluded from auto payment verification (ported from maintenance.php).

### `bot/routers/admin_users.py`
* `# === IMPORTS ===`
* `# === ROUTER: USERS MENU ===`
* `# === ROUTER: WALLET MANAGEMENT ===`
* `# === ROUTER: USER STATUS ===`
* `# === ROUTER: VIEW PAYMENTS ===`

> Telegram handlers for user search and management natively within the chat. Includes FSM state logic for adding/reducing Wallet Balances, blocking/unblocking users, and mocking payment views.

### `bot/routers/admin_xui.py`
* `# === IMPORTS ===`
* `# ============================================================`
* `# === ROUTER: مدیریت ثنا (XUI Panel Management) MAIN MENU ===`
* `# ============================================================`
* `# ============================================================`
* `# === FSM: ADD PANEL — 4 STEP FLOW ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: LIST ALL PANELS ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: PANEL DETAIL VIEW ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: DELETE PANEL ===`
* `# ============================================================`

> Telegram handlers for 3x-ui panel management (adding, viewing, and deleting panels) using a multi-step FSM.

### `bot/routers/admin_shop.py`
* `# === IMPORTS ===`
* `# === ROUTER: SHOP MENU ===`

> Telegram handlers for shop toggles like bulk buy and copy cart configurations.

### `bot/routers/admin_plans.py`
* `# === IMPORTS ===`
* `# ============================================================`
* `# === ROUTER: MANAGE PLANS MAIN ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: ADD PLAN FSM ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: PLAN DASHBOARD ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: FAST PRICING ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: اتصال مخزن (Panel Connection) ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: MANAGE TIME PACKAGES (comma-separated input) ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: MANAGE TRAFFIC PACKAGES (comma-separated input) ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: DELETE PLAN ===`
* `# ============================================================`

> Handles Plans, Packages, Fast Pricing, and Cargo/Stock management.

### `bot/routers/admin_reports.py`
* `# === IMPORTS ===`
* `# === ROUTER: REPORTS MENU ===`
* `# === ROUTER: FETCH STATS ===`
* `# === ROUTER: EXPORT DATA ===`
* `# === ROUTER: CRM TRIAL FOLLOW-UP ===`

> Handles Bot Statistics and reporting for various timeframes (today, yesterday, this month). Generates dynamic CSV data exports for Users, Orders, and Payments and sends them as native Telegram documents.

### `bot/routers/checkout.py`
* `# === IMPORTS ===`
* `# === HELPER: GENERATE INVOICE ===`
* `# ============================================================`
* `# === STEP 0: CONFIG NOTE PROMPT (before calculator) ===`
* `# ============================================================`
* `# ============================================================`
* `# === ROUTER: CALCULATOR ===`
* `# ============================================================`
* `# === ROUTER: PRE-PAYMENT INVOICE ===`
* `# === ROUTER: DISCOUNT CODE ===`
* `# === ROUTER: GIFT CODE ===`
* `# === ROUTER: CANCEL MODIFIER ===`
* `# === ROUTER: FREE TEST ===`

> Handles the unified FSM user checkout process.
> - Renders the Smart Unified Calculator which allows simultaneous selection of Time and Traffic packages.
> - Dynamically hides Time or Traffic grids if a plan explicitly only has one type of package defined.
> - Handles wallet deduction logic and dynamic invoice processing prior to payment delegation.

### `bot/routers/payment.py`
* `# === IMPORTS ===`
* `# === ROUTER: UNIFIED PAYMENT HANDLER ===`
* `# === ROUTER: ADMIN RECEIPT APPROVAL ===`

> Decoupled generic payment handler routing.
> - Captures all `pay_*` callbacks triggered from checkout.
> - Handles offline gateway generation for Card, USDT, and GRAM natively, fetching live exchange rates via `utils/exchange.py`.
> - Dynamically fetches the required Gateway API credentials directly from the `settings` table.
> - Initializes classes from `payment/gateways.py` for online gateways (e.g. Tetra), requests payment URLs, and instantly redirects the user via native Telegram URL buttons.

### `bot/routers/support.py`
* `# === IMPORTS ===`
* `# === ROUTER: SUPPORT REQUEST ===`
* `# === ROUTER: ADMIN REPLY ===`

> Manages user support requests and allows admins to reply directly to users.

### `bot/routers/user.py`
* `# === IMPORTS ===`
* `# === ROUTER: START COMMAND ===`
* `# === ROUTER: BUY SUBSCRIPTION ===`
* `# === ROUTER: USER PROFILE ===`
* `# === ROUTER: MAIN MENU ===`
* `# === NEW HANDLERS FOR USER ROUTER ===`
* `# === ROUTER: ACQUISITION & FEEDBACK ===`

> Core Telegram user interfaces. Expanded to include Native Wallet Top-Up (شارژ حساب), Affiliate Dashboard generation, and viewing purchased services. Dynamically fetches welcome texts and keyboard layouts directly from the SQLite `settings` table.

### `bot/services/broadcast.py`
* `# === IMPORTS ===`
* `# === BROADCAST SERVICE ===`

> Handles background processing of broadcast queues and notifications, natively triggering `aiogram` sends.

### `bot/services/xui_client.py`
* `# === IMPORTS ===`

> Async HTTP client for communicating with the 3x-UI panel API. Handles provisioning and renewing licenses.

### `cron/tasks.py`
* `# === IMPORTS ===`
* `# === BACKGROUND TASK: PAYMENT CHECK ===`
* `# === BACKGROUND TASK: DB CLEANUP ===`
* `# === BACKGROUND TASK: NOTIFICATIONS & BROADCAST ===`
* `# === BACKGROUND TASK: HOUSEKEEPING ===`
* `# === CRON SETUP ===`

> Sets up and runs periodic background tasks natively in asyncio for verifying payments, cleaning up the database, housekeeping (discounts/gifts expiry), lottery scoring, and broadcasting queued messages.

### `database/db_manager.py`
* `# === IMPORTS AND CONFIG ===`
* `# === IMPORTS ===`
* `# === DATABASE INITIALIZATION ===`
* `# === USER OPERATIONS ===`
* `# === GENERIC DB OPERATIONS ===`
* `# === AUTH DB OPERATIONS ===`
* `# === NEW API OPERATIONS ===`
* `# === PLAN OPERATIONS ===`
* `# === PACKAGE OPERATIONS ===`
* `# === CARGO OPERATIONS ===`
* `# === INVOICE OPERATIONS ===`
* `# === DISCOUNT & GIFT OPERATIONS ===`
* `# === DISCOUNT DB OPERATIONS ===`
* `# === PAYMENT DB OPERATIONS ===`
* `# === SETTING DB OPERATIONS ===`
* `# === LOGGING OPERATIONS ===`
* `# === STATS OPERATIONS ===`
* `# === DISCOUNTS & GIFTS ===`
* `# ============================================================`
* `# === XUI PANEL DB OPERATIONS ===`
* `# ============================================================`
* `# ============================================================`
* `# === PLAN ↔ PANEL BINDING ===`
* `# ============================================================`
* `# ============================================================`
* `# === XUI LICENSE OPERATIONS ===`
* `# ============================================================`
* `# ============================================================`
* `# === INVOICE UPDATE HELPERS (XUI-SPECIFIC) ===`
* `# ============================================================`
* `# ============================================================`
* `# === OPERATING MODE ===`
* `# ============================================================`
* `# ============================================================`
* `# === WALLET LEDGER ===`
* `# ============================================================`
* `# ============================================================`
* `# === CASHBACK ===`
* `# ============================================================`
* `# ============================================================`
* `# === REFERRAL / AFFILIATE ===`
* `# ============================================================`
* `# ============================================================`
* `# === CUSTOMER FEEDBACK ===`
* `# ============================================================`
* `# ============================================================`
* `# === ACQUISITION SURVEY ===`
* `# ============================================================`
* `# ============================================================`
* `# === INVOICE STATUS HELPERS ===`
* `# ============================================================`

> Provides asynchronous functions for interacting with the SQLite database to manage users, plans, invoices, and other core data. Now includes generic key-value `get_setting` and `set_setting` functions for dynamic configurations.

### `database/schema.sql`
> Raw SQLite schema statements used to initialize the `candy.db` structure.

### `payment/confirm.py`
* `# === IMPORTS ===`
* `# === PAYMENT CONFIRMATION LOGIC ===`

> Handles side effects of payment states (Paid, Failed, Expired), replacing legacy `PaymentConfirm.php`. Manages DB updates, cashback logic, and sends notifications via the aiogram bot.

### `payment/gateways.py`
* `# === IMPORTS ===`
* `# === BASE GATEWAY CLASS ===`

> Contains the base PaymentGateway interface and the TetraGateway implementation for online payments.

### `payment/verifiers.py`
* `# === IMPORTS ===`
* `# === PAYMENT VERIFIERS ===`

> Contains an empty skeleton for processing pending invoices. Online verifiers have been purged.

### `utils/auth.py`
* `# === IMPORTS ===`

> Validates Telegram init data and extracts Bearer tokens for API auth.

### `utils/date_formatter.py`
* `# === IMPORTS ===`
* `# === JALALI DATE FORMATTER ===`

> Replaces the legacy `jdf.php` module. Provides native Python wrappers for converting UNIX timestamps to Persian (Jalali) dates using `jdatetime`.

### `utils/error_handler.py`
* `# === IMPORTS ===`

> Middleware for trapping exceptions in the web API and converting them into JSON error responses.

### `utils/exchange.py`
* `# === IMPORTS ===`
* `# === CONSTANTS ===`
* `# === EXCHANGE RATE FETCHERS ===`

> Retrieves dynamic cryptocurrency-to-Toman exchange rates (USDT and TON/GRAM) by scraping multiple fallback providers natively, replacing the legacy `arz.php` and `arzgram.php`.

### `utils/i18n.py`
* `# === IMPORTS ===`
* `# === LOCALIZATION (I18N) MANAGER ===`

> Loads and serves the massive nested JSON dictionaries from `locales_fa.json` (formerly `text.json`) into memory natively.

### `utils/logger.py`
* `# === IMPORTS ===`

> File-based JSON custom logger.

### `utils/response.py`
* `# === IMPORTS ===`

> Helpers for formatting standardized JSON responses in aiohttp handlers.

### `utils/validator.py`
* `# === IMPORTS ===`

> Sanitizes and validates request payloads and inputs for the API endpoints.

### `utils/backup.py`
* `# === IMPORTS ===`
* `# === BACKUP UTILITY ===`

> Creates zipped backups of the SQLite database (`candy.db`) natively, replacing the legacy `mysqldump` and PHP zip architecture.

### `web/discount_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: DISCOUNTS ===`
* `# === API ENDPOINTS: DISCOUNT SELLS ===`
* `# === ROUTER REGISTRATION ===`

> Provides web API endpoints for managing discounts and discount sells.

### `web/invoice_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: INVOICES ===`
* `# === ROUTER REGISTRATION ===`

> Provides web API endpoints for accessing and managing invoices and services.

### `web/misc_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: UTILITIES ===`
* `# === API ENDPOINTS: LOGGING ===`
* `# === ROUTER REGISTRATION ===`

> Handles miscellaneous utilities like QR code generation, diagnostic health checks (`/api/diag`), and client/bot logging endpoints.

### `web/panel_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS ===`
* `# === WEB APP INITIALIZATION ===`

> Initializes the aiohttp web application, attaches middlewares, and defines primary API endpoints for panel data access.

### `web/payment_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: PAYMENTS ===`
* `# === API ENDPOINTS: PAYMENT ACTIONS ===`
* `# === API ENDPOINTS: WEBHOOKS & CALLBACKS ===`
* `# === ROUTER REGISTRATION ===`

> Provides core web API endpoints for viewing payment reports and initializing payments. Retains SMS auto-verification webhook for card payments and callback webhook for Tetra gateway.

### `web/settings_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: SETTINGS ===`
* `# === ROUTER REGISTRATION ===`

> Provides web API endpoints for configuring bot, shop, and brand settings.

### `web/users_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: USERS ===`
* `# === API ENDPOINTS: OTHERS ===`
* `# === ROUTER REGISTRATION ===`

> Provides web API endpoints for managing user accounts, balances, verifications, and other user actions.

### `install.sh`
> Shell script for automating the installation and dependency resolution.

### `locales_fa.json`
> JSON dictionary containing the Persian (Farsi) string localizations used throughout the bot interfaces.

### `requirements.txt`
> Python package dependencies required to run the CandyBot application.
