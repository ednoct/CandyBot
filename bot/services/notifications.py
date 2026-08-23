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

    async def send_report(self, topic_key: str, text: str, user_id: int = None, file=None, caption=None):
        """
        Sends a report to the designated report supergroup topic.
        If user_id is provided, includes a deep-link button for user management.
        If file is provided (e.g. for nightly backup), it sends the document instead of just text.
        """
        report_group_id = await db_manager.get_report_setting("report_group_id")
        thread_id = await db_manager.get_report_setting(topic_key)

        if not report_group_id:
            logging.warning(f"NotificationService: report_group_id not set. Cannot send to {topic_key}.")
            return

        keyboard = None
        if user_id:
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

        try:
            if file:
                # If file is a string (path) or bytes, aiogram handles it based on how we pass it,
                # but typically we pass types.FSInputFile or BufferedInputFile.
                await self.bot.send_document(
                    chat_id=report_group_id,
                    message_thread_id=thread_id,
                    document=file,
                    caption=caption or text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await self.bot.send_message(
                    chat_id=report_group_id,
                    message_thread_id=thread_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except TelegramAPIError as e:
            logging.error(f"NotificationService: Telegram API Error when sending to {topic_key}: {e}")
        except Exception as e:
            logging.error(f"NotificationService: Unknown Error when sending to {topic_key}: {e}")
