# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from database import db_manager

# === LICENSES HANDLERS ===
async def licenses_get(request):
    """Render the license vault page (مخزن لایسنس ها)."""
    licenses = []
    plans = []
    
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            # Fetch available plans with their packages
            async with db.execute("SELECT id, name FROM plans ORDER BY id DESC") as p_cursor:
                for p_row in await p_cursor.fetchall():
                    plan_dict = dict(p_row)
                    async with db.execute("SELECT * FROM time_packages WHERE plan_id = ?", (plan_dict['id'],)) as t_cursor:
                        plan_dict['times'] = [dict(t) for t in await t_cursor.fetchall()]
                    async with db.execute("SELECT * FROM traffic_packages WHERE plan_id = ?", (plan_dict['id'],)) as tr_cursor:
                        plan_dict['traffics'] = [dict(tr) for tr in await tr_cursor.fetchall()]
                    plans.append(plan_dict)
                
            # Fetch licenses from licenses_cargo
            async with db.execute('''
                SELECT lc.*, p.name as plan_name, tp.days as time_days, tr.gb as traffic_gb 
                FROM licenses_cargo lc 
                LEFT JOIN plans p ON lc.plan_id = p.id
                LEFT JOIN time_packages tp ON lc.time_package_id = tp.id
                LEFT JOIN traffic_packages tr ON lc.traffic_package_id = tr.id
                ORDER BY lc.id DESC
            ''') as cursor:
                licenses = [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            pass

    context = {"licenses": licenses, "plans": plans}
    return aiohttp_jinja2.render_template('admin/licenses.html', request, context)

async def licenses_post(request):
    """Upload/paste new licenses into the vault."""
    data = await request.post()
    combo = data.get("combo")
    license_keys_raw = data.get("license_keys", "")
    
    if not combo or not license_keys_raw:
        return web.HTTPBadRequest(text="Missing combo or license keys")
        
    keys = [k.strip() for k in license_keys_raw.splitlines() if k.strip()]
    if not keys:
        return web.HTTPBadRequest(text="No valid keys provided")
        
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        if combo == "free_test":
            for key in keys:
                await db.execute('INSERT INTO licenses_cargo (license_key, is_free_test) VALUES (?, 1)', (key,))
        else:
            try:
                plan_id, time_id, traffic_id = combo.split('_')
                for key in keys:
                    await db.execute('''
                        INSERT INTO licenses_cargo (plan_id, time_package_id, traffic_package_id, license_key, is_free_test)
                        VALUES (?, ?, ?, ?, 0)
                    ''', (int(plan_id), int(time_id), int(traffic_id), key))
            except Exception as e:
                return web.HTTPBadRequest(text="Invalid combo format")
                
        await db.commit()
        
    return web.HTTPFound('/admin/licenses')

async def licenses_delete(request):
    """Delete a license."""
    license_id = request.match_info.get('id')
    if not license_id:
        return web.HTTPBadRequest(text="Missing license id")
        
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        await db.execute("DELETE FROM licenses_cargo WHERE id = ?", (license_id,))
        await db.commit()
        
    return web.HTTPFound('/admin/licenses')
