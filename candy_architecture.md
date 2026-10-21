# CandyBot Architecture Map

```text
/CandyBot/
├── bot/
│   ├── config.py
│   ├── main.py
│   ├── states.py
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── force_join.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── admin_agent.py
│   │   ├── admin_discounts.py
│   │   ├── admin_finance.py
│   │   ├── admin_free_trial.py
│   │   ├── admin_plans.py
│   │   ├── admin_reports.py
│   │   ├── admin_settings.py
│   │   ├── admin_support.py
│   │   ├── admin_users.py
│   │   ├── admin_xui.py
│   │   ├── agent.py
│   │   ├── agent_support.py
│   │   ├── checkout.py
│   │   ├── payment.py
│   │   ├── support.py
│   │   ├── user.py
│   │   └── user_free_trial.py
│   └── services/
│       ├── __init__.py
│       ├── broadcast.py
│       ├── channel_service.py
│       ├── notifications.py
│       ├── sub_stats.py
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
│   ├── ui_helpers.py
│   └── validator.py
├── install.sh
├── locales_fa.json
├── requirements.txt
└── run.py

## Branch Briefings

Module Briefings
run.py
Root entry point script. Imports main() from bot.main and starts the asyncio event loop.

bot/config.py
Loads .env variables and configures bot tokens, admin IDs, webhook paths, and SSL certificate paths.

bot/main.py
Initializes the SQLite database (WAL mode), registers all 18 Telegram routers, launches background cron tasks, and runs the aiohttp server hosting the FrenzyEx IPN webhook (/ipn/frenzyex) and optional Telegram webhook endpoint.

payment/gateways.py
Implements FrenzyExGateway compliant with FrenzyEx Merchant API v1.0 (POST /api/v1/payment-requests, GET /api/v1/payment-requests/{request_id}, POST /api/v1/payment-requests/{request_id}/cancel) using a shared httpx.AsyncClient pool.

payment/verifiers.py
Implements constant-time HMAC-SHA256 signature verification over raw HTTP request bytes and active polling recovery for pending FrenzyEx invoices.

payment/confirm.py
Implements PaymentConfirmationManager with task-reentrant per-invoice locking, atomic wallet ledgering, cashback/referral/agent commission payouts, and 3x-UI license provisioning & smart renewal (unexpired vs. expired keep_plan / change_plan).

bot/services/xui_client.py
Async client for 3x-UI / Sanaei panels supporting client provisioning, in-place renewal (including unlimited traffic/time), cross-panel migration preserving sub_id, and client deletion.

cron/tasks.py
Runs periodic background jobs: FrenzyEx active polling & offline payment expiration (every 60s), 3x-UI low-quota alerts (every 6h), automatic cleanup of expired XUI licenses >2 days past expiry from both 3x-UI panel and DB (every 6h), nightly backup & stats report (every 24h), and bi-weekly DB optimization.