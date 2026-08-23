"""
broadcast.py
------------
Module containing functionalities for broadcast.
"""
# === IMPORTS ===
import asyncio
import logging
from database import db_manager

# === BROADCAST SERVICE ===
class BroadcastService:
    """
    Handles background processing of broadcast queues and notifications.
    Replaces legacy sendmessage.php and NoticationsService.php.
    """
    def __init__(self, bot):
        self.bot = bot
        
    async def process_queue(self):
        """
        Fetches pending messages from the database and sends them.
        """
        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                # Example queue processing logic for the future broadcast table
                async with db.execute("SELECT * FROM broadcast_queue WHERE status = 'pending' LIMIT 10") as cursor:
                    messages = await cursor.fetchall()
                for msg in messages:
                    # Mark as processing
                    await db.execute("UPDATE broadcast_queue SET status = 'processing' WHERE id = ?", (msg['id'],))
                    await db.commit()
                    
                    success = await self.send_notification(msg['user_id'], msg['message_text'])
                    
                    # Mark complete or failed
                    final_status = 'completed' if success else 'failed'
                    await db.execute("UPDATE broadcast_queue SET status = ? WHERE id = ?", (final_status, msg['id']))
                    await db.commit()
        except Exception as e:
            logging.error(f"Broadcast processing error: {e}")

    async def send_notification(self, user_id: int, message: str, markup=None):
        """
        Directly send a notification to a specific user.
        """
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=markup,
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logging.error(f"Failed to send notification to {user_id}: {e}")
            return False

async def safe_broadcast(bot, admin_id: int, user_ids: list, message_id: int, from_chat_id: int, is_forward: bool, pin_message: bool = False):
    """
    Broadcasts a message safely to a list of users.
    Handles rate limiting (max 30 msgs/sec), blocks, and errors.
    """
    from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramAPIError
    import time
    import asyncio
    
    total = len(user_ids)
    success = 0
    fail = 0
    
    start_time = time.time()
    
    # Send starting message to admin
    await bot.send_message(admin_id, f"🚀 ارسال همگانی به {total} کاربر آغاز شد...")
    
    for row in user_ids:
        # Depending on if we passed a list of rows or a list of ints
        user_id = row['id'] if hasattr(row, '__getitem__') else row
        
        try:
            if is_forward:
                msg = await bot.forward_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
            else:
                msg = await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
                
            if pin_message and msg:
                try:
                    await bot.pin_chat_message(chat_id=user_id, message_id=msg.message_id)
                except Exception as e:
                    logging.warning(f"Could not pin message for user {user_id}: {e}")
                    
            success += 1
            
        except TelegramRetryAfter as e:
            logging.error(f"Rate limit exceeded! Sleeping for {e.retry_after} seconds.")
            await asyncio.sleep(e.retry_after)
            # Retry this specific user
            try:
                if is_forward:
                    msg = await bot.forward_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
                else:
                    msg = await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
                if pin_message and msg:
                    await bot.pin_chat_message(chat_id=user_id, message_id=msg.message_id)
                success += 1
            except:
                fail += 1
                
        except TelegramForbiddenError:
            logging.warning(f"User {user_id} blocked the bot. Disabling user in DB.")
            from database import db_manager
            await db_manager.disable_user(user_id)
            fail += 1
            
        except TelegramAPIError as e:
            logging.error(f"Failed to send to {user_id}: {e}")
            fail += 1
            
        except Exception as e:
            logging.error(f"Unexpected error when sending to {user_id}: {e}")
            fail += 1
            
        # Ensure we don't hit the 30 msgs/sec limit (30 messages per second = ~0.034s per msg). 
        # Using 0.05 is safe (20 msgs/sec).
        await asyncio.sleep(0.05)
        
    end_time = time.time()
    duration = round(end_time - start_time, 2)
    
    report = (
        f"✅ **گزارش ارسال همگانی**\n\n"
        f"📊 تعداد کل هدف: `{total}`\n"
        f"🟢 ارسال موفق: `{success}`\n"
        f"🔴 ارسال ناموفق (یا بلاک): `{fail}`\n"
        f"⏱ زمان صرف شده: `{duration}` ثانیه"
    )
    
    await bot.send_message(admin_id, report, parse_mode="Markdown")
