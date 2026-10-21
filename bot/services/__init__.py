"""
bot/services/__init__.py
------------------------
Exports core service classes and helper functions for CandyBot.
"""
from .broadcast import BroadcastService
from .channel_service import (
    ChannelService,
    get_force_join_channels,
    extract_chat_id,
    check_user_membership,
    get_unjoined_channels,
    build_force_join_markup,
    invalidate_user_membership_cache,
    invalidate_channels_cache,
)
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
    "get_force_join_channels",
    "extract_chat_id",
    "check_user_membership",
    "get_unjoined_channels",
    "build_force_join_markup",
    "invalidate_user_membership_cache",
    "invalidate_channels_cache",
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