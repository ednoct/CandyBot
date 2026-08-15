# Candy Architecture Map

```text
/python_candy/
├── bot/
│   ├── config.py
│   ├── main.py
│   ├── states.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── admin_settings.py
│   │   ├── admin_finance.py
│   │   ├── admin_users.py
│   │   ├── admin_shop.py
│   │   ├── admin_plans.py
│   │   ├── admin_reports.py
│   │   ├── checkout.py
│   │   ├── payment.py
│   │   └── user.py
│   └── services/
│       └── broadcast.py
├── cron/
│   └── tasks.py
├── database/
│   └── db_manager.py
├── payment/
│   ├── confirm.py
│   ├── gateways.py
│   └── verifiers.py
├── run.py
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
└── web/
    ├── admin/
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── broadcast.py
    │   ├── dashboard.py
    │   ├── discounts.py
    │   ├── finance.py
    │   ├── licenses.py
    │   ├── plans.py
    │   ├── settings.py
    │   └── users.py
    ├── discount_api.py
    ├── invoice_api.py
    ├── misc_api.py
    ├── panel_api.py
    ├── payment_api.py
    ├── settings_api.py
    └── users_api.py
```

## Branch Briefings

### `run.py`
> New absolute root entry point script. Imports the main async function from `bot.main` and runs the event loop, avoiding relative import traps when executing the bot.

### `bot/config.py`
* `# === IMPORTS AND ENV LOAD ===`
* `# === BOT CONFIGURATION ===`
* `# === WEB CONFIGURATION ===`
> Handles environment variable loading and sets up configuration constants. Explicitly defines `WEBHOOK_DOMAIN` to prevent import errors.

### `bot/main.py`
* `# === IMPORTS ===`
* `# === LOGGING CONFIG ===`
* `# === MAIN ASYNC INITIALIZATION ===`
* `# === INIT DATABASE ===`
* `# === BOT SETUP ===`
* `# === ROUTER REGISTRATION ===`
* `# === CRON TASKS ===`
* `# === WEB SERVER START ===`
* `# === BOT START POLLING ===`
* `# === ENTRY POINT ===`
> Main entry point for initializing the database, configuring the bot, registering routers, starting background tasks, and launching the web server. Refactored to use absolute imports targeting the root (e.g., `from bot.routers`) to prevent `ImportError`.

### `bot/states.py`
* `# === IMPORTS ===`
* `# === FSM STATES: ADMIN ===`
* `# === FSM STATES: CHECKOUT ===`
* `# === FSM STATES: SUPPORT ===`
> Defines finite state machine (FSM) states used by aiogram to manage conversation flows.

### `bot/routers/__init__.py`
* `# === IMPORTS EXPORTS ===`
> Exports all the registered routers for easier import in the main application.

### `bot/routers/admin.py`
* `# === IMPORTS ===`
* `# === ADMIN FILTER ===`
* `# === ROUTER: ADMIN PANEL ===`
> Streamlined entry point for Telegram Administrators. The `/admin` command serves the master inline keyboard pointing to Users, Finance, Settings, and Shop. Banned legacy features (e.g., Fast Pricing, Manual Renewals) have been purged. Fixed module import paths to use absolute imports (e.g., `bot.config`).

### `bot/routers/admin_settings.py`
* `# === IMPORTS ===`
* `# === ROUTER: SETTINGS MENU ===`
* `# === ROUTER: CHANNELS MANAGEMENT ===`
* `# === ROUTER: ADMIN MANAGEMENT`
- **Settings Dashboard:** Base toggle points for bot switches.
- **Channels Management:** Add, remove forced join channels.
- **Admins Management:** Manage active admins and their IDs.
- **App Management:** Manage external VPN application download links (ported from maintenance.php).

### `bot/routers/admin_finance.py`
* `# === ROUTER: FINANCE MENU ===`
- **Finance Menu:** Gateways toggles (Card-to-card, NowPayments, Zarinpal, AqayePardakht). Now actively read and write direct `gateway_status_*` to the SQLite `settings` table.
- **Card-to-card System:** Card number setup.
- **Auto-Confirm Exceptions:** Manage user IDs excluded from auto payment verification (ported from maintenance.php).

### `bot/routers/admin_users.py`
* `# === ROUTER: USERS MENU ===`
* `# === ROUTER: WALLET MANAGEMENT ===`
* `# === ROUTER: USER STATUS ===`
* `# === ROUTER: VIEW PAYMENTS ===`
> Telegram handlers for user search and management natively within the chat. Includes FSM state logic for adding/reducing Wallet Balances, blocking/unblocking users, and mocking payment views.

### `bot/routers/admin_shop.py`
* `# === ROUTER: SHOP MENU ===`
> Telegram handlers for shop toggles like bulk buy and copy cart configurations.

### `bot/routers/admin_plans.py`
* `# === IMPORTS ===`
* `# === ROUTER: MANAGE PLANS ===`
* `# === ROUTER: MANAGE PLAN PACKAGES ===`
* `# === ROUTER: FAST PRICING ===`
* `# === ROUTER: MANAGE CARGO ===`
> Handles Plans, Packages, Fast Pricing, and Cargo/Stock management.

### `bot/routers/admin_reports.py`
* `# === IMPORTS ===`
* `# === ROUTER: REPORTS MENU ===`
* `# === ROUTER: FETCH STATS ===`
* `# === ROUTER: EXPORT DATA ===`
> Handles Bot Statistics and reporting for various timeframes (today, yesterday, this month). Generates dynamic CSV data exports for Users, Orders, and Payments and sends them as native Telegram documents.

