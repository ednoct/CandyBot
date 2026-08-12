# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from ...database import db_manager

# === USERS HANDLERS ===
async def users_get(request):
    """Render the user management page."""
    users = []
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY id DESC LIMIT 100") as cursor:
            users = [dict(row) for row in await cursor.fetchall()]

    context = {"users": users}
    return aiohttp_jinja2.render_template('admin/users.html', request, context)
