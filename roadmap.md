# CandyBot Roadmap

## Payment & Finance Reliability
- Add a unified `PaymentGatewayInterface` so Tetra98, ZarinPal, AqayePardakht, NowPayments, Plisio, card-to-card, and Telegram Stars share the same create, verify, expire, and reporting lifecycle.
- Add Tetra98-specific regression tests for toman-to-rial conversion, Telegram payment URL generation, callback domain generation from `$domainhosts`, authority/hash verification, and duplicate callback idempotency.
- Store gateway callbacks in an append-only payment event log before mutating wallet balances, making duplicate callbacks idempotent and auditable.
- Add a finance health dashboard that shows gateway uptime, failed invoice reasons, callback latency, daily totals, and suspicious duplicate-payment attempts.
- Introduce admin-configurable payment routing rules, such as minimum/maximum amount, user trust level, gateway daily cap, and fallback gateway order.

## Admin Experience
- Add a guided setup wizard that validates bot token, webhook domain, database connectivity, payment API keys, panel connectivity, and cron status.
- Add masked secret fields with “test connection” buttons for every payment gateway.
- Add role-based admin permissions for finance, users, products, panels, broadcasts, and settings.
- Add audit logs for sensitive actions such as wallet edits, gateway key changes, service deletion, and mass messaging.

## Telegram Bot UX
- Add payment progress messages that update automatically from “invoice created” to “waiting for gateway” to “paid” or “expired”.
- Add multilingual onboarding flows with user language auto-detection and per-user language preference.
- Add richer support flows with ticket categories, priorities, canned replies, and optional operator assignment.
- Add smart renewal reminders based on remaining time, remaining volume, and historical renewal behavior.

## Product & Subscription Automation
- Add plan recommendation logic that suggests packages based on previous usage patterns.
- Add configurable trials with anti-abuse controls for device fingerprint, phone verification, and per-panel quotas.
- Add bundle products that can include multiple locations, multiple protocols, or family/team seats.
- Add automated downgrade/upgrade paths with prorated balance calculations.

## Operations & Observability
- Add structured JSON logging and a log viewer in the admin panel.
- Add background queue workers for payment verification, panel provisioning, broadcasts, and webhook retries.
- Add cron health monitoring with last-run timestamps and Telegram alerts when jobs are stale.
- Add backup automation for database dumps, config snapshots, and encrypted off-site storage.

## Security Hardening
- Encrypt stored gateway API keys and other secrets at rest.
- Add CSRF coverage checks for all panel write actions and rate limiting for login/API endpoints.
- Add webhook signature or shared-secret validation where supported by payment providers.
- Add input validation schemas for admin settings, payment callbacks, and public API requests.

## Developer Quality
- Split large procedural bot files into services for payments, users, invoices, panels, localization, and notifications.
- Add PHPUnit tests for payment callbacks, wallet mutations, invoice creation, and translation key coverage.
- Add a staging mode with sandbox payment keys and fake panel adapters.
- Add CI checks for PHP syntax, static analysis, translation parity, and database migration safety.
