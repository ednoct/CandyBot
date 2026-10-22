"""
payment/verifiers.py
--------------------
Webhook signature verification, shared per-invoice concurrency locks,
and bounded concurrent polling/recovery for pending FrenzyEx invoices.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import aiosqlite

from database import db_manager
from payment.gateways import FrenzyExGateway

logger = logging.getLogger(__name__)

from payment.confirm import get_invoice_lock


class PaymentVerifier:
    """Handles HMAC verification and active polling recovery for pending gateway requests."""

    @staticmethod
    def verify_frenzyex_signature(raw_body: bytes, signature: str, secret: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature of a FrenzyEx webhook payload over exact raw bytes.
        Uses byte-level constant-time comparison to avoid TypeError on non-ASCII inputs.
        """
        if not raw_body or not signature or not secret:
            return False
        try:
            expected_bytes = hmac.new(
                secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest().encode("ascii")
            received_bytes = signature.strip().lower().encode("ascii")
        except UnicodeEncodeError:
            return False
        return hmac.compare_digest(expected_bytes, received_bytes)

    @staticmethod
    async def process_pending_invoices(confirmation_manager) -> None:
        """
        Polls pending FrenzyEx payment requests to:
        1. Recover missed webhooks (status == 'paid').
        2. Mark expired/canceled requests (status in ('expired', 'canceled')) after 60m lifetime.
        """
        api_key = (await db_manager.get_setting("frenzyex_api_key", "")).strip()
        base_url = (await db_manager.get_setting("frenzyex_base_url", "https://frenzy.fastsnap.info")).strip()
        if not api_key:
            return

        try:
            gateway = FrenzyExGateway(api_key=api_key, base_url=base_url)
        except ValueError as exc:
            logger.error("Cannot initialize FrenzyExGateway in verifier: %s", exc)
            return

        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout = 5000;")
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT pr.invoice_id, pr.gateway_request_id, i.final_amount, i.status AS inv_status
                FROM payment_reports pr
                JOIN invoices i ON pr.invoice_id = i.id
                WHERE i.status = 'pending'
                  AND pr.status IN ('pending', 'Unpaid')
                  AND pr.gateway_request_id IS NOT NULL
                  AND pr.gateway_request_id != ''
                ORDER BY pr.created_at ASC
                LIMIT 25
                """
            ) as cursor:
                pending_rows = await cursor.fetchall()

        if not pending_rows:
            return

        sem = asyncio.Semaphore(5)

        async def _check_one(row: aiosqlite.Row) -> None:
            invoice_id = str(row["invoice_id"]).strip()
            request_id = str(row["gateway_request_id"]).strip()
            expected_amount = row["final_amount"]

            async with sem:
                check = await gateway.verify_payment(
                    request_id=request_id,
                    expected_amount=expected_amount,
                    expected_order_ref=invoice_id,
                    expected_ccy="TMN",
                )

            if not check.get("success"):
                return

            remote_status = check.get("status")
            if remote_status not in ("paid", "expired", "canceled"):
                return

            lock = get_invoice_lock(invoice_id)
            async with lock:
                # Enforce FrenzyEx deduplication & idempotency: check current invoice state under lock
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute("PRAGMA busy_timeout = 5000;")
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) as cur:
                        inv_check = await cur.fetchone()
                    if not inv_check or inv_check["status"] != "pending":
                        return

                if remote_status == "paid":
                    tx_hash = check.get("tx_hash") or ""
                    paid_at = check.get("paid_at") or ""
                    async with aiosqlite.connect(db_manager.DB_PATH) as db:
                        await db.execute("PRAGMA busy_timeout = 5000;")
                        await db.execute(
                            """
                            UPDATE payment_reports
                            SET status = 'paid',
                                crypto_hash = COALESCE(NULLIF(?, ''), crypto_hash),
                                receipt_time = COALESCE(NULLIF(?, ''), receipt_time)
                            WHERE invoice_id = ? AND gateway_request_id = ?
                            """,
                            (tx_hash, paid_at, invoice_id, request_id),
                        )
                        await db.commit()
                    logger.info("Recovered paid FrenzyEx invoice via polling: %s (req=%s)", invoice_id, request_id)
                    await confirmation_manager.confirm_paid(invoice_id, method="FrenzyEx Polling")

                elif remote_status == "expired":
                    logger.info("FrenzyEx request expired: %s (req=%s)", invoice_id, request_id)
                    async with aiosqlite.connect(db_manager.DB_PATH) as db:
                        await db.execute("PRAGMA busy_timeout = 5000;")
                        await db.execute(
                            "UPDATE payment_reports SET status = 'expired' WHERE invoice_id = ? AND status IN ('pending', 'Unpaid')",
                            (invoice_id,),
                        )
                        await db.commit()
                    await confirmation_manager.mark_expired(invoice_id)

                elif remote_status == "canceled":
                    logger.info("FrenzyEx request canceled: %s (req=%s)", invoice_id, request_id)
                    async with aiosqlite.connect(db_manager.DB_PATH) as db:
                        await db.execute("PRAGMA busy_timeout = 5000;")
                        await db.execute(
                            "UPDATE payment_reports SET status = 'canceled' WHERE invoice_id = ? AND status IN ('pending', 'Unpaid')",
                            (invoice_id,),
                        )
                        await db.commit()
                    await confirmation_manager.notify_failed(invoice_id, reason="لغو شده توسط کاربر یا درگاه")

        await asyncio.gather(*(_check_one(r) for r in pending_rows), return_exceptions=True)