"""
settings_api.py
---------------
Module containing functionalities for settings_api.
"""
# === IMPORTS ===
from aiohttp import web
from database import db_manager

# === API ENDPOINTS: SETTINGS ===
async def api_keyboard_set(request):
    try:
        data = await request.json()
        keyboard = data.get('keyboard')
        if not keyboard:
            return web.json_response({'status': False, 'msg': 'missing fields'})
            
        await db_manager.api_update_setting('keyboard', keyboard)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_setting_info(request):
    try:
        setting = await db_manager.api_get_settings()
        if not setting:
            return web.json_response({'status': False, 'msg': 'settings not found'})
            
        # Strip out product/category related settings based on Purge Rules
        safe_setting = {k: v for k, v in dict(setting).items() if 'product' not in k.lower() and 'category' not in k.lower()}
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': safe_setting})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_save_setting_shop(request):
    try:
        data = await request.json()
        # Drop logic related to Category & Product Management, renewals, extra traffic/time
        # Only saving allowed settings
        allowed_keys = ['name_shop', 'support_id', 'channel_id']
        updates = {}
        for key in allowed_keys:
            if key in data:
                updates[key] = data[key]
                
        if updates:
            await db_manager.api_update_settings_batch(updates)
            
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === ROUTER REGISTRATION ===
def register_settings_routes(app: web.Application):
    app.router.add_post('/api/settings/keyboard', api_keyboard_set)
    app.router.add_get('/api/settings/info', api_setting_info)
    app.router.add_post('/api/settings/shop', api_save_setting_shop)
