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


# === BOTTOM-ANCHORED NAVIGATION (SEND-THEN-DELETE) ===
import logging
from typing import Union, Optional
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply

logger = logging.getLogger(__name__)

async def send_bottom_message(
    event: Union[types.CallbackQuery, types.Message],
    text: str,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]] = None,
    parse_mode: Optional[str] = "HTML",
    delete_prev: bool = True,
    **kwargs
) -> types.Message:
    """
    Standardized Bottom-Anchored Navigation (Send-Then-Delete pattern).
    Ensures that menus and messages are always sent at the bottom-most position
    in the chat history, while cleanly removing the previous message or disabling
    its inline keyboard if deletion is not possible (e.g. past 48h Telegram restriction).
    """
    if isinstance(event, types.CallbackQuery):
        # Acknowledge callback immediately to eliminate loading spinner
        try:
            await event.answer()
        except Exception:
            pass

        chat_id = event.message.chat.id if event.message else event.from_user.id
        bot = event.bot

        new_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            **kwargs
        )

        if delete_prev and event.message:
            try:
                await event.message.delete()
            except Exception as del_err:
                logger.debug(f"Could not delete previous message {event.message.message_id}: {del_err}")
                try:
                    await event.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass

        return new_msg

    elif isinstance(event, types.Message):
        delete_user_message = kwargs.pop("delete_user_message", False)
        new_msg = await event.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            **kwargs
        )

        # Do not delete incoming user message by default.
        # Only delete if message is from a bot or delete_user_message=True is explicitly specified.
        is_bot = bool(event.from_user and event.from_user.is_bot)
        if delete_prev and (is_bot or delete_user_message):
            try:
                await event.delete()
            except Exception as del_err:
                logger.debug(f"Could not delete message {event.message_id}: {del_err}")

        return new_msg

    else:
        raise TypeError(f"Unsupported event type: {type(event)}")


async def safe_edit_message(
    target: Union[types.CallbackQuery, types.Message],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    **kwargs
) -> Optional[types.Message]:
    """
    Safely edits a message without raising or spamming on TelegramBadRequest:
    - If Telegram reports 'message is not modified', silently ignores it and answers callback (no duplicate message!).
    - If the message cannot be edited (e.g. user message), gracefully falls back to answering with a new message.
    """
    msg = target.message if isinstance(target, types.CallbackQuery) else target
    cb = target if isinstance(target, types.CallbackQuery) else None

    if cb:
        try:
            await cb.answer()
        except Exception:
            pass

    try:
        if msg:
            return await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        err = str(e).lower()
        if "not modified" in err:
            # User clicked the already-selected button — ignore safely
            if cb:
                try:
                    await cb.answer()
                except Exception:
                    pass
            return None
        # Other errors (e.g., cannot edit user message) -> fallback to sending new message
        try:
            if msg:
                return await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
        except Exception as send_err:
            logger.debug(f"safe_edit_message fallback failed: {send_err}")
            return None
    return None

