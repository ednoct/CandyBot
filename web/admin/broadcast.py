# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from ...database import db_manager

# === BROADCAST HANDLERS ===
async def broadcast_get(request):
    """Render the broadcast management page."""
    return aiohttp_jinja2.render_template('admin/broadcast.html', request, {})

async def broadcast_post(request):
    """Queue a new broadcast message."""
    data = await request.post()
    message = data.get("message")
    
    if message:
        async with aiosqlite.connect(db_manager.DB_PATH) as db:
            # We fetch all users and queue the message for each
            async with db.execute("SELECT id FROM users") as cursor:
                users = await cursor.fetchall()
                
            for user in users:
                await db.execute('''
                    INSERT INTO broadcast_queue (user_id, message_text, status)
                    VALUES (?, ?, 'pending')
                ''', (user[0], message))
            await db.commit()
            
    return web.HTTPFound('/admin/broadcast')
