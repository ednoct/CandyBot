"""
notifications.py
----------------
Module containing the Centralized Notification Service for CandyBot.
"""
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_manager

class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_report(
        self,
        topic_key: str,
        text: str,
        user_id: int = None,
        file=None,
        caption=None,
        reply_markup=None
    ) -> bool:
        """
        Sends a report to the designated report supergroup topic.
        If reply_markup is provided, uses it.
        Otherwise if user_id is provided, includes a deep-link button for user management.
        If file is provided (e.g. for nightly backup), it sends the document instead of just text.
        Returns True if sent successfully, False otherwise.
        """
        report_group_id = await db_manager.get_report_setting("report_group_id")
        thread_id = await db_manager.get_report_setting(topic_key)

        if not report_group_id:
            logging.warning(f"NotificationService: report_group_id not set. Cannot send to {topic_key}.")
            return False

        keyboard = reply_markup
        if hasattr(keyboard, "as_markup"):
            keyboard = keyboard.as_markup()

        if keyboard is None and user_id:
            try:
                me = await self.bot.get_me()
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="👤 مدیریت کاربر",
                            url=f"https://t.me/{me.username}?start=manage_{user_id}"
                        )
                    ]]
                )
            except Exception as e:
                logging.error(f"NotificationService: Failed to get bot username: {e}")

        send_kwargs = {
            "chat_id": report_group_id,
            "reply_markup": keyboard,
            "parse_mode": "HTML"
        }
        if thread_id:
            send_kwargs["message_thread_id"] = thread_id

        try:
            if file:
                # If file is a string (path) or bytes, aiogram handles it based on how we pass it,
                # but typically we pass types.FSInputFile or BufferedInputFile.
                await self.bot.send_document(
                    document=file,
                    caption=caption or text,
                    **send_kwargs
                )
            else:
                await self.bot.send_message(
                    text=text,
                    **send_kwargs
                )
            return True
        except TelegramAPIError as e:
            err_str = str(e).lower()
            # If thread not found, retry in general chat
            if "thread not found" in err_str or "message thread not found" in err_str:
                send_kwargs.pop("message_thread_id", None)
                try:
                    if file:
                        await self.bot.send_document(document=file, caption=caption or text, **send_kwargs)
                    else:
                        await self.bot.send_message(text=text, **send_kwargs)
                    return True
                except Exception as retry_e:
                    logging.error(f"NotificationService: Retry without thread_id failed: {retry_e}")

            # If HTML parsing failed, retry without parse_mode
            if "can't parse entities" in err_str or "tag" in err_str:
                send_kwargs.pop("parse_mode", None)
                try:
                    if file:
                        await self.bot.send_document(document=file, caption=caption or text, **send_kwargs)
                    else:
                        await self.bot.send_message(text=text, **send_kwargs)
                    return True
                except Exception as retry_e:
                    logging.error(f"NotificationService: Retry without parse_mode failed: {retry_e}")

            logging.error(f"NotificationService: Telegram API Error when sending to {topic_key}: {e}")
            return False
        except Exception as e:
            logging.error(f"NotificationService: Unknown Error when sending to {topic_key}: {e}")
            return False
