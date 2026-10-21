"""
bot/services/xui_client.py
--------------------------
Async HTTP client for communicating with the 3x-UI / Sanaei panel API.
Handles provisioning, renewing, migrating, and deleting clients across inbounds.
Patched for BUG-01 (top-level delete_client export) and BUG-02 (dual-signature provision method).
"""
from __future__ import annotations

import json
import logging
import secrets
import string
import time
import uuid
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


def _gen_sub_id(length: int = 16) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_client_email(license_note: str, user_id: int | str, invoice_id: str) -> str:
    """Builds a deterministic, collision-free client email identifier for 3x-UI."""
    clean_inv = "".join(ch for ch in str(invoice_id) if ch.isalnum() or ch in ("-", "_"))[:24]
    clean_note = "".join(ch for ch in str(license_note or "") if ch.isalnum() or ch in ("-", "_"))[:16]
    if clean_note:
        return f"{clean_note}_{user_id}_{clean_inv}"
    return f"u{user_id}_{clean_inv}"


def parse_inbound_ids(raw_inbound_ids: Any) -> list[int]:
    """Safely parses comma-separated inbound IDs into a validated list of integers."""
    if isinstance(raw_inbound_ids, list):
        return [int(x) for x in raw_inbound_ids if str(x).strip().isdigit()]
    raw_str = str(raw_inbound_ids or "")
    return [int(x.strip()) for x in raw_str.split(",") if x.strip().isdigit()]


