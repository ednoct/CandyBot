"""
dashboard.py
------------
Module containing functionalities for dashboard.
"""
# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from database import db_manager

# === DASHBOARD HANDLERS ===
async def dashboard_get(request):
    """Render the admin dashboard index page."""
    stats = {
        "total_users": 0,
        "total_sales": 0,
        "active_licenses": 0,
        "pending_payments": 0
    }
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        # Get users count
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            stats["total_users"] = (await cursor.fetchone())[0]
            
        # Get pending payments
        async with db.execute("SELECT COUNT(*) FROM invoices WHERE status = 'pending'") as cursor:
            stats["pending_payments"] = (await cursor.fetchone())[0]
            
        # Get total sales (completed invoices)
        async with db.execute("SELECT SUM(final_amount) FROM invoices WHERE status = 'paid'") as cursor:
            res = await cursor.fetchone()
            stats["total_sales"] = res[0] if res and res[0] else 0
            
        # Get active licenses (where assigned to a user)
        # Note: This schema will be created/used in licenses.py
        try:
            async with db.execute("SELECT COUNT(*) FROM licenses WHERE assigned_to IS NOT NULL") as cursor:
                stats["active_licenses"] = (await cursor.fetchone())[0]
        except aiosqlite.OperationalError:
            pass # Table might not exist yet
            
    context = {"stats": stats}
    return aiohttp_jinja2.render_template('admin/dashboard.html', request, context)
