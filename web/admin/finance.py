# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from ...database import db_manager

# === FINANCE HANDLERS ===
async def finance_get(request):
    """Render the financial reports and invoices page."""
    invoices = []
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invoices ORDER BY created_at DESC LIMIT 100") as cursor:
            invoices = [dict(row) for row in await cursor.fetchall()]

    context = {"invoices": invoices}
    return aiohttp_jinja2.render_template('admin/finance.html', request, context)