class XUIClient:
    """Async client for interacting with 3x-UI / Sanaei panels."""

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 15.0):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.bearer_token = (bearer_token or "").strip()
        self.timeout = httpx.Timeout(timeout, connect=5.0)
        self._cookies: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.bearer_token:
            if ":" in self.bearer_token and not self.bearer_token.lower().startswith("bearer "):
                # Supports username:password or raw token alongside Bearer header
                headers["Authorization"] = f"Bearer {self.bearer_token}"
            else:
                token_val = self.bearer_token[7:].strip() if self.bearer_token.lower().startswith("bearer ") else self.bearer_token
                headers["Authorization"] = f"Bearer {token_val}"
        return headers

    async def _authenticate_if_needed(self, client: httpx.AsyncClient) -> None:
        """If bearer_token is formatted as 'username:password', logs into 3x-UI session cookie."""
        if ":" in self.bearer_token and " " not in self.bearer_token:
            username, password = self.bearer_token.split(":", 1)
            try:
                resp = await client.post(
                    f"{self.base_url}/login",
                    json={"username": username, "password": password},
                )
                if resp.status_code == 200:
                    self._cookies = dict(resp.cookies)
            except Exception as exc:
                logger.debug("XUI session login attempt skipped/failed: %s", exc)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
        ) as client:
            await self._authenticate_if_needed(client)
            resp = await client.request(
                method=method,
                url=url,
                json=json_payload,
                headers=self._headers(),
                cookies=self._cookies,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"XUI HTTP {resp.status_code} on {path}: {resp.text[:250]}")
            try:
                return resp.json()
            except Exception:
                return {"success": resp.status_code < 300, "raw": resp.text[:250]}

    async def list_inbounds(self) -> list[dict[str, Any]]:
        """Fetches all inbounds from the 3x-UI panel."""
        for endpoint in (
            "/panel/api/inbounds/list",
            "/xui/API/inbounds/",
            "/panel/inbound/list",
        ):
            try:
                data = await self._request("GET", endpoint)
                if isinstance(data, dict) and data.get("obj") is not None:
                    obj = data.get("obj")
                    if isinstance(obj, list):
                        return obj
            except Exception:
                continue
        return []

    async def provision(
        self,
        email: str = "",
        total_gb: Optional[float] = None,
        days: Optional[int] = None,
        tg_id: int | str = 0,
        limit_ip: Optional[int] = None,
        inbound_ids: Optional[list[int]] = None,
        group: str = "Customers",
        sub_id: Optional[str] = None,
        *,
        total_bytes: Optional[int] = None,
        expiry_time_ms: Optional[int] = None,
        ip_limit: Optional[int] = None,
        comment: str = "",
    ) -> str:
        """
        Provisions a client across all specified `inbound_ids` with the same `sub_id`.
        Supports BOTH parameter conventions (Fixes BUG-02):
        1. High-level: (email, total_gb, days, tg_id, limit_ip, inbound_ids, group, sub_id)
        2. Low-level:  (inbound_ids=..., email=..., sub_id=..., total_bytes=..., expiry_time_ms=..., ip_limit=..., comment=..., group=...)
        """
        parsed_inbounds = parse_inbound_ids(inbound_ids)
        if not parsed_inbounds:
            raise RuntimeError("لیست اینباندهای پنل (inbound_ids) خالی است.")

        final_sub_id = (sub_id or "").strip() or _gen_sub_id(16)
        final_ip_limit = int(ip_limit if ip_limit is not None else (limit_ip if limit_ip is not None else 1))

        if total_bytes is not None:
            final_total_bytes = max(0, int(total_bytes))
        elif total_gb is not None and float(total_gb) > 0:
            final_total_bytes = int(float(total_gb) * (1024 ** 3))
        else:
            final_total_bytes = 0  # 0 means Unlimited in 3x-UI

        if expiry_time_ms is not None:
            final_expiry_ms = max(0, int(expiry_time_ms))
        elif days is not None and int(days) > 0:
            final_expiry_ms = int((time.time() + int(days) * 86400) * 1000)
        else:
            final_expiry_ms = 0  # 0 means Unlimited time in 3x-UI

        last_error: Optional[Exception] = None
        success_count = 0

        for idx, inbound_id in enumerate(parsed_inbounds):
            client_email = email if idx == 0 else f"{email}_inb{inbound_id}"
            client_obj = {
                "id": str(uuid.uuid4()),
                "flow": "",
                "email": client_email,
                "limitIp": final_ip_limit,
                "totalGB": final_total_bytes,
                "expiryTime": final_expiry_ms,
                "enable": True,
                "tgId": str(tg_id or ""),
                "subId": final_sub_id,
                "comment": str(comment or group or ""),
                "reset": 0,
            }
            payload = {
                "id": int(inbound_id),
                "settings": json.dumps({"clients": [client_obj]}, ensure_ascii=False),
            }

            added = False
            for endpoint in (
                "/panel/api/inbounds/addClient",
                "/xui/API/inbounds/addClient",
                "/panel/inbound/addClient",
            ):
                try:
                    res = await self._request("POST", endpoint, json_payload=payload)
                    if isinstance(res, dict) and res.get("success") is False:
                        raise RuntimeError(str(res.get("msg") or "Failed to addClient"))
                    added = True
                    success_count += 1
                    break
                except Exception as exc:
                    last_error = exc

            if not added and last_error:
                logger.warning("Failed to add client %s to inbound %s: %s", client_email, inbound_id, last_error)

        if success_count == 0:
            raise RuntimeError(f"خطا در ساخت کلاینت روی پنل 3x-UI: {last_error}")

        return final_sub_id

    async def renew(
        self,
        email: str,
        add_days: int,
        add_gb: float,
        sub_id: Optional[str] = None,
    ) -> str:
        """
        Finds an existing client by `email` or `sub_id` across inbounds, adds `add_days` and `add_gb`
        (or sets to 0 if unlimited), resets used traffic if needed, and updates the client in-place.
        """
        inbounds = await self.list_inbounds()
        if not inbounds:
            raise RuntimeError("امکان دریافت لیست اینباندها از پنل وجود ندارد.")

        matched_clients: list[tuple[int, dict[str, Any]]] = []
        target_email = (email or "").strip().lower()
        target_sub = (sub_id or "").strip()

        for inb in inbounds:
            inb_id = inb.get("id")
            settings_raw = inb.get("settings")
            if not inb_id or not settings_raw:
                continue
            try:
                settings_obj = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
                clients = settings_obj.get("clients", [])
            except Exception:
                continue

            for cl in clients:
                cl_email = str(cl.get("email") or "").strip().lower()
                cl_sub = str(cl.get("subId") or "").strip()
                if (target_sub and cl_sub == target_sub) or (
                    target_email and (cl_email == target_email or cl_email.startswith(f"{target_email}_inb"))
                ):
                    matched_clients.append((int(inb_id), cl))

        if not matched_clients:
            raise RuntimeError("کلاینت مورد نظر در پنل فعلی یافت نشد.")

        now_ms = int(time.time() * 1000)
        resolved_sub_id = str(matched_clients[0][1].get("subId") or target_sub or _gen_sub_id(16))

        for inb_id, cl in matched_clients:
            client_uuid = cl.get("id") or cl.get("password") or cl.get("email")
            cl_email = cl.get("email")

            # Calculate remaining time and new expiry (Fixes BUG-02 for unlimited days=0)
            old_exp_ms = int(cl.get("expiryTime") or 0)
            if int(add_days) <= 0:
                new_exp_ms = 0  # Unlimited time
            else:
                base_ms = old_exp_ms if old_exp_ms > now_ms else now_ms
                new_exp_ms = base_ms + int(add_days) * 86400 * 1000

            # Calculate remaining traffic and new totalGB (Fixes BUG-02 for unlimited gb=0)
            old_total_bytes = int(cl.get("totalGB") or 0)
            if float(add_gb) <= 0:
                new_total_bytes = 0  # Unlimited traffic
            else:
                added_bytes = int(float(add_gb) * (1024 ** 3))
                new_total_bytes = (old_total_bytes + added_bytes) if old_total_bytes > 0 else added_bytes

            updated_client = dict(cl)
            updated_client["expiryTime"] = new_exp_ms
            updated_client["totalGB"] = new_total_bytes
            updated_client["enable"] = True
            updated_client["subId"] = resolved_sub_id

            payload = {
                "id": int(inb_id),
                "settings": json.dumps({"clients": [updated_client]}, ensure_ascii=False),
            }

            for endpoint in (
                f"/panel/api/inbounds/updateClient/{client_uuid}",
                f"/xui/API/inbounds/updateClient/{client_uuid}",
                f"/panel/inbound/updateClient/{client_uuid}",
            ):
                try:
                    res = await self._request("POST", endpoint, json_payload=payload)
                    if isinstance(res, dict) and res.get("success") is not False:
                        break
                except Exception:
                    continue

            # Reset client traffic on inbound if previously expired
            if old_exp_ms > 0 and old_exp_ms <= now_ms and cl_email:
                for reset_ep in (
                    f"/panel/api/inbounds/{inb_id}/resetClientTraffic/{cl_email}",
                    f"/xui/API/inbounds/{inb_id}/resetClientTraffic/{cl_email}",
                ):
                    try:
                        await self._request("POST", reset_ep)
                        break
                    except Exception:
                        continue

        return resolved_sub_id

    async def delete_client(self, email: str = "", sub_id: Optional[str] = None) -> bool:
        """
        Deletes a client from all inbounds on the 3x-UI panel matching `email` or `sub_id`.
        """
        inbounds = await self.list_inbounds()
        if not inbounds:
            return False

        target_email = (email or "").strip().lower()
        target_sub = (sub_id or "").strip()
        deleted_any = False

        for inb in inbounds:
            inb_id = inb.get("id")
            settings_raw = inb.get("settings")
            if not inb_id or not settings_raw:
                continue
            try:
                settings_obj = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
                clients = settings_obj.get("clients", [])
            except Exception:
                continue

            for cl in clients:
                cl_email = str(cl.get("email") or "").strip().lower()
                cl_sub = str(cl.get("subId") or "").strip()
                if (target_sub and cl_sub == target_sub) or (
                    target_email and (cl_email == target_email or cl_email.startswith(f"{target_email}_inb"))
                ):
                    client_uuid = cl.get("id") or cl.get("password") or cl.get("email")
                    for endpoint in (
                        f"/panel/api/inbounds/{inb_id}/delClient/{client_uuid}",
                        f"/xui/API/inbounds/{inb_id}/delClient/{client_uuid}",
                        f"/panel/inbound/{inb_id}/delClient/{client_uuid}",
                    ):
                        try:
                            res = await self._request("POST", endpoint)
                            if isinstance(res, dict) and res.get("success") is not False:
                                deleted_any = True
                                break
                        except Exception:
                            continue

        return deleted_any


# === MODULE-LEVEL CONVENIENCE FUNCTIONS ===
async def provision_license(
    panel: dict[str, Any],
    invoice: dict[str, Any],
    user_id: int,
    group: str = "Customers",
    sub_id: Optional[str] = None,
) -> str:
    """High-level helper to provision a license on a 3x-UI panel for an invoice."""
    inbound_ids = parse_inbound_ids(panel.get("inbound_ids"))
    if not inbound_ids:
        raise RuntimeError(f"هیچ اینباندی برای پنل {panel.get('name') or panel.get('id')} تنظیم نشده است.")

    note = str(invoice.get("license_note") or "")
    email = build_client_email(note, user_id, str(invoice.get("id") or ""))
    days = int(invoice.get("days") or 0)
    gb = float(invoice.get("gb") or 0.0)
    ip_limit = int(panel.get("ip_limit") or 1)

    client = XUIClient(panel["url"], panel["bearer_token"])
    return await client.provision(
        email=email,
        total_gb=gb,
        days=days,
        tg_id=user_id,
        limit_ip=ip_limit,
        inbound_ids=inbound_ids,
        group=group,
        sub_id=sub_id,
        comment=note,
    )


async def renew_license(
    panel: dict[str, Any],
    email: str,
    add_days: int,
    add_gb: float,
    sub_id: Optional[str] = None,
) -> str:
    """High-level helper to renew an existing client on a 3x-UI panel."""
    client = XUIClient(panel["url"], panel["bearer_token"])
    return await client.renew(email=email, add_days=add_days, add_gb=add_gb, sub_id=sub_id)


async def delete_client(
    panel: dict[str, Any],
    email: str = "",
    sub_id: Optional[str] = None,
) -> bool:
    """
    Top-level helper to delete a client from a 3x-UI panel by email and/or sub_id.
    Fixes BUG-01 across payment/confirm.py, database/db_manager.py, and bot/routers/user.py.
    """
    if not panel or not panel.get("url") or not panel.get("bearer_token"):
        return False
    client = XUIClient(panel["url"], panel["bearer_token"])
    return await client.delete_client(email=email, sub_id=sub_id)