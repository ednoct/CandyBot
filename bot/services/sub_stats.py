"""
bot/services/sub_stats.py
─────────────────────────
License stats extractor based on sub-link headers.
"""
import aiohttp
import time
import logging

logger = logging.getLogger(__name__)

async def fetch_sub_stats(sub_link: str, sub_id: str) -> dict | None:
    """
    Fetch subscription stats from the sub-link HTTP headers.
    Expects 'Subscription-Userinfo' header containing upload, download, total, and expire fields.
    Returns structured dict or None on failure.
    """
    if not sub_link or not sub_id:
        return None
        
    url = f"{sub_link.rstrip('/')}/{sub_id}"
    
    try:
        # We only need the headers, so a HEAD request is more efficient,
        # but some endpoints might not send headers on HEAD, so we use GET.
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                
                userinfo = response.headers.get('Subscription-Userinfo')
                if not userinfo:
                    return None
                    
                # Parse: upload=123; download=456; total=789; expire=1234567890
                parts = userinfo.split(';')
                data = {}
                for part in parts:
                    if '=' in part:
                        k, v = part.split('=', 1)
                        data[k.strip().lower()] = int(v.strip())
                        
                up = data.get('upload', 0)
                down = data.get('download', 0)
                total = data.get('total', 0)
                expire = data.get('expire', 0)
                
                total_gb = total / (1024**3) if total > 0 else 0
                used_gb = (up + down) / (1024**3)
                remaining_gb = max(0, total_gb - used_gb) if total > 0 else 0
                
                now = int(time.time())
                days_left = (expire - now) / 86400 if expire > 0 else 0
                
                fraction = remaining_gb / total_gb if total_gb > 0 else 1.0
                
                return {
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "remaining_gb": remaining_gb,
                    "fraction": fraction,
                    "days_left": max(0, days_left),
                    "is_expired": (expire > 0 and now > expire) or (total > 0 and (up + down) >= total),
                    "is_unlimited_traffic": total == 0,
                    "is_unlimited_time": expire == 0
                }
    except Exception as e:
        logger.error(f"Failed to fetch sub stats for {sub_id}: {e}")
        return None
