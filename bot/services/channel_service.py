"""
channel_service.py
------------------
Service for managing force join (جوین اجباری) channels and verifying user membership.
"""
import logging
from typing import List, Dict, Tuple, Optional
import aiosqlite
from aiogram import Bot, types
from aiogram.enums import ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_manager import DB_PATH
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def get_force_join_channels() -> List[Dict]:
    """Fetches all active force join channels from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels ORDER BY id ASC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

def extract_chat_id(link: Optional[str], linkjoin: Optional[str] = "") -> Optional[str | int]:
    """
    Extracts a valid Telegram chat_id (e.g. '@channel' or -1001234567890)
    from stored link or linkjoin.
    """
    for candidate in [link, linkjoin]:
        if not candidate:
            continue
        candidate = candidate.strip()
        
        # Check if numeric chat ID (e.g. -100...)
        if candidate.startswith("-100") or candidate.isdigit() or (candidate.startswith("-") and candidate[1:].isdigit()):
            try:
                return int(candidate)
            except ValueError:
                pass
                
        # Check if username with @
        if candidate.startswith("@") and len(candidate) > 1:
            return candidate
            
        # Check if URL
        if "t.me/" in candidate:
            parts = candidate.split("t.me/")
            if len(parts) > 1:
                sub = parts[1].split("/")[0].split("?")[0]
                # If not a private join link (+ or joinchat/)
                if sub and not sub.startswith("+") and not sub.startswith("joinchat"):
                    return f"@{sub}"

        # If it's a plain username without @ and without http
        if not candidate.startswith("http") and "/" not in candidate and not candidate.startswith("+"):
            return f"@{candidate}"
            
    return None

async def check_user_membership(bot: Bot, chat_identifier: str | int, user_id: int) -> bool:
    """Checks if a user is a member of the given chat."""
    try:
        member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        elif member.status == ChatMemberStatus.RESTRICTED:
            return getattr(member, 'is_member', True)
        else:
            return False
    except Exception as e:
        logger.warning(f"Could not verify chat member for {chat_identifier} (user {user_id}): {e}")
        # If the bot is not admin or channel identifier is unreachable, fail-open to avoid locking out users
        return True

async def get_unjoined_channels(bot: Bot, user_id: int) -> List[Dict]:
    """
    Returns the list of channels that the user has NOT joined.
    Admins are always exempt.
    """
    if user_id in ADMIN_IDS:
        return []

    channels = await get_force_join_channels()
    if not channels:
        return []

    unjoined = []
    for ch in channels:
        chat_identifier = extract_chat_id(ch.get('link'), ch.get('linkjoin'))
        if not chat_identifier:
            continue

        is_member = await check_user_membership(bot, chat_identifier, user_id)
        if not is_member:
            unjoined.append(ch)

    return unjoined

def build_force_join_markup(unjoined_channels: List[Dict]) -> Tuple[str, types.InlineKeyboardMarkup]:
    """
    Builds the exact force join prompt message and keyboard matching the user's reference image:
    Header:
    ⚠️ کاربر گرامی؛ شما عضو چنل ما نیستید
    از طریق دکمه زیر وارد کانال شده و عضو شوید
    پس از عضویت دکمه بررسی عضویت را کلیک کنید

    Buttons:
    - Channel title (remark e.g. "به جمع ما بپیوند") -> linkjoin URL
    - "بررسی عضویت ✅" (style="danger") -> callback "confirm_channel"
    """
    text = (
        "⚠️ <b>کاربر گرامی؛ شما عضو چنل ما نیستید</b>\n"
        "از طریق دکمه زیر وارد کانال شده و عضو شوید\n"
        "پس از عضویت دکمه بررسی عضویت را کلیک کنید"
    )

    builder = InlineKeyboardBuilder()
    for ch in unjoined_channels:
        title = ch.get('remark') or "به جمع ما بپیوند"
        join_url = ch.get('linkjoin') or ch.get('link') or "https://t.me"
        builder.row(types.InlineKeyboardButton(text=title, url=join_url))

    builder.row(
        types.InlineKeyboardButton(
            text="بررسی عضویت ✅", 
            callback_data="confirm_channel", 
            style="danger"
        )
    )

    return text, builder.as_markup()
