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
    Modular verifiers replacing legacy cronbots (croncard, cryptocheck, iranpay1, nowpaymentcheck, plisio).
    """
    
    @staticmethod
    async def process_pending_invoices(confirmation_manager):
        """
        Orchestrator to find pending invoices and run verifiers.
        This handles the database abstraction previously done by croncard.php, etc.
        """
        pass
