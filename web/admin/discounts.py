"""
discounts.py
------------
Module containing functionalities for discounts.
"""
# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from database import db_manager

# === DISCOUNTS HANDLERS ===
async def discounts_get(request):
    """Render the discounts management page."""
    discounts = []
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM discount_codes ORDER BY created_at DESC") as cursor:
            discounts = [dict(row) for row in await cursor.fetchall()]

    context = {"discounts": discounts}
    return aiohttp_jinja2.render_template('admin/discounts.html', request, context)
