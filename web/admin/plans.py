"""
plans.py
--------
Module containing functionalities for plans.
"""
# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from database import db_manager

# === PLANS HANDLERS ===
async def plans_get(request):
    """Render the plans management page."""
    plans = []
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            # Fetch plans
            async with db.execute("SELECT * FROM plans ORDER BY id DESC") as cursor:
                for row in await cursor.fetchall():
                    plan_dict = dict(row)
                    
                    # Fetch time packages for this plan
                    async with db.execute("SELECT * FROM time_packages WHERE plan_id = ?", (plan_dict['id'],)) as t_cursor:
                        plan_dict['time_packages'] = [dict(t) for t in await t_cursor.fetchall()]
                        
                    # Fetch traffic packages for this plan
                    async with db.execute("SELECT * FROM traffic_packages WHERE plan_id = ?", (plan_dict['id'],)) as tr_cursor:
                        plan_dict['traffic_packages'] = [dict(tr) for tr in await tr_cursor.fetchall()]
                        
                    plans.append(plan_dict)
        except Exception as e:
            pass # Handle gracefully in template

    context = {"plans": plans}
    return aiohttp_jinja2.render_template('admin/plans.html', request, context)

async def plans_post(request):
    """Create a new plan."""
    data = await request.post()
    action = data.get("action", "add_plan")
    
    if action == "add_plan":
        name = data.get("name")
        admin_description = data.get("admin_description", "")
        price_per_day = data.get("price_per_day", 0)
        price_per_gb = data.get("price_per_gb", 0)

        if not name:
            return web.HTTPBadRequest(text="Missing plan name")

        try:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                await db.execute('''
                    INSERT INTO plans (name, admin_description, price_per_day, price_per_gb)
                    VALUES (?, ?, ?, ?)
                ''', (name, admin_description, int(price_per_day), int(price_per_gb)))
                await db.commit()
        except ValueError:
            return web.HTTPBadRequest(text="Invalid number format")

    elif action == "add_time":
        plan_id = data.get("plan_id")
        days = data.get("days")
        if plan_id and days:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                await db.execute('INSERT INTO time_packages (plan_id, days) VALUES (?, ?)', (int(plan_id), int(days)))
                await db.commit()
                
    elif action == "add_traffic":
        plan_id = data.get("plan_id")
        gb = data.get("gb")
        if plan_id and gb:
            async with aiosqlite.connect(db_manager.DB_PATH) as db:
                await db.execute('INSERT INTO traffic_packages (plan_id, gb) VALUES (?, ?)', (int(plan_id), int(gb)))
                await db.commit()

    return web.HTTPFound('/admin/plans')

async def plans_delete(request):
    """Delete a plan, time_package, or traffic_package."""
    item_type = request.query.get('type', 'plan')
    item_id = request.match_info.get('id')
    if not item_id:
        return web.HTTPBadRequest(text="Missing id")
        
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        if item_type == 'plan':
            await db.execute("DELETE FROM plans WHERE id = ?", (item_id,))
        elif item_type == 'time':
            await db.execute("DELETE FROM time_packages WHERE id = ?", (item_id,))
        elif item_type == 'traffic':
            await db.execute("DELETE FROM traffic_packages WHERE id = ?", (item_id,))
        await db.commit()
        
    return web.HTTPFound('/admin/plans')