### `bot/routers/checkout.py`
* `# === IMPORTS ===`
* `# === HELPER: GENERATE INVOICE ===`
* `# === ROUTER: SELECT PLAN AND TIME ===`
* `# === ROUTER: SELECT TRAFFIC ===`
* `# === ROUTER: PRE-PAYMENT INVOICE ===`
* `# === ROUTER: DISCOUNT CODE ===`
* `# === ROUTER: GIFT CODE ===`
* `# === ROUTER: CANCEL MODIFIER ===`
> Handles the unified FSM user checkout process.
> - Renders the Smart Unified Calculator which allows simultaneous selection of Time and Traffic packages.
> - Dynamically hides Time or Traffic grids if a plan explicitly only has one type of package defined.
> - Handles wallet deduction logic and dynamic invoice processing prior to payment delegation.

### `bot/routers/payment.py`
* `# === ROUTER: UNIFIED PAYMENT HANDLER ===`
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
> Core Telegram user interfaces. Expanded to include Native Wallet Top-Up (شارژ حساب), Affiliate Dashboard generation, and viewing purchased services. Dynamically fetches welcome texts and keyboard layouts directly from the SQLite `settings` table.

### `bot/services/broadcast.py`
* `# === IMPORTS ===`
* `# === BROADCAST SERVICE ===`
> Handles background processing of broadcast queues and notifications, natively triggering `aiogram` sends.

### `cron/tasks.py`
* `# === IMPORTS ===`
* `# === BACKGROUND TASK: PAYMENT CHECK ===`
* `# === BACKGROUND TASK: DB CLEANUP ===`
* `# === BACKGROUND TASK: NOTIFICATIONS & BROADCAST ===`
* `# === BACKGROUND TASK: HOUSEKEEPING ===`
* `# === BACKGROUND TASK: LOTTERY ===`
* `# === CRON SETUP ===`
> Sets up and runs periodic background tasks natively in asyncio for verifying payments, cleaning up the database, housekeeping (discounts/gifts expiry), lottery scoring, and broadcasting queued messages.

### `database/db_manager.py`
* `# === IMPORTS AND CONFIG ===`
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
> Provides asynchronous functions for interacting with the SQLite database to manage users, plans, invoices, and other core data. Now includes generic key-value `get_setting` and `set_setting` functions for dynamic configurations.

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
* `# === API AUTHENTICATION ===`
> Validates Telegram init data and extracts Bearer tokens for API auth.

### `utils/date_formatter.py`
* `# === JALALI DATE FORMATTER ===`
> Replaces the legacy `jdf.php` module. Provides native Python wrappers for converting UNIX timestamps to Persian (Jalali) dates using `jdatetime`.

### `utils/error_handler.py`
* `# === WEB ERROR MIDDLEWARE ===`
> Middleware for trapping exceptions in the web API and converting them into JSON error responses.

### `utils/exchange.py`
* `# === IMPORTS ===`
* `# === CONSTANTS ===`
* `# === EXCHANGE RATE FETCHERS ===`
> Retrieves dynamic cryptocurrency-to-Toman exchange rates (USDT and TON/GRAM) by scraping multiple fallback providers natively, replacing the legacy `arz.php` and `arzgram.php`.

### `utils/i18n.py`
* `# === LOCALIZATION (I18N) MANAGER ===`
> Loads and serves the massive nested JSON dictionaries from `locales_fa.json` (formerly `text.json`) into memory natively.

### `utils/logger.py`
* `# === CUSTOM LOGGER ===`
> File-based JSON custom logger.

### `utils/response.py`
* `# === API RESPONSES ===`
> Helpers for formatting standardized JSON responses in aiohttp handlers.

### `utils/validator.py`
* `# === API INPUT VALIDATION ===`
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
* `# === API ENDPOINTS: SERVICES ===`
* `# === API ENDPOINTS: ACTIONS ===`
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
* `# === ROUTER REGISTRATION ===`
> Provides core web API endpoints for viewing payment reports and initializing payments. Retains SMS auto-verification webhook for card payments and callback webhook for Tetra gateway.

### `web/settings_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: SETTINGS ===`
* `# === API ENDPOINTS: BRAND ===`
* `# === ROUTER REGISTRATION ===`
> Provides web API endpoints for configuring bot, shop, and brand settings.

### `web/users_api.py`
* `# === IMPORTS ===`
* `# === API ENDPOINTS: USERS ===`
* `# === API ENDPOINTS: OTHERS ===`
* `# === ROUTER REGISTRATION ===`
> Provides web API endpoints for managing user accounts, balances, verifications, and other user actions.

### `web/admin/*` (The New Admin Web Panel)
* **`auth.py`**: Manages secure session-based login and logout for the admin.
* **`dashboard.py`**: Renders the main index dashboard displaying financial charts and core system stats.
* **`plans.py`**: Completely replaces legacy `panels.php`. Manages the creation of base Plans (e.g., Bronze, Silver, Gold) and their Time/Traffic combinations.
* **`licenses.py`**: The "مخزن لایسنس ها" replacing legacy "انبار شبکه ملی". Allows the admin to upload raw Candy Connect licenses and assign them to specific Plans.
* **`users.py`**: Renders the user management view.
* **`finance.py`**: Renders financial reports, invoices, and pending payment tables.
* **`discounts.py`**: Manages discount codes.
* **`broadcast.py`**: Provides the interface for sending global messages to users via the queue.
* **`settings.py`**: Renders the interface for managing bot configurations including core settings, bot texts (Welcome, Rules), and dynamic JSON keyboard layouts.
