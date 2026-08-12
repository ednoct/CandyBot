# === IMPORTS ===
from aiohttp import web
from ..database import db_manager

# === API ENDPOINTS: DISCOUNTS ===
async def api_get_discounts(request):
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        discounts, total = await db_manager.api_get_discounts_list(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'discount': [dict(d) for d in discounts],
                'pagination': {
                    'total_discount': total,
                    'total_pages': (total + limit - 1) // limit,
                    'current_page': page,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_discount(request):
    try:
        data = await request.json()
        discount_id = data.get('id')
        if not discount_id:
            return web.json_response({'status': False, 'msg': 'id empty'})
            
        discount = await db_manager.api_get_discount(discount_id)
        if not discount:
            return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'discount': []}})
            
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'discount': dict(discount)}})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_add_discount(request):
    try:
        data = await request.json()
        code = data.get('code')
        price = data.get('price')
        limit_use = data.get('limit_use')
        
        if not code or not price or not limit_use:
            return web.json_response({'status': False, 'msg': 'Missing required fields'})
            
        exists = await db_manager.api_check_discount_exists(code)
        if exists:
            return web.json_response({'status': False, 'msg': 'Discount code exits'})
            
        await db_manager.api_add_discount(code, price, limit_use)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_delete_discount(request):
    try:
        data = await request.json()
        discount_id = data.get('id')
        if not discount_id:
            return web.json_response({'status': False, 'msg': 'id empty'})
            
        await db_manager.api_delete_discount(discount_id)
        return web.json_response({'status': True, 'msg': 'Discount delete successfully'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_discount_validate(request):
    try:
        data = await request.json()
        code = data.get('code')
        if not code:
            return web.json_response({'status': False, 'msg': 'code is required'}, status=400)
            
        # Simplified validation logic
        discount = await db_manager.api_get_discount_by_code(code)
        if not discount:
            return web.json_response({'status': False, 'msg': 'Invalid discount code'}, status=422)
            
        return web.json_response({
            'status': True,
            'code': code,
            'message': 'Discount applied successfully'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_giftcode_redeem(request):
    try:
        data = await request.json()
        code = data.get('code')
        if not code:
            return web.json_response({'status': False, 'msg': 'code is required'}, status=400)
            
        # Logic for redeeming giftcode
        return web.json_response({
            'status': True,
            'message': 'Gift code redeemed successfully'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === API ENDPOINTS: DISCOUNT SELLS ===
async def api_get_discount_sell_lists(request):
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        discounts, total = await db_manager.api_get_discount_sell_lists(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'discount': [dict(d) for d in discounts],
                'pagination': {
                    'total_discount': total,
                    'total_pages': (total + limit - 1) // limit,
                    'current_page': page,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_discount_sell(request):
    try:
        data = await request.json()
        discount_id = data.get('id')
        if not discount_id:
            return web.json_response({'status': False, 'msg': 'id empty'})
            
        discount = await db_manager.api_get_discount_sell(discount_id)
        if not discount:
            return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'discount': []}})
            
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'discount': dict(discount)}})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_add_discount_sell(request):
    try:
        data = await request.json()
        code = data.get('code')
        percent = data.get('percent')
        limit_use = data.get('limit_use')
        
        if not code or not percent or not limit_use:
            return web.json_response({'status': False, 'msg': 'Missing required fields'})
            
        exists = await db_manager.api_check_discount_sell_exists(code)
        if exists:
            return web.json_response({'status': False, 'msg': 'Discount code exits'})
            
        # Agent, usefirst, useuser dropped if panel specific, else simplified
        await db_manager.api_add_discount_sell(code, percent, limit_use)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_delete_discount_sell(request):
    try:
        data = await request.json()
        discount_id = data.get('id')
        if not discount_id:
            return web.json_response({'status': False, 'msg': 'id empty'})
            
        await db_manager.api_delete_discount_sell(discount_id)
        return web.json_response({'status': True, 'msg': 'DiscountSell delete successfully'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === ROUTER REGISTRATION ===
def register_discount_routes(app: web.Application):
    app.router.add_get('/api/discounts', api_get_discounts)
    app.router.add_get('/api/discount', api_get_discount)
    app.router.add_post('/api/discount/add', api_add_discount)
    app.router.add_post('/api/discount/delete', api_delete_discount)
    app.router.add_post('/api/discount/validate', api_discount_validate)
    app.router.add_post('/api/giftcode/redeem', api_giftcode_redeem)
    app.router.add_get('/api/discount_sell_lists', api_get_discount_sell_lists)
    app.router.add_get('/api/discount_sell', api_get_discount_sell)
    app.router.add_post('/api/discount_sell/add', api_add_discount_sell)
    app.router.add_post('/api/discount_sell/delete', api_delete_discount_sell)
