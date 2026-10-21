"""
payment/gateways.py
-------------------
Production-ready, async FrenzyEx Merchant API v1.0 client with connection pooling,
strict SSRF/URL validation, Decimal precision, Retry-After support, and safe error handling.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
import ipaddress
import logging
import random
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class PaymentGateway:
    """Base interface for online payment gateways."""

    async def create_payment(
        self,
        order_id: str,
        amount: int | float | Decimal,
        callback_url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def verify_payment(
        self,
        request_id: str,
        expected_amount: Optional[int | float | Decimal] = None,
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
    FORBIDDEN_HOSTS = {"localhost", "localhost.localdomain", "127.0.0.1", "0.0.0.0", "::1"}

    _shared_client: Optional[httpx.AsyncClient] = None
    _client_lock = asyncio.Lock()

    def __init__(self, api_key: str, base_url: str = "https://frenzy.fastsnap.info"):
        if not api_key or not api_key.strip():
            raise ValueError("FrenzyEx API key is required.")
        self.api_key = api_key.strip()
        self.base_url = self._validate_https_endpoint(base_url, field_name="base_url")

    @classmethod
    def _validate_https_endpoint(cls, url: str, field_name: str = "callback_url") -> str:
        """
        Validates URLs according to FrenzyEx Section 04 & 10:
        - Must be HTTPS
        - Must not point to loopback, link-local, unspecified, or private IP space
        """
        cleaned = (url or "").strip().rstrip("/") if field_name == "base_url" else (url or "").strip()
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"{field_name} must use https scheme and have a valid hostname.")

        host = parsed.hostname.lower().strip(".")
        if host in cls.FORBIDDEN_HOSTS or host.endswith((".local", ".internal", ".localhost")):
            raise ValueError(f"{field_name} must not point to a local or internal hostname.")

        try:
            ip = ipaddress.ip_address(host)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise ValueError(f"{field_name} must not point to a private or reserved IP address.")
        except ValueError as exc:
            if field_name in str(exc):
                raise
            # Host is a domain name, not an IP literal

        return cleaned

    @classmethod
    def validate_callback_url(cls, callback_url: str) -> str:
        return cls._validate_https_endpoint(callback_url, field_name="callback_url")

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
        async with cls._client_lock:
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
        retry_on_read_timeout: bool = True,
    ) -> httpx.Response:
        """
        Executes an HTTP request following Section 10 Retry Matrix:
        - Respects Retry-After header on HTTP 429.
        - Avoids blind duplicate POSTs on ReadTimeout when retry_on_read_timeout=False.
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
                        retry_after_hdr = response.headers.get("Retry-After")
                        if retry_after_hdr and retry_after_hdr.isdigit():
                            backoff = min(float(retry_after_hdr), 15.0) + random.uniform(0.1, 0.5)
                        else:
                            backoff = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                        logger.warning(
                            "FrenzyEx HTTP %s on %s %s (attempt %d/%d). Retrying in %.2fs...",
                            response.status_code, method, url, attempt, max_retries, backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                return response
            except httpx.ReadTimeout as exc:
                last_exc = exc
                if not retry_on_read_timeout or attempt >= max_retries:
                    raise
                backoff = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                logger.warning(
                    "FrenzyEx read timeout on %s %s (attempt %d/%d). Retrying in %.2fs...",
                    method, url, attempt, max_retries, backoff,
                )
                await asyncio.sleep(backoff)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < max_retries:
                    backoff = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                    logger.warning(
                        "FrenzyEx network error on %s %s (attempt %d/%d): %s. Retrying in %.2fs...",
                        method, url, attempt, max_retries, exc.__class__.__name__, backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise

        if last_exc:
            raise last_exc
        raise RuntimeError("Unreachable retry state")

    @staticmethod
    def _parse_decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError):
            return None

    async def create_payment(
        self,
        order_id: str,
        amount: int | float | Decimal,
        callback_url: str,
        amount_ccy: str = "TMN",
        description: str = "",
        payment_method: str = "auto",
        usd_rate_toman: Optional[int | float | Decimal] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Creates a new Payment Request via POST /api/v1/payment-requests."""
        if not order_id or not str(order_id).strip():
            return {"success": False, "error_code": "INVALID_ORDER_REF", "error": "order_ref is required."}

        dec_amount = self._parse_decimal(amount)
        if dec_amount is None or dec_amount <= Decimal("0"):
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
            "amount": int(dec_amount) if ccy == "TMN" else float(dec_amount),
            "amount_ccy": ccy,
            "order_ref": str(order_id).strip(),
            "description": (description or "").strip(),
            "payment_method": method,
            "callback_url": valid_callback,
        }
        if usd_rate_toman is not None:
            dec_rate = self._parse_decimal(usd_rate_toman)
            if dec_rate and dec_rate > Decimal("0"):
                payload["usd_rate_toman"] = float(dec_rate)

        url = f"{self.base_url}/api/v1/payment-requests"
        try:
            # Do not retry POST on ReadTimeout because v1 create has no Idempotency-Key header
            response = await self._request_with_retry(
                "POST", url, json_payload=payload, max_retries=2, retry_on_read_timeout=False
            )
            if 200 <= response.status_code < 300:
                data = response.json()
                if not isinstance(data, dict) or not data.get("request_id"):
                    return {"success": False, "error": "Invalid response schema from gateway."}
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
                "FrenzyEx create_payment failed | status=%d | order_ref=%s",
                response.status_code, order_id,
            )
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }
        except Exception as exc:
            logger.error("FrenzyEx create_payment exception for order %s: %s", order_id, exc.__class__.__name__)
            return {"success": False, "error": "خطا در برقراری ارتباط با درگاه پرداخت."}

    async def get_payment_status(self, request_id: str) -> dict[str, Any]:
        """Retrieves payment status and reconciliation metadata via GET /api/v1/payment-requests/{request_id}."""
        if not request_id or not str(request_id).strip():
            return {"success": False, "error": "request_id is empty"}

        url = f"{self.base_url}/api/v1/payment-requests/{request_id.strip()}"
        try:
            response = await self._request_with_retry("GET", url, max_retries=2)
            if 200 <= response.status_code < 300:
                data = response.json()
                if not isinstance(data, dict):
                    return {"success": False, "error": "Malformed JSON response"}
                return {
                    "success": True,
                    "request_id": data.get("request_id"),
                    "status": data.get("status"),
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
            logger.error("FrenzyEx get_payment_status error for %s: %s", request_id, exc.__class__.__name__)
            return {"success": False, "error": str(exc)}

    async def verify_payment(
        self,
        request_id: str,
        expected_amount: Optional[int | float | Decimal] = None,
        expected_order_ref: Optional[str] = None,
        expected_ccy: str = "TMN",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verifies a payment request against expected internal invoice parameters using exact Decimal comparison."""
        res = await self.get_payment_status(request_id)
        if not res.get("success"):
            return res

        if expected_order_ref and str(res.get("order_ref") or "").strip() != str(expected_order_ref).strip():
            logger.critical(
                "FrenzyEx order_ref mismatch! expected=%s, got=%s (request_id=%s)",
                expected_order_ref, res.get("order_ref"), request_id,
            )
            return {"success": False, "error": "Order reference mismatch"}

        if expected_ccy:
            remote_ccy = str(res.get("amount_ccy") or "").upper().strip()
            if remote_ccy != expected_ccy.upper().strip():
                logger.critical(
                    "FrenzyEx currency mismatch! expected=%s, got=%s (request_id=%s)",
                    expected_ccy, remote_ccy, request_id,
                )
                return {"success": False, "error": "Payment currency mismatch"}

        if expected_amount is not None:
            got_dec = self._parse_decimal(res.get("amount"))
            exp_dec = self._parse_decimal(expected_amount)
            if got_dec is None or exp_dec is None or got_dec != exp_dec:
                logger.critical(
                    "FrenzyEx amount mismatch! expected=%s, got=%s (request_id=%s)",
                    expected_amount, res.get("amount"), request_id,
                )
                return {"success": False, "error": "Payment amount mismatch"}

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
            response = await self._request_with_retry("POST", url, max_retries=1, retry_on_read_timeout=False)
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
        except Exception as exc:
            logger.error("FrenzyEx cancel_payment error for %s: %s", request_id, exc.__class__.__name__)
            return {"success": False, "error": str(exc)}