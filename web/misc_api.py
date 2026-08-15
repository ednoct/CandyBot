# === IMPORTS ===
from aiohttp import web
from database import db_manager

# === API ENDPOINTS: UTILITIES ===
async def api_qr_generate(request):
    try:
        payload = request.query.get('d', '')
        if not payload:
            return web.Response(text='d (data) is required', status=400)
            
        size = int(request.query.get('s', 320))
        url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={payload}"
        return web.HTTPFound(url)
    except Exception as e:
        return web.Response(text=str(e), status=500)

async def api_diag(request):
    import time
    from database import db_manager
    try:
        # Basic health check: test DB connection
        count = await db_manager.get_user_count()
        return web.json_response({
            'ok': True,
            'service': 'Candy Connect',
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'db_status': 'connected',
            'user_count': count
        })
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)}, status=500)

# === API ENDPOINTS: LOGGING ===
async def api_log(request):
    try:
        data = await request.json() if request.can_read_body else {}
        action = data.get('actions', 'log')
        ip = request.remote or 'unknown'
        
        await db_manager.api_insert_log(dict(request.headers), data, ip, action)
        
        count_user = await db_manager.get_user_count()
        count_agent = await db_manager.get_agent_count()
        count_invoice = await db_manager.get_invoice_count()
        
        return web.json_response({
            'count_user': count_user,
            'count_invoice': count_invoice,
            'count_agent': count_agent
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_clientlog(request):
    import json
    from datetime import datetime
    import os
    try:
        data = await request.json()
        ip = request.remote or '0.0.0.0'
        
        entry = {
            'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ip': ip,
            'ua': request.headers.get('User-Agent', '')[:400],
            'ref': request.headers.get('Referer', '')[:400],
            'level': str(data.get('level', 'error')),
            'msg': str(data.get('msg', ''))[:1000],
            'where': str(data.get('where', ''))[:400],
            'stack': str(data.get('stack', ''))[:4000],
            'diag': data.get('diag'),
            'extra': data.get('extra')
        }
        
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"client-{datetime.now().strftime('%Y-%m-%d')}.log")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'msg': str(e)}, status=500)

# === ROUTER REGISTRATION ===
def register_misc_routes(app: web.Application):
    app.router.add_get('/api/diag', api_diag)
    app.router.add_get('/api/qr', api_qr_generate)
    app.router.add_post('/api/log', api_log)
    app.router.add_post('/api/statbot', api_log)
    app.router.add_post('/api/clientlog', api_clientlog)
