"""
force_join.py
-------------
Middleware to ensure users join required channels before interacting with the bot.
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import ADMIN_IDS
from bot.services.channel_service import get_unjoined_channels, build_force_join_markup

class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)

        # Ignore force-join checks in group/supergroup chats (e.g. reports group)
        chat = getattr(event, "chat", None) or (getattr(event, "message", None) and getattr(event.message, "chat", None))
        if chat and getattr(chat, "type", None) in ["group", "supergroup"]:
            return await handler(event, data)

        bot = data.get("bot")
        if not bot:
            return await handler(event, data)

        # Allow confirm_channel callback so it can verify membership
        if isinstance(event, CallbackQuery) and event.data == "confirm_channel":
            return await handler(event, data)

        # If it's /start command message, let cmd_start run (it handles user creation/referrals, then enforces join)
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        unjoined = await get_unjoined_channels(bot, user.id)
        if unjoined:
            text, markup = build_force_join_markup(unjoined)
            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ لطفاً ابتدا در کانال‌های زیر عضو شوید.", show_alert=True)
                try:
                    await event.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
                except Exception:
                    pass
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=markup, parse_mode="HTML")
            return

        return await handler(event, data)
