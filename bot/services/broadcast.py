"""
broadcast.py
------------
Module containing functionalities for broadcast.
"""
# === IMPORTS ===
import asyncio
import logging
import aiosqlite
from database import db_manager
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

START_BUTTON_MARKUP = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="🟢 شروع و خرید از ربات", callback_data="start_from_notification", style="success")
]])

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
                    
                    success = await self.send_notification(msg['user_id'], msg['message_text'], markup=START_BUTTON_MARKUP)
                    
                    # Mark complete or failed
                    final_status = 'completed' if success else 'failed'
                    await db.execute("UPDATE broadcast_queue SET status = ? WHERE id = ?", (final_status, msg['id']))
                    await db.commit()
        except Exception as e:
            logging.error(f"Broadcast processing error: {e}")

    async def send_notification(self, user_id: int, message: str, markup=None):
        """
        Directly send a notification to a specific user with interactive start button.
        """
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=markup or START_BUTTON_MARKUP,
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
                try:
                    await bot.send_message(chat_id=user_id, text="👇 جهت ورود به منوی اصلی و ثبت سفارش کلیک کنید:", reply_markup=START_BUTTON_MARKUP)
                except Exception:
                    pass
            else:
                msg = await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id, reply_markup=START_BUTTON_MARKUP)
                
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
                    try:
                        await bot.send_message(chat_id=user_id, text="👇 جهت ورود به منوی اصلی و ثبت سفارش کلیک کنید:", reply_markup=START_BUTTON_MARKUP)
                    except Exception:
                        pass
                else:
                    msg = await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id, reply_markup=START_BUTTON_MARKUP)
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


async def safe_post_broadcast(
    bot,
    admin_id: int,
    media_type: str | None,
    file_id: str | None,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None,
    user_ids: list[int] | None = None,
    channel_targets: list[dict] | None = None,
    group_targets: list[dict] | None = None,
    target_description: str = "پست سفارشی"
):
    """
    Safely broadcasts a post (photo, video, or text with styled button)
    to users, channels, and groups.
    """
    from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramAPIError
    import time
    import asyncio
    
    start_time = time.time()
    
    user_ids = user_ids or []
    channel_targets = channel_targets or []
    group_targets = group_targets or []
    
    total_users = len(user_ids)
    total_channels = len(channel_targets)
    total_groups = len(group_targets)
    
    status_msg = f"🚀 **فرآیند ارسال {target_description} آغاز شد...**\n"
    if total_users:
        status_msg += f"👤 پیوی کاربران: {total_users}\n"
    if total_channels:
        status_msg += f"📢 کانال‌ها: {total_channels}\n"
    if total_groups:
        status_msg += f"👥 گروه‌ها: {total_groups}\n"
        
    await bot.send_message(admin_id, status_msg, parse_mode="Markdown")
    
    async def _send_single(chat_id: int | str):
        if media_type == "photo":
            return await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        elif media_type == "video":
            return await bot.send_video(
                chat_id=chat_id,
                video=file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            return await bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
    # 1. Send to Channels
    chan_success = 0
    chan_fail = 0
    chan_details = []
    for ch in channel_targets:
        cid = ch.get("id") or ch.get("link")
        cname = ch.get("remark") or ch.get("name") or str(cid)
        try:
            await _send_single(cid)
            chan_success += 1
            chan_details.append(f"🟢 {cname}: موفق")
        except Exception as e:
            logging.error(f"Failed to send post to channel {cid}: {e}")
            chan_fail += 1
            chan_details.append(f"🔴 {cname}: خطا ({str(e)[:30]})")
        await asyncio.sleep(0.1)
        
    # 2. Send to Groups
    group_success = 0
    group_fail = 0
    group_details = []
    for gr in group_targets:
        gid = gr.get("id")
        gname = gr.get("name") or str(gid)
        try:
            await _send_single(gid)
            group_success += 1
            group_details.append(f"🟢 {gname}: موفق")
        except Exception as e:
            logging.error(f"Failed to send post to group {gid}: {e}")
            group_fail += 1
            group_details.append(f"🔴 {gname}: خطا ({str(e)[:30]})")
        await asyncio.sleep(0.1)
        
    # 3. Send to Users (PV)
    user_success = 0
    user_fail = 0
    for uid in user_ids:
        try:
            await _send_single(uid)
            user_success += 1
        except TelegramRetryAfter as e:
            logging.warning(f"Rate limit hit during post broadcast, sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await _send_single(uid)
                user_success += 1
            except Exception:
                user_fail += 1
        except TelegramForbiddenError:
            from database import db_manager
            await db_manager.disable_user(uid)
            user_fail += 1
        except Exception as e:
            logging.error(f"Error sending post to user {uid}: {e}")
            user_fail += 1
            
        await asyncio.sleep(0.05)
        
    duration = round(time.time() - start_time, 2)
    
    report_lines = [
        f"✅ **گزارش ارسال {target_description}**\n",
        f"⏱ زمان کل: `{duration}` ثانیه\n"
    ]
    if total_users > 0:
        report_lines.append(f"👤 **پیوی کاربران:**")
        report_lines.append(f"  • کل: `{total_users}`")
        report_lines.append(f"  • موفق: `{user_success}`")
        report_lines.append(f"  • ناموفق/بلاک: `{user_fail}`\n")
    if total_channels > 0:
        report_lines.append(f"📢 **کانال‌ها:**")
        report_lines.append(f"  • موفق: `{chan_success}`")
        report_lines.append(f"  • ناموفق: `{chan_fail}`")
        if chan_details:
            report_lines.extend([f"  {d}" for d in chan_details])
        report_lines.append("")
    if total_groups > 0:
        report_lines.append(f"👥 **گروه‌ها:**")
        report_lines.append(f"  • موفق: `{group_success}`")
        report_lines.append(f"  • ناموفق: `{group_fail}`")
        if group_details:
            report_lines.extend([f"  {d}" for d in group_details])
        report_lines.append("")
        
    await bot.send_message(admin_id, "\n".join(report_lines), parse_mode="Markdown")

