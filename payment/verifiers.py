"""
verifiers.py
------------
Module containing functionalities for verifiers.
"""
# === IMPORTS ===
import aiohttp
import logging
from database import db_manager
import aiosqlite

# === PAYMENT VERIFIERS ===
class PaymentVerifier:
    """
    Modular verifiers replacing legacy cronbots (cryptocheck, iranpay1, nowpaymentcheck, plisio).
    """
    
    @staticmethod
    async def process_pending_invoices(confirmation_manager):
        """
        Orchestrator to find pending invoices and run verifiers.
        This handles the database abstraction previously done by legacy cronbots.
        """
        pass

    @staticmethod
    def verify_frenzyex_signature(raw_body: bytes, signature: str, secret: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature of a FrenzyEx webhook payload.
        """
        import hmac
        import hashlib
        
        if not signature or not secret:
            return False
            
        computed_hmac = hmac.new(
            secret.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_hmac, signature)
