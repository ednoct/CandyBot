"""
bot/services/__init__.py
------------------------
Exports core service classes and helper functions for CandyBot.
"""
from .broadcast import BroadcastService
from .channel_service import ChannelService
from .notifications import NotificationService
from .sub_stats import fetch_sub_stats
from .xui_client import (
    XUIClient,
    generate_qr_bytes,
    build_sub_url,
    build_client_email,
    provision_license,
    renew_license,
    delete_client,
)

__all__ = [
    "BroadcastService",
    "ChannelService",
    "NotificationService",
    "fetch_sub_stats",
    "XUIClient",
    "generate_qr_bytes",
    "build_sub_url",
    "build_client_email",
    "provision_license",
    "renew_license",
    "delete_client",
]