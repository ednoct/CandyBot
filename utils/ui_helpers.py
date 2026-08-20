"""
ui_helpers.py
-------------
Module containing UI utility helpers for CandyBot, including
the Telegram Premium emoji substitution system.
"""

# === PREMIUM EMOJI MAP ===
# Maps standard emoji characters to their Telegram Premium Emoji IDs.
# These IDs are used to render animated Lottie stickers in-line within
# message text via the <tg-emoji> HTML tag.
PREMIUM_EMOJI_MAP = {
    '💰': 6025976946083500432,  # Wallet
    '🌀': 5370715282044100355,  # Renew
    '⭐': 5429623880949970643,  # Purchase
    '🤝': 5370715282044100355,  # Affiliate/Invite
    '🔗': 5271604874419647061,  # Subscriptions
    '📢': 5900108844960322391,  # News
    '❓': 5436113877181941026,  # FAQ
    '❔': 6024053298951098659,  # Tutorials
    '📥': 5443127283898405358,  # Download
    '💬': 6026239948405870716,  # Support
    '🆓': 5406756500108501710,  # Free Trial
    '✍️': 5258500400918587241,  # Terms
}


def apply_premium_emojis(text: str) -> str:
    """
    Scans the text and replaces mapped standard emojis with
    premium <tg-emoji> tags for Telegram's animated emoji rendering.

    NOTE: Only apply this to message body text — NEVER to
    InlineKeyboardButton labels, as Telegram's Bot API rejects HTML
    in button text fields.
    """
    for emoji_char, emoji_id in PREMIUM_EMOJI_MAP.items():
        if emoji_id:
            tg_emoji_tag = f'<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji>'
            text = text.replace(emoji_char, tg_emoji_tag)
    return text
