"""
bot/services/sub_stats.py
-------------------------
Service to fetch and parse subscription traffic & expiration stats from the 3x-UI sub-link.
Patched to expose `expire_ts` and `raw_days_left` so 2-day post-expiry cleanup works accurately.
"""
import time
import logging
import httpx
from typing import Optional, Dict, Any


async def fetch_sub_stats(sub_link_base: str, sub_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches subscription headers from `{sub_link_base}/{sub_id}` and parses `Subscription-Userinfo`.
    Returns a dict with traffic/time statistics or None if unreachable.
    """
    if not sub_link_base or not sub_id:
        return None

    base = sub_link_base.strip().rstrip("/")
    url = f"{base}/{sub_id.strip()}"

    try:
        async with httpx.AsyncClient(verify=False, timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "CandyConnect/1.0"})
            if resp.status_code != 200:
                return None

            userinfo = resp.headers.get("Subscription-Userinfo") or resp.headers.get("subscription-userinfo")
            if not userinfo:
                return None

            parts = {}
            for item in userinfo.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    try:
                        parts[k.strip().lower()] = int(float(v.strip()))
                    except ValueError:
                        pass

            upload = parts.get("upload", 0)
            download = parts.get("download", 0)
            total = parts.get("total", 0)
            expire = parts.get("expire", 0)

            used_bytes = max(0, upload) + max(0, download)
            used_gb = used_bytes / (1024 ** 3)

            if total <= 0:
                is_unlimited_traffic = True
                total_gb = 0.0
                remaining_gb = 0.0
                fraction = 1.0
                traffic_expired = False
            else:
                is_unlimited_traffic = False
                total_gb = total / (1024 ** 3)
                remaining_bytes = max(0, total - used_bytes)
                remaining_gb = remaining_bytes / (1024 ** 3)
                fraction = remaining_bytes / total if total > 0 else 0.0
                traffic_expired = remaining_bytes <= 0

            now = time.time()
            if expire <= 0:
                is_unlimited_time = True
                days_left = 0.0
                raw_days_left = 0.0
                time_expired = False
            else:
                is_unlimited_time = False
                diff = expire - now
                raw_days_left = diff / 86400.0
                if diff <= 0:
                    days_left = 0.0
                    time_expired = True
                else:
                    days_left = diff / 86400.0
                    time_expired = False

            is_expired = traffic_expired or time_expired

            return {
                "used_gb": used_gb,
                "total_gb": total_gb,
                "remaining_gb": remaining_gb,
                "fraction": fraction,
                "days_left": days_left,
                "raw_days_left": raw_days_left,
                "expire_ts": expire,
                "is_unlimited_traffic": is_unlimited_traffic,
                "is_unlimited_time": is_unlimited_time,
                "is_expired": is_expired,
            }
    except Exception as e:
        logging.debug(f"Failed to fetch sub stats from {url}: {e}")
        return None