"""
bot/services/xui_client.py
--------------------------
Async HTTP client for communicating with the 3x-UI (v3.10.2) / Sanaei panel API.
Handles provisioning, in-place renewal (with accurate remaining quota & traffic reset),
cross-panel migration, connection testing, QR generation, and client deletion.
"""
from __future__ import annotations

from io import BytesIO
import json
import logging
import secrets
import string
import time
import uuid
from typing import Any, Optional

import httpx
import qrcode

logger = logging.getLogger(__name__)


class _AwaitableBytesIO(BytesIO):
    """
    A BytesIO subclass that can be used BOTH synchronously (`buf = generate_qr_bytes(s)`)
    AND asynchronously (`buf = await generate_qr_bytes(s)`).
    Fixes BUG-02 without breaking any sync or async caller across the codebase.
    """

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()


def generate_qr_bytes(data: str) -> _AwaitableBytesIO:
    """
    Generates a PNG QR code image in memory for the given license key (`sub_id`) or string.
    Returns an `_AwaitableBytesIO` buffer supporting both sync and `await` usage (Fixes BUG-01 & BUG-02).
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(str(data or ""))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = _AwaitableBytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_sub_url(panel_url: Optional[str], sub_id: str) -> str:
    """
    Safely formats a subscription/license reference string.
    Handles None/empty `panel_url` gracefully without AttributeError (Fixes BUG-01, BUG-07 & BUG-09).
    """
    clean_sub = str(sub_id or "").strip()
    if not panel_url or not str(panel_url).strip():
        return clean_sub
    base = str(panel_url).strip().rstrip("/")
    if "/sub" in base:
        return f"{base}/{clean_sub}"
    return f"{base}/sub/{clean_sub}"


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
    """
    Async client for interacting with 3x-UI / Sanaei panels.
    Supports `async with XUIClient(...) as client:` context manager protocol (Fixes BUG-03).
    """

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 15.0):
        raw_url = (base_url or "").strip().rstrip("/")
        # Auto-normalize: strip trailing web UI suffixes like /panel, /panel/inbounds, /panel/setting
        for suffix in ("/panel/inbounds", "/panel/setting", "/panel/settings", "/panel"):
            if raw_url.endswith(suffix):
                raw_url = raw_url[:-len(suffix)].rstrip("/")
        self.base_url = raw_url
        self.bearer_token = (bearer_token or "").strip()
        self.timeout = httpx.Timeout(timeout, connect=5.0)
        self._cookies: dict[str, str] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._logged_in: bool = False

    async def __aenter__(self) -> "XUIClient":
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=False,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Closes the underlying httpx.AsyncClient if open."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._logged_in = False

    def _build_url(self, path: str) -> str:
        """Constructs an absolute URL, avoiding duplicated /panel path segments."""
        clean_path = "/" + path.lstrip("/")
        base = self.base_url.rstrip("/")
        if base.endswith("/panel") and clean_path.startswith("/panel/"):
            clean_path = clean_path[len("/panel"):]
        return f"{base}{clean_path}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.bearer_token:
            token_val = (
                self.bearer_token[7:].strip()
                if self.bearer_token.lower().startswith("bearer ")
                else self.bearer_token
            )
            headers["Authorization"] = f"Bearer {token_val}"
        return headers

    async def _authenticate_if_needed(self, client: httpx.AsyncClient) -> None:
        """If bearer_token is formatted as 'username:password', logs into 3x-UI session cookie."""
        if self._logged_in:
            return
        if ":" in self.bearer_token and " " not in self.bearer_token:
            username, password = self.bearer_token.split(":", 1)
            login_url = self._build_url("/login")
            # 1. Try form-encoded data (standard for 3x-UI Gin engine)
            try:
                resp = await client.post(
                    login_url,
                    data={"username": username, "password": password},
                )
                if resp.status_code == 200:
                    try:
                        res_json = resp.json()
                        if res_json.get("success") is False:
                            logger.warning("XUI form login failed: %s", res_json.get("msg"))
                        else:
                            self._cookies.update(dict(resp.cookies))
                            self._logged_in = True
                            return
                    except Exception:
                        self._cookies.update(dict(resp.cookies))
                        self._logged_in = True
                        return
            except Exception as exc:
                logger.debug("XUI form login error: %s", exc)

            # 2. Try JSON payload fallback
            try:
                resp = await client.post(
                    login_url,
                    json={"username": username, "password": password},
                )
                if resp.status_code == 200:
                    try:
                        res_json = resp.json()
                        if res_json.get("success") is False:
                            logger.warning("XUI JSON login failed: %s", res_json.get("msg"))
                        else:
                            self._cookies.update(dict(resp.cookies))
                            self._logged_in = True
                            return
                    except Exception:
                        self._cookies.update(dict(resp.cookies))
                        self._logged_in = True
                        return
            except Exception as exc:
                logger.debug("XUI JSON login error: %s", exc)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = self._build_url(path)
        if self._client is not None and not self._client.is_closed:
            await self._authenticate_if_needed(self._client)
            resp = await self._client.request(
                method=method,
                url=url,
                json=json_payload,
                headers=self._headers(),
                cookies=self._cookies,
            )
        else:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=False,
                follow_redirects=True,
            ) as temp_client:
                await self._authenticate_if_needed(temp_client)
                resp = await temp_client.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    headers=self._headers(),
                    cookies=self._cookies,
                )

        if resp.status_code >= 400:
            resp_detail = (resp.text or "").strip()[:250]
            raise RuntimeError(f"XUI HTTP {resp.status_code} on {path}: {resp_detail}")
        try:
            return resp.json()
        except Exception:
            return {"success": resp.status_code < 300, "raw": (resp.text or "")[:250]}

    async def list_inbounds(self) -> list[dict[str, Any]]:
        """Fetches all inbounds from the 3x-UI panel."""
        for endpoint in (
            "/panel/api/inbounds/list",
            "/api/inbounds/list",
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

    async def get_inbounds(self) -> list[dict[str, Any]]:
        """Alias for list_inbounds() required by admin_users.py (Fixes BUG-04)."""
        return await self.list_inbounds()

    async def test_connection(self) -> tuple[bool, str]:
        """
        Tests connectivity and authentication against the 3x-UI panel (Required by admin_xui.py).
        Returns (success_bool, status_message).
        """
        if not self.base_url:
            return False, "آدرس پنل خالی است."

        errors: list[str] = []
        for endpoint in (
            "/panel/api/inbounds/list",
            "/api/inbounds/list",
            "/xui/API/inbounds/",
            "/panel/inbound/list",
        ):
            try:
                data = await self._request("GET", endpoint)
                if isinstance(data, dict) and data.get("success") is True:
                    inbounds = data.get("obj") or []
                    count = len(inbounds) if isinstance(inbounds, list) else 0
                    inb_summary = []
                    if isinstance(inbounds, list):
                        for inb in inbounds[:5]:
                            inb_id = inb.get("id")
                            inb_proto = inb.get("protocol") or "unknown"
                            inb_port = inb.get("port") or "?"
                            inb_summary.append(f"ID {inb_id} ({inb_proto}:{inb_port})")
                    summary_str = f"\nاینباندهای فعال: {', '.join(inb_summary)}" if inb_summary else ""
                    return True, f"اتصال موفق ({count} اینباند دریافت شد).{summary_str}"
                elif isinstance(data, dict) and data.get("msg"):
                    errors.append(f"{endpoint}: {data.get('msg')}")
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")

        err_detail = " | ".join(errors[:2]) if errors else "عدم دریافت پاسخ معتبر."
        return False, f"خطا در برقراری ارتباط:\n{err_detail[:180]}"

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
        Supports both high-level (total_gb/days) and low-level (total_bytes/expiry_time_ms) signatures.
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

        endpoints = (
            "/panel/api/inbounds/addClient",
            "/api/inbounds/addClient",
            "/xui/API/inbounds/addClient",
            "/panel/inbound/addClient",
        )

        for idx, inbound_id in enumerate(parsed_inbounds):
            client_email = email if idx == 0 else f"{email}_inb{inbound_id}"
            client_uuid = str(uuid.uuid4())
            client_obj = {
                "id": client_uuid,
                "password": client_uuid,
                "flow": "",
                "email": client_email,
                "limitIp": final_ip_limit,
                "totalGB": final_total_bytes,
                "expiryTime": final_expiry_ms,
                "enable": True,
                "tgId": int(tg_id) if str(tg_id).isdigit() else str(tg_id or ""),
                "subId": final_sub_id,
                "comment": str(comment or ""),
                "group": str(group or "Customers"),
                "reset": 0,
            }
            payload = {
                "id": int(inbound_id),
                "settings": json.dumps({"clients": [client_obj]}, ensure_ascii=False),
            }

            added = False
            primary_error: Optional[Exception] = None
            attempt_errors: list[str] = []

            for ep_idx, endpoint in enumerate(endpoints):
                try:
                    res = await self._request("POST", endpoint, json_payload=payload)
                    if isinstance(res, dict) and res.get("success") is False:
                        raise RuntimeError(str(res.get("msg") or "Failed to addClient"))
                    added = True
                    success_count += 1
                    break
                except Exception as exc:
                    attempt_errors.append(f"{endpoint} -> {exc}")
                    if ep_idx == 0:
                        primary_error = exc
                    last_error = exc

            if not added:
                effective_err = primary_error or last_error
                last_error = effective_err
                logger.warning(
                    "Failed to add client %s to inbound %s. Attempted endpoints: %s",
                    client_email, inbound_id, " | ".join(attempt_errors)
                )

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
        Finds an existing client by `email` or `sub_id` across inbounds, calculates exact remaining
        traffic (using `clientStats` up+down) and remaining time, adds `add_gb` and `add_days`,
        resets client traffic counters in 3x-UI, and re-enables the client.
        """
        inbounds = await self.list_inbounds()
        if not inbounds:
            raise RuntimeError("امکان دریافت لیست اینباندها از پنل وجود ندارد.")

        matched_clients: list[tuple[int, dict[str, Any], int]] = []
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

            # Map per-email used traffic (up + down) from inbound's clientStats array in 3x-UI
            stats_by_email: dict[str, int] = {}
            for st in (inb.get("clientStats") or []):
                if isinstance(st, dict) and st.get("email"):
                    st_email = str(st["email"]).strip().lower()
                    used = max(0, int(st.get("up") or 0)) + max(0, int(st.get("down") or 0))
                    stats_by_email[st_email] = used

            for cl in clients:
                cl_email = str(cl.get("email") or "").strip()
                cl_email_low = cl_email.lower()
                cl_sub = str(cl.get("subId") or "").strip()
                if (target_sub and cl_sub == target_sub) or (
                    target_email and (cl_email_low == target_email or cl_email_low.startswith(f"{target_email}_inb"))
                ):
                    used_bytes = stats_by_email.get(cl_email_low, 0)
                    matched_clients.append((int(inb_id), cl, used_bytes))

        if not matched_clients:
            raise RuntimeError("کلاینت مورد نظر در پنل فعلی یافت نشد.")

        now_ms = int(time.time() * 1000)
        resolved_sub_id = str(matched_clients[0][1].get("subId") or target_sub or _gen_sub_id(16))

        # Aggregate total used bytes across all inbounds sharing this client/subId
        total_used_bytes = sum(used for _, _, used in matched_clients)

        for inb_id, cl, _ in matched_clients:
            client_uuid = cl.get("id") or cl.get("password") or cl.get("email")
            cl_email = str(cl.get("email") or "").strip()

            old_exp_ms = int(cl.get("expiryTime") or 0)
            old_total_bytes = int(cl.get("totalGB") or 0)

            was_time_expired = (old_exp_ms > 0 and old_exp_ms <= now_ms)
            was_traffic_expired = (old_total_bytes > 0 and total_used_bytes >= old_total_bytes)
            was_expired = was_time_expired or was_traffic_expired

            # 1. Calculate new expiryTime in ms (0 = unlimited)
            if int(add_days) <= 0 or (not was_expired and old_exp_ms == 0):
                new_exp_ms = 0
            else:
                base_ms = old_exp_ms if old_exp_ms > now_ms else now_ms
                new_exp_ms = base_ms + int(add_days) * 86400 * 1000

            # 2. Calculate new totalGB in bytes (0 = unlimited)
            # Since we reset client traffic to 0 upon renewal, new_total_bytes = remaining_bytes + added_bytes
            if float(add_gb) <= 0 or (not was_expired and old_total_bytes == 0):
                new_total_bytes = 0
            else:
                rem_bytes = max(0, old_total_bytes - total_used_bytes) if old_total_bytes > 0 else 0
                added_bytes = int(float(add_gb) * (1024 ** 3))
                new_total_bytes = rem_bytes + added_bytes

            updated_client = dict(cl)
            updated_client["expiryTime"] = new_exp_ms
            updated_client["totalGB"] = new_total_bytes
            updated_client["enable"] = True
            updated_client["subId"] = resolved_sub_id

            payload = {
                "id": int(inb_id),
                "settings": json.dumps({"clients": [updated_client]}, ensure_ascii=False),
            }

            updated_ok = False
            for endpoint in (
                f"/panel/api/inbounds/updateClient/{client_uuid}",
                f"/api/inbounds/updateClient/{client_uuid}",
                f"/xui/API/inbounds/updateClient/{client_uuid}",
                f"/panel/inbound/updateClient/{client_uuid}",
            ):
                try:
                    res = await self._request("POST", endpoint, json_payload=payload)
                    if isinstance(res, dict) and res.get("success") is not False:
                        updated_ok = True
                        break
                except Exception:
                    continue

            if not updated_ok:
                raise RuntimeError(f"خطا در بروزرسانی کلاینت {cl_email} روی اینباند {inb_id}")

            # 3. Reset client traffic counter on the inbound so up=0, down=0 matches new_total_bytes
            if cl_email:
                for reset_ep in (
                    f"/panel/api/inbounds/{inb_id}/resetClientTraffic/{cl_email}",
                    f"/xui/API/inbounds/{inb_id}/resetClientTraffic/{cl_email}",
                    f"/panel/inbound/{inb_id}/resetClientTraffic/{cl_email}",
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
        Supports both `delClient/{clientId}` and `delClientByEmail/{email}` from 3x-UI v3.10.2.
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
                cl_email_exact = str(cl.get("email") or "").strip()
                cl_email = cl_email_exact.lower()
                cl_sub = str(cl.get("subId") or "").strip()
                if (target_sub and cl_sub == target_sub) or (
                    target_email and (cl_email == target_email or cl_email.startswith(f"{target_email}_inb"))
                ):
                    client_uuid = cl.get("id") or cl.get("password") or cl_email_exact
                    for endpoint in (
                        f"/panel/api/inbounds/{inb_id}/delClient/{client_uuid}",
                        f"/panel/api/inbounds/{inb_id}/delClientByEmail/{cl_email_exact}",
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

    async with XUIClient(panel["url"], panel["bearer_token"]) as client:
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
    async with XUIClient(panel["url"], panel["bearer_token"]) as client:
        return await client.renew(email=email, add_days=add_days, add_gb=add_gb, sub_id=sub_id)


async def delete_client(
    panel: dict[str, Any],
    email: str = "",
    sub_id: Optional[str] = None,
) -> bool:
    """Top-level helper to delete a client from a 3x-UI panel by email and/or sub_id."""
    if not panel or not panel.get("url") or not panel.get("bearer_token"):
        return False
    async with XUIClient(panel["url"], panel["bearer_token"]) as client:
        return await client.delete_client(email=email, sub_id=sub_id)