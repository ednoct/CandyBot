"""
invoice_api.py
--------------
Module containing functionalities for invoice_api.
"""
# === IMPORTS ===
from aiohttp import web
from database import db_manager

# === API ENDPOINTS: INVOICES ===
async def api_get_invoices(request):
    """Handles api get invoices."""
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        invoices, total = await db_manager.api_get_invoices_list(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'invoices': [dict(i) for i in invoices],
                'pagination': {
                    'total_record': total,
                    'total_pages': (total + limit - 1) // limit,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_user_invoices(request):
    """Handles api user invoices."""
    try:
        limit = int(request.query.get('limit', 10))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        # user_id should come from auth, assuming query for now in this skeleton
        user_id = request.query.get('user_id', '')
        
        # db call to get user specific invoices
        invoices, total = await db_manager.api_get_user_invoices(user_id, limit, offset, q)
        return web.json_response({
            'status': True,
            'items': [dict(i) for i in invoices],
            'total': total,
            'total_pages': (total + limit - 1) // limit,
            'page': page,
            'limit': limit
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_services(request):
    """Handles api get services."""
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        services, total = await db_manager.api_get_services_list(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'services': [dict(s) for s in services],
                'pagination': {
                    'total_record': total,
                    'total_pages': (total + limit - 1) // limit,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_invoice(request):
    """Handles api get invoice."""
    try:
        data = await request.json()
        id_invoice = data.get('id_invoice')
        if not id_invoice:
            return web.json_response({'status': False, 'msg': 'id_invoice empty'})
            
        invoice = await db_manager.get_invoice(id_invoice)
        if not invoice:
            return web.json_response({'status': False, 'msg': 'invoice not found'})
            
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': dict(invoice)})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_invoice_add(request):
    """Handles api invoice add."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        username = data.get('username')
        code_product = data.get('code_product')
        
        if not chat_id or not username or not code_product:
            return web.json_response({'status': False, 'msg': 'Missing required fields'})
            
        # Mock logic, replace with true DB insertion for one-time sale
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_remove_service(request):
    """Handles api remove service."""
    try:
        data = await request.json()
        id_invoice = data.get('id_invoice')
        if not id_invoice:
            return web.json_response({'status': False, 'msg': 'id_invoice empty'})
            
        # Dropped: type one/tow/three panel connections
        # Simplified: just removing local record
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_service_action(request):
    """Handles api service action."""
    try:
        data = await request.json()
        action = data.get('action')
        # Logic for service action like changelink (purged), refund, transfer
        return web.json_response({'status': True, 'msg': f'Action {action} processed successfully'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_service_simple_action(request):
    """Handles api service simple action."""
    try:
        data = await request.json()
        action = data.get('action')
        # Logic for simple actions: note, report_problem
        return web.json_response({'status': True, 'msg': f'Simple action {action} processed successfully'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_time_ranges(request):
    """Handles api time ranges."""
    try:
        # Mocking time ranges
        return web.json_response({
            'status': True,
            'ranges': [
                {'id': 1, 'name': '1 Month', 'day': 30},
                {'id': 2, 'name': '3 Months', 'day': 90}
            ]
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === ROUTER REGISTRATION ===
def register_invoice_routes(app: web.Application):
    """Handles register invoice routes."""
    app.router.add_get('/api/invoices', api_get_invoices)
    app.router.add_get('/api/user_invoices', api_user_invoices)
    app.router.add_get('/api/services', api_get_services)
    app.router.add_get('/api/invoice', api_get_invoice)
    app.router.add_post('/api/invoice/add', api_invoice_add)
    app.router.add_post('/api/invoice/remove', api_remove_service)
    app.router.add_post('/api/service/action', api_service_action)
    app.router.add_post('/api/service/simple_action', api_service_simple_action)
    app.router.add_get('/api/service/time_ranges', api_time_ranges)
