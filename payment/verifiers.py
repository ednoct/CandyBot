"""
payment/verifiers.py
--------------------
Webhook signature verification and periodic polling/recovery for pending FrenzyEx invoices.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import aiosqlite

from database import db_manager
from payment.gateways import FrenzyExGateway

logger = logging.getLogger(__name__)


class PaymentVerifier:
    """Handles HMAC verification and active polling recovery for pending gateway requests."""

    @staticmethod
    def verify_frenzyex_signature(raw_body: bytes, signature: str, secret: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature of a FrenzyEx webhook payload over exact raw bytes.
        """
        if not raw_body or not signature or not secret:
            return False

        expected_hmac = hmac.new(
            secret.strip().encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_hmac, signature.strip().lower())

    @staticmethod
    async def process_pending_invoices(confirmation_manager) -> None:
        """
        Polls pending FrenzyEx payment requests to:
        1. Recover missed webhooks (status == 'paid').
        2. Mark expired/canceled requests (status in ('expired', 'canceled')) after 60m lifetime.
        """
        api_key = await db_manager.get_setting("frenzyex_api_key", "")
        base_url = await db_manager.get_setting("frenzyex_base_url", "https://frenzy.fastsnap.info")
        if not api_key:
            return

        try:
            gateway = FrenzyExGateway(api_key=api_key, base_url=base_url)
        except ValueError as e:
            logger.error("Cannot initialize FrenzyExGateway in verifier: %s", e)
            return

        async with aiosqlite.connect(db_manager.DB_PATH) as db:
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

        for row in pending_rows:
            invoice_id = row["invoice_id"]
            request_id = row["gateway_request_id"]
            expected_amount = row["final_amount"]

            check = await gateway.verify_payment(
                request_id=request_id,
                expected_amount=expected_amount,
                expected_order_ref=invoice_id,
                expected_ccy="TMN",
            )
            if not check.get("success"):
                continue

            remote_status = check.get("status")
            if remote_status == "paid":
                tx_hash = check.get("tx_hash") or ""
                paid_at = check.get("paid_at") or ""
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute(
                        """
                        UPDATE payment_reports
                        SET crypto_hash = COALESCE(NULLIF(?, ''), crypto_hash),
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
                    await db.execute(
                        "UPDATE payment_reports SET status = 'expire' WHERE invoice_id = ?",
                        (invoice_id,),
                    )
                    await db.commit()
                await confirmation_manager.mark_expired(invoice_id)

            elif remote_status == "canceled":
                logger.info("FrenzyEx request canceled: %s (req=%s)", invoice_id, request_id)
                async with aiosqlite.connect(db_manager.DB_PATH) as db:
                    await db.execute(
                        "UPDATE payment_reports SET status = 'failed' WHERE invoice_id = ?",
                        (invoice_id,),
                    )
                    await db.commit()
                await confirmation_manager.notify_failed(invoice_id, reason="لغو شده در درگاه پرداخت")