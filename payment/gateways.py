"""
payment/gateways.py
-------------------
Production-ready, async FrenzyEx Merchant API v1.0 client with connection pooling,
strict input/URL validation, structured error handling, and bounded retries.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class PaymentGateway:
    """Base interface for online payment gateways."""

    async def create_payment(
        self,
        order_id: str,
        amount: int | float,
        callback_url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def verify_payment(
        self,
        request_id: str,
        expected_amount: Optional[int | float] = None,
        expected_order_ref: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def cancel_payment(self, request_id: str) -> dict[str, Any]:
        raise NotImplementedError


class FrenzyExGateway(PaymentGateway):
    """
    FrenzyEx Merchant API v1.0 implementation compliant with official documentation.
    """

    ALLOWED_CURRENCIES = {"TMN", "TRX"}
    ALLOWED_METHODS = {"auto", "standard", "nowpay"}
    TERMINAL_STATUSES = {"paid", "expired", "canceled"}

    _shared_client: Optional[httpx.AsyncClient] = None
    _client_lock = asyncio.Lock()

    def __init__(self, api_key: str, base_url: str = "https://frenzy.fastsnap.info"):
        if not api_key or not api_key.strip():
            raise ValueError("FrenzyEx API key is required.")
        self.api_key = api_key.strip()
        self.base_url = self._validate_base_url(base_url)

    @staticmethod
    def _validate_base_url(url: str) -> str:
        cleaned = (url or "https://frenzy.fastsnap.info").strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"Invalid FrenzyEx base_url (must be HTTPS): {url}")
        return cleaned

    @staticmethod
    def validate_callback_url(callback_url: str) -> str:
        """
        Validates callback_url according to Section 04 & 10:
        - Must be HTTPS
        - Must not resolve/point to loopback or private IP space
        """
        cleaned = (callback_url or "").strip()
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("callback_url must use https scheme and have a valid hostname.")

        host = parsed.hostname.lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("callback_url must not point to localhost/loopback.")

        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("callback_url must not point to a private or reserved IP address.")
        except ValueError as e:
            if "callback_url" in str(e):
                raise
            # Hostname is a domain name, not an IP literal

        return cleaned

    @classmethod
    async def get_http_client(cls) -> httpx.AsyncClient:
        """Returns a shared httpx.AsyncClient instance with connection pooling and bounded timeouts."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            async with cls._client_lock:
                if cls._shared_client is None or cls._shared_client.is_closed:
                    cls._shared_client = httpx.AsyncClient(
                        timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
                        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                        follow_redirects=False,
                        verify=True,
                    )
        return cls._shared_client

    @classmethod
    async def close_http_client(cls) -> None:
        """Closes the shared HTTP client cleanly on bot shutdown."""
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json_payload: Optional[dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        """
        Executes an HTTP request following Section 10 Retry Matrix:
        - Retries network errors, HTTP 429, and HTTP 5xx with exponential backoff + jitter.
        - Does NOT retry 400, 401, 403, 404, 409.
        """
        client = await self.get_http_client()
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    headers=self._headers(),
                )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < max_retries:
                        backoff = (2 ** (attempt - 1)) + random.uniform(0.1, 0.6)
                        logger.warning(
                            "FrenzyEx HTTP %s on %s %s (attempt %d/%d). Retrying in %.2fs...",
                            response.status_code, method, url, attempt, max_retries, backoff
                        )
                        await asyncio.sleep(backoff)
                        continue
                return response
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < max_retries:
                    backoff = (2 ** (attempt - 1)) + random.uniform(0.1, 0.6)
                    logger.warning(
                        "FrenzyEx network error on %s %s (attempt %d/%d): %s. Retrying in %.2fs...",
                        method, url, attempt, max_retries, exc, backoff
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise

        if last_exc:
            raise last_exc
        raise RuntimeError("Unreachable retry state")

    async def create_payment(
        self,
        order_id: str,
        amount: int | float,
        callback_url: str,
        amount_ccy: str = "TMN",
        description: str = "",
        payment_method: str = "auto",
        usd_rate_toman: Optional[int | float] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Creates a new Payment Request via POST /api/v1/payment-requests."""
        if not order_id or not str(order_id).strip():
            return {"success": False, "error_code": "INVALID_ORDER_REF", "error": "order_ref is required."}

        if amount is None or float(amount) <= 0:
            return {"success": False, "error_code": "INVALID_AMOUNT", "error": "amount must be greater than zero."}

        ccy = (amount_ccy or "TMN").upper().strip()
        if ccy not in self.ALLOWED_CURRENCIES:
            return {"success": False, "error_code": "INVALID_CCY", "error": f"Unsupported currency: {ccy}"}

        method = (payment_method or "auto").lower().strip()
        if method not in self.ALLOWED_METHODS:
            return {"success": False, "error_code": "INVALID_METHOD", "error": f"Unsupported method: {method}"}

        try:
            valid_callback = self.validate_callback_url(callback_url)
        except ValueError as ve:
            logger.error("FrenzyEx callback_url validation failed: %s", ve)
            return {"success": False, "error_code": "INVALID_CALLBACK_URL", "error": str(ve)}

        payload: dict[str, Any] = {
            "amount": int(amount) if ccy == "TMN" else float(amount),
            "amount_ccy": ccy,
            "order_ref": str(order_id).strip(),
            "description": (description or "").strip(),
            "payment_method": method,
            "callback_url": valid_callback,
        }
        if usd_rate_toman is not None and float(usd_rate_toman) > 0:
            payload["usd_rate_toman"] = float(usd_rate_toman)

        url = f"{self.base_url}/api/v1/payment-requests"
        try:
            response = await self._request_with_retry("POST", url, json_payload=payload)
            if 200 <= response.status_code < 300:
                data = response.json()
                return {
                    "success": True,
                    "request_id": data.get("request_id"),
                    "status": data.get("status", "pending"),
                    "asset": data.get("asset", "TRX"),
                    "amount": data.get("amount"),
                    "amount_ccy": data.get("amount_ccy"),
                    "order_ref": data.get("order_ref"),
                    "quote_trx": data.get("quote_trx"),
                    "quote_toman": data.get("quote_toman"),
                    "created_at": data.get("created_at"),
                    "expires_at": data.get("expires_at"),
                    "payment_url_web": data.get("checkout_url") or data.get("mini_app_url"),
                    "payment_url_bot": data.get("bot_pay_url") or data.get("pay_url"),
                    "pay_url": data.get("pay_url"),
                }

            logger.error(
                "FrenzyEx create_payment failed | status=%d | order_ref=%s | body=%s",
                response.status_code, order_id, response.text[:300]
            )
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }
        except Exception as exc:
            logger.error("FrenzyEx create_payment exception for order %s: %s", order_id, exc)
            return {"success": False, "error": "خطا در برقراری ارتباط با درگاه پرداخت."}

    async def get_payment_status(self, request_id: str) -> dict[str, Any]:
        """Retrieves full payment status and reconciliation metadata via GET /api/v1/payment-requests/{request_id}."""
        if not request_id or not str(request_id).strip():
            return {"success": False, "error": "request_id is empty"}

        url = f"{self.base_url}/api/v1/payment-requests/{request_id.strip()}"
        try:
            response = await self._request_with_retry("GET", url, max_retries=2)
            if 200 <= response.status_code < 300:
                data = response.json()
                return {
                    "success": True,
                    "request_id": data.get("request_id"),
                    "status": data.get("status"),  # pending, paid, expired, canceled
                    "amount": data.get("amount"),
                    "amount_ccy": data.get("amount_ccy"),
                    "order_ref": data.get("order_ref"),
                    "quote_trx": data.get("quote_trx"),
                    "quote_toman": data.get("quote_toman"),
                    "tx_hash": data.get("tx_hash"),
                    "created_at": data.get("created_at"),
                    "expires_at": data.get("expires_at"),
                    "paid_at": data.get("paid_at"),
                }
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }
        except Exception as exc:
            logger.error("FrenzyEx get_payment_status error for %s: %s", request_id, exc)
            return {"success": False, "error": str(exc)}

    async def verify_payment(
        self,
        request_id: str,
        expected_amount: Optional[int | float] = None,
        expected_order_ref: Optional[str] = None,
        expected_ccy: str = "TMN",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verifies a payment request against expected internal invoice parameters."""
        res = await self.get_payment_status(request_id)
        if not res.get("success"):
            return res

        if expected_order_ref and str(res.get("order_ref")) != str(expected_order_ref):
            logger.critical(
                "FrenzyEx order_ref mismatch! expected=%s, got=%s (request_id=%s)",
                expected_order_ref, res.get("order_ref"), request_id
            )
            return {"success": False, "error": "Order reference mismatch"}

        if expected_amount is not None and res.get("amount") is not None:
            if int(float(res["amount"])) != int(float(expected_amount)):
                logger.critical(
                    "FrenzyEx amount mismatch! expected=%s, got=%s (request_id=%s)",
                    expected_amount, res.get("amount"), request_id
                )
                return {"success": False, "error": "Payment amount mismatch"}

        if expected_ccy and res.get("amount_ccy") and res["amount_ccy"].upper() != expected_ccy.upper():
            return {"success": False, "error": "Payment currency mismatch"}

        return res

    async def cancel_payment(self, request_id: str) -> dict[str, Any]:
        """
        Cancels an unpaid payment request via POST /api/v1/payment-requests/{request_id}/cancel.
        Follows Section 06 & 10: checks status first and handles HTTP 409 Conflict gracefully.
        """
        status_res = await self.get_payment_status(request_id)
        if not status_res.get("success"):
            return status_res

        current_status = status_res.get("status")
        if current_status in self.TERMINAL_STATUSES:
            return {
                "success": current_status == "canceled",
                "status": current_status,
                "already_terminal": True,
            }

        url = f"{self.base_url}/api/v1/payment-requests/{request_id.strip()}/cancel"
        try:
            response = await self._request_with_retry("POST", url, max_retries=2)
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "status": data.get("status", "canceled")}
            if response.status_code == 409:
                logger.info("FrenzyEx cancel conflict (409) for %s: already paid or under review.", request_id)
                latest = await self.get_payment_status(request_id)
                return {
                    "success": False,
                    "conflict": True,
                    "status": latest.get("status"),
                    "error": "Payment is already paid or under review.",
                }
            return {"success": False, "status_code": response.status_code, "error": f"HTTP {response.status_code}"}
        except httpx.HTTPError as exc:
            logger.error("FrenzyEx cancel_payment HTTP error for %s: %s", request_id, exc)
            return {"success": False, "error": str(exc)}