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
