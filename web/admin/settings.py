# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
import json
from ...database import db_manager

# === SETTINGS HANDLERS ===
async def settings_get(request):
    """Render the settings management page."""
    settings = {}
    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM settings") as cursor:
            for row in await cursor.fetchall():
                settings[row['key']] = row['value']

    context = {"settings": settings}
    return aiohttp_jinja2.render_template('admin/settings.html', request, context)

async def settings_post(request):
    """Handle settings form submission."""
    data = await request.post()
    
    # Checkbox fields
    checkboxes = ['tetra_status', 'usdt_status', 'gram_status']
    for key in checkboxes:
        val = '1' if key in data else '0'
        await db_manager.set_setting(key, val)

    # Simple key-value fields
    keys = [
        'Channel_Report', 'support_username', 'bot_text_welcome', 'bot_text_rules',
        'tetra_api_key', 'min_deposit_tetra', 'max_deposit_tetra',
        'wallet_usdt', 'min_deposit_usdt', 'max_deposit_usdt',
        'wallet_gram', 'exchanger_gram', 'memo_gram', 'min_deposit_gram', 'max_deposit_gram'
    ]
    for key in keys:
        if key in data:
            await db_manager.set_setting(key, data[key])
            
    # JSON fields like keyboard
    keyboard_layout = data.get('keyboard_layout')
    if keyboard_layout:
        try:
            # Validate JSON before saving
            json.loads(keyboard_layout)
            await db_manager.set_setting('keyboard_layout', keyboard_layout)
        except json.JSONDecodeError:
            pass # Invalid JSON, ignore or flash error
            
    return web.HTTPFound('/admin/settings')
