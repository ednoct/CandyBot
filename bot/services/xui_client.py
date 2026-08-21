"""
bot/services/xui_client.py
──────────────────────────
Async 3x-UI panel API client.

Translated from SpeedyBot's synchronous core.py helpers into
fully async httpx-based code compatible with the CandyBot aiogram 3.x
architecture.

Key public surface:
    XUIClient          — per-panel async HTTP client
    build_sub_url()    — construct the subscriber URL from sub_id
    provision_license  — top-level coroutine called by payment/confirm.py
    generate_qr_bytes  — QR code image as BytesIO (Pillow + qrcode)
"""

# === IMPORTS ===
from __future__ import annotations

import asyncio
import logging
import re
import time
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# QR CODE GENERATION (with graceful fallback if Pillow is unavailable)
# ---------------------------------------------------------------------------

def generate_qr_bytes(data: str) -> Optional[BytesIO]:
    """
    Generate a QR code PNG for `data` and return it as a BytesIO object.

    Returns None if either qrcode or Pillow is not installed,
    so callers can fall back to text-only delivery.
    """
    try:
        import qrcode
        from PIL import Image  # noqa: F401 — confirms Pillow is present

        qr = qrcode.QRCode(
            version=None,           # auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    except ImportError as e:
        logger.warning("QR generation unavailable (%s). Falling back to text delivery.", e)
        return None
    except Exception as e:
        logger.error("QR generation error: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def build_sub_url(panel_url: str, sub_id: str) -> str:
    """
    Build the subscription URL for a given panel and sub_id.
    3x-UI default subscription path: {panel_url}/sub/{sub_id}
    """
    base = panel_url.rstrip("/")
    encoded = quote(str(sub_id), safe="")
    return f"{base}/sub/{encoded}"


def _mask_token(token: str) -> str:
    """Return a safely masked version of a bearer token for log output."""
    if not token or len(token) < 8:
        return "****"
    return token[:4] + "..." + token[-4:]


# ---------------------------------------------------------------------------
# Email / client-name builder
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def build_client_email(license_note: str, user_id: int, invoice_id: str) -> str:
    """
    Produce a safe, unique 3x-UI email (client identifier) from user inputs.

    Format: {sanitized_note}-{user_id}-{invoice_id}
    If note is empty, uses "candy-{user_id}-{invoice_id}".
    """
    note = (license_note or "").strip()
    # Transliterate common Persian/Arabic characters to Latin approximation
    note = note.replace(" ", "-").replace("\u060c", "-").replace(",", "-")
    safe_note = _UNSAFE_RE.sub("", note)[:20]  # max 20 chars from note

    if safe_note:
        return f"{safe_note}-{user_id}-{invoice_id}"
    return f"candy-{user_id}-{invoice_id}"


# ---------------------------------------------------------------------------
# XUIClient
# ---------------------------------------------------------------------------

class XUIClient:
    """
    Async 3x-UI panel API client.

    Usage:
        async with XUIClient(url, token) as client:
            sub_id = await client.get_client_sub_id(email)

    Or use the convenience coroutine `provision_license()` at module level.
    """

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 20.0):
        """Handles   init  ."""
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # context-manager support
    async def __aenter__(self) -> "XUIClient":
        """Handles   aenter  ."""
        self._client = httpx.AsyncClient(
            headers=self._headers(),
            timeout=self.timeout,
            verify=True,  # always verify SSL in production
        )
        return self

    async def __aexit__(self, *_) -> None:
        """Handles   aexit  ."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # internal helpers
    def _headers(self) -> dict:
        """Handles  headers."""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, endpoint: str) -> str:
        """Handles  url."""
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    async def _get(self, endpoint: str) -> dict:
        """Handles  get."""
        assert self._client, "XUIClient must be used as async context manager"
        url = self._url(endpoint)
        try:
            r = await self._client.get(url)
            return self._parse(r, endpoint)
        except httpx.RequestError as e:
            raise RuntimeError(f"خطای ارتباط با پنل ({endpoint}): {e}") from e

    async def _post(self, endpoint: str, json: dict = None) -> dict:
        """Handles  post."""
        assert self._client, "XUIClient must be used as async context manager"
        url = self._url(endpoint)
        try:
            r = await self._client.post(url, json=json or {})
            return self._parse(r, endpoint)
        except httpx.RequestError as e:
            raise RuntimeError(f"خطای ارتباط با پنل ({endpoint}): {e}") from e

    @staticmethod
    def _parse(response: httpx.Response, endpoint: str) -> dict:
        """Handles  parse."""
        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code in (401, 403):
            raise RuntimeError(
                f"احراز هویت پنل رد شد (HTTP {response.status_code}). "
                f"XUI_BEARER_TOKEN را بررسی کنید. Endpoint: {endpoint}"
            )
        if response.status_code == 404:
            raise RuntimeError(
                f"مسیر API پیدا نشد (HTTP 404). "
                f"URL پنل و نسخه 3x-ui را بررسی کنید. Endpoint: {endpoint}"
            )
        if response.status_code >= 500:
            body = (response.text or "")[:300]
            raise RuntimeError(
                f"خطای داخلی پنل (HTTP {response.status_code}): {body}"
            )
        if not data.get("success"):
            msg = data.get("msg") or response.text[:200] or "پاسخ ناموفق"
            raise RuntimeError(f"پنل خطا برگرداند ({endpoint}): {msg}")

        return data

    # public API
    async def get_active_inbound_ids(self) -> list:
        """Return IDs of all enabled inbounds."""
        data = await self._get("panel/api/inbounds/list")
        inbounds = data.get("obj") or []
        ids = [int(ib["id"]) for ib in inbounds if ib.get("enable", True) and ib.get("id") is not None]
        if not ids:
            raise RuntimeError("هیچ Inbound فعالی در پنل پیدا نشد.")
        return ids

    async def get_client(self, email: str) -> dict:
        """Return the client object for `email`, or empty dict if not found."""
        encoded = quote(email, safe="")
        try:
            data = await self._get(f"panel/api/clients/get/{encoded}")
            return data.get("obj") or {}
        except RuntimeError as e:
            if "پیدا نشد" in str(e) or "404" in str(e) or "not found" in str(e).lower():
                return {}
            raise

    async def get_client_sub_id(self, email: str, client_data: dict = None) -> Optional[str]:
        """
        Return the subId for an existing client.
        Tries client_data first, then fetches traffic endpoint as fallback.
        """
        cd = client_data or {}
        sub_id = cd.get("subId") or cd.get("subid")
        if sub_id:
            return str(sub_id)

        # Fallback: traffic endpoint also carries subId
        encoded = quote(email, safe="")
        try:
            data = await self._get(f"panel/api/clients/traffic/{encoded}")
            obj = data.get("obj") or {}
            sub_id = obj.get("subId") or obj.get("subid")
            return str(sub_id) if sub_id else None
        except Exception:
            return None

    async def add_client(
        self,
        email: str,
        total_gb: float,
        days: int,
        tg_id: int,
        limit_ip: int,
        inbound_ids: list,
        group: str = "Customers",
    ) -> bool:
        """
        Create a new client on the panel.
        total_gb=0 means unlimited traffic.
        group: XUI client group name ("Customers" for paid, "Trial" for free test).
        """
        total_bytes = int(float(total_gb) * 1024 ** 3) if float(total_gb) > 0 else 0
        expiry_ms = int((time.time() + days * 86400) * 1000)

        payload = {
            "client": {
                "email": email,
                "totalGB": total_bytes,
                "expiryTime": expiry_ms,
                "tgId": int(tg_id),
                "limitIp": int(limit_ip),
                "enable": True,
                "group": group,
            },
            "inboundIds": inbound_ids,
        }
        await self._post("panel/api/clients/add", payload)
        return True

    async def update_client(self, email: str, changes: dict) -> bool:
        """Patch an existing client. `changes` are merged onto the current client object."""
        encoded = quote(email, safe="")
        # Fetch current state first
        current = await self.get_client(email)
        if not current:
            raise RuntimeError(f"کلاینت {email} برای ویرایش پیدا نشد.")

        payload = dict(current)
        payload.update(changes)
        # Strip read-only / non-payload keys
        for key in ("traffic", "inboundIds", "clientStats", "id"):
            payload.pop(key, None)

        await self._post(f"panel/api/clients/update/{encoded}", payload)
        return True

    async def reset_traffic(self, email: str) -> bool:
        """Reset the traffic counter for a client (used after renewal)."""
        encoded = quote(email, safe="")
        await self._post(f"panel/api/clients/resetTraffic/{encoded}")
        return True

    async def delete_client(self, email: str) -> bool:
        """Remove a client from the panel."""
        encoded = quote(email, safe="")
        await self._post(f"panel/api/clients/del/{encoded}?keepTraffic=0")
        return True

    # high-level provisioning
    async def provision(
        self,
        email: str,
        total_gb: float,
        days: int,
        tg_id: int,
        limit_ip: int,
        inbound_ids: list,
        group: str = "Customers",
    ) -> str:
        """
        Idempotent: create the client if it doesn't exist, then return its subId.
        group: "Customers" for paid plans, "Trial" for free tests.

        Raises RuntimeError if provisioning fails or no subId is available.
        """
        # Check for existing client first (idempotency)
        client_data = await self.get_client(email)

        if not client_data:
            await self.add_client(email, total_gb, days, tg_id, limit_ip, inbound_ids, group=group)
            # Brief pause for panel to register the new client
            await asyncio.sleep(1.2)
            client_data = await self.get_client(email)

        sub_id = await self.get_client_sub_id(email, client_data)
        if not sub_id:
            raise RuntimeError(
                f"کلاینت {email} ساخته شد اما پنل subId برنگرداند. "
                "اتصال و نسخه 3x-ui را بررسی کنید."
            )
        return sub_id

    async def renew(
        self,
        email: str,
        extra_days: int,
        total_gb: float,
        limit_ip: int,
    ) -> str:
        """
        Renew an existing client: extend expiry, update traffic limit, reset counter.
        Returns the sub_id (unchanged — same link, no re-delivery needed).
        """
        client_data = await self.get_client(email)
        if not client_data:
            raise RuntimeError(f"سرویس {email} برای تمدید در پنل پیدا نشد.")

        now_ms = int(time.time() * 1000)
        current_expiry = int(client_data.get("expiryTime") or 0)
        base = max(now_ms, current_expiry) if current_expiry else now_ms
        new_expiry = base + int(extra_days) * 86400 * 1000
        total_bytes = int(float(total_gb) * 1024 ** 3) if float(total_gb) > 0 else 0

        await self.update_client(email, {
            "expiryTime": new_expiry,
            "totalGB": total_bytes,
            "limitIp": int(limit_ip),
            "enable": True,
        })
        await self.reset_traffic(email)

        sub_id = await self.get_client_sub_id(email, client_data)
        if not sub_id:
            raise RuntimeError("تمدید انجام شد اما subId دریافت نشد.")
        return sub_id


# ---------------------------------------------------------------------------
# Module-level convenience coroutines (called from payment/confirm.py)
# ---------------------------------------------------------------------------

async def provision_license(panel_row, invoice_row, user_id: int, group: str = "Customers") -> str:
    """
    Top-level coroutine that provisions a 3x-UI license for a paid invoice.

    Parameters
    ----------
    panel_row   : aiosqlite.Row from `xui_panels` (url, bearer_token, inbound_ids, ip_limit)
    invoice_row : aiosqlite.Row from `invoices`   (id, days, gb, license_note)
    user_id     : Telegram user ID
    group       : XUI client group — "Customers" for paid plans, "Trial" for free tests

    Returns
    -------
    sub_id : str
    """
    panel_url = panel_row["url"]
    bearer_token = panel_row["bearer_token"]
    inbound_ids_str = panel_row["inbound_ids"] or ""
    ip_limit = int(panel_row["ip_limit"] or 1)

    # Parse the comma-separated inbound IDs stored by the admin
    inbound_ids = [int(x.strip()) for x in inbound_ids_str.split(",") if x.strip().isdigit()]
    if not inbound_ids:
        raise RuntimeError(
            "هیچ Inbound ID تعریف نشده برای این پنل. "
            "از بخش مدیریت ثنا آیدی اینباند را تنظیم کنید."
        )

    # Safe access — license_note may not exist in older rows
    try:
        license_note = invoice_row["license_note"] or ""
    except Exception:
        license_note = ""

    invoice_id = invoice_row["id"]
    days = int(invoice_row["days"] or 30)
    gb = float(invoice_row["gb"] or 0)

    email = build_client_email(license_note, user_id, invoice_id)

    logger.info(
        "Provisioning XUI license | panel=%s | email=%s | days=%d | gb=%.1f | inbounds=%s",
        panel_url, email, days, gb, inbound_ids,
    )

    async with XUIClient(panel_url, bearer_token) as client:
        sub_id = await client.provision(
            email=email,
            total_gb=gb,
            days=days,
            tg_id=user_id,
            limit_ip=ip_limit,
            inbound_ids=inbound_ids,
            group=group,
        )

    logger.info("License provisioned | email=%s | sub_id=%s | group=%s", email, sub_id, group)
    return sub_id


async def renew_license(panel_row, email: str, days: int, gb: float) -> str:
    """
    Renew an existing client on a panel. Returns the (unchanged) sub_id.
    """
    panel_url = panel_row["url"]
    bearer_token = panel_row["bearer_token"]
    ip_limit = int(panel_row["ip_limit"] or 1)

    async with XUIClient(panel_url, bearer_token) as client:
        sub_id = await client.renew(
            email=email,
            extra_days=days,
            total_gb=gb,
            limit_ip=ip_limit,
        )

    return sub_id
