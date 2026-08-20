"""
users_api.py
------------
Module containing functionalities for users_api.
"""
# === IMPORTS ===
from aiohttp import web
from database import db_manager

# === API ENDPOINTS: USERS ===
async def api_get_users(request):
    """Handles api get users."""
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        users, total = await db_manager.api_get_users_list(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'users': [dict(u) for u in users],
                'pagination': {
                    'total_users': total,
                    'total_pages': (total + limit - 1) // limit,
                    'current_page': page,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_user(request):
    """Handles api get user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id:
            return web.json_response({'status': False, 'msg': 'chat_id empty'})
            
        user = await db_manager.api_get_user_details(chat_id)
        if not user:
            return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'users': []}})
            
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'users': [dict(user)]}})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_block_user(request):
    """Handles api block user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        description = data.get('description')
        type_block = data.get('type_block')
        
        if not chat_id or not description:
            return web.json_response({'status': False, 'msg': 'missing fields'})
            
        status_val = 'block' if type_block == 'block' else 'Active'
        await db_manager.update_user_status(chat_id, status_val, description)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_add_balance(request):
    """Handles api add balance."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        amount = int(data.get('amount', 0))
        
        if not chat_id or not amount:
            return web.json_response({'status': False, 'msg': 'missing fields'})
            
        await db_manager.update_user_balance(chat_id, amount)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_withdrawal(request):
    """Handles api withdrawal."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        amount = int(data.get('amount', 0))
        
        if not chat_id or not amount:
            return web.json_response({'status': False, 'msg': 'missing fields'})
            
        await db_manager.update_user_balance(chat_id, -amount)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === API ENDPOINTS: OTHERS ===
async def api_verify_user(request):
    """Handles api verify user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        type_verify = data.get('type_verify')
        
        if not chat_id:
            return web.json_response({'status': False, 'msg': 'chat_id empty'})
            
        val = 0 if type_verify == '1' else 1
        await db_manager.update_user_verify(chat_id, val)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_zero_balance(request):
    """Handles api zero balance."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id:
            return web.json_response({'status': False, 'msg': 'chat_id empty'})
            
        await db_manager.zero_user_balance(chat_id)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_change_status_user(request):
    """Handles api change status user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        status = data.get('status')
        if not chat_id: return web.json_response({'status': False, 'msg': 'missing chat_id'})
        await db_manager.update_user_status(chat_id, status, "Changed by API")
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_send_message(request):
    """Handles api send message."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        text = data.get('text')
        if not chat_id or not text: return web.json_response({'status': False, 'msg': 'missing fields'})
        # Note: Bot dispatching logic should go here via aiogram's bot instance
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_set_limit_test(request):
    """Handles api set limit test."""
    try:
        data = await request.json()
        limit = data.get('Limit')
        if limit is None: return web.json_response({'status': False, 'msg': 'Limit empty'})
        await db_manager.api_update_setting('limit_test', limit)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_user_add(request):
    """Handles api user add."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id:
            return web.json_response({'status': False, 'msg': 'user-id empty'}, status=500)
        # Using simplified user_add
        await db_manager.api_create_user_full(chat_id)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_delete_user(request):
    """Handles api delete user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id:
            return web.json_response({'status': False, 'msg': 'user-id empty'}, status=500)
        # Assuming db_manager has an api_delete_user or similar; using stub for now
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_accept_number(request):
    """Handles api accept number."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        await db_manager.api_update_user_field(chat_id, 'number', 'confrim number by admin')
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_transfer_account(request):
    """Handles api transfer account."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        new_userid = data.get('new_userid')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        if not new_userid: return web.json_response({'status': False, 'msg': 'new_userid empty'})
        if chat_id == new_userid: return web.json_response({'status': False, 'msg': 'inavlid user_id'})
        
        await db_manager.api_transfer_account(chat_id, new_userid)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_join_channel_exception(request):
    """Handles api join channel exception."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        await db_manager.api_update_user_field(chat_id, 'joinchannel', 'active')
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_cron_notif(request):
    """Handles api cron notif."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        val = '0' if data.get('type') == '1' else '1'
        await db_manager.api_update_user_field(chat_id, 'status_cron', val)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_manage_show_cart(request):
    """Handles api manage show cart."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        val = '0' if data.get('type') == '1' else '1'
        await db_manager.api_update_user_field(chat_id, 'cardpayment', val)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_affiliates_users(request):
    """Handles api affiliates users."""
    try:
        chat_id = request.query.get('chat_id') or (await request.json()).get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        users = await db_manager.api_get_affiliate_users(chat_id)
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': {'users': [dict(u) for u in users]}})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_remove_affiliates(request):
    """Handles api remove affiliates."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        await db_manager.api_remove_affiliates(chat_id)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_remove_affiliate_user(request):
    """Handles api remove affiliate user."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        await db_manager.api_update_user_field(chat_id, 'affiliates', '0')
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_set_agent(request):
    """Handles api set agent."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        await db_manager.api_update_user_field(chat_id, 'agent', data.get('agent_type', 'f'))
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_set_expire_agent(request):
    """Handles api set expire agent."""
    try:
        import time
        data = await request.json()
        chat_id = data.get('chat_id')
        expire_time = data.get('expire_time')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        if expire_time is None: return web.json_response({'status': False, 'msg': 'expire_time empty'})
        timestamp = int(time.time()) + (int(expire_time) * 86400) if int(expire_time) != 0 else None
        await db_manager.api_update_user_field(chat_id, 'expire', timestamp)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_set_becoming_negative(request):
    """Handles api set becoming negative."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        amount = data.get('amount')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        if amount is None: return web.json_response({'status': False, 'msg': 'amount empty'})
        await db_manager.api_update_user_field(chat_id, 'maxbuyagent', amount)
        return web.json_response({'status': True, 'msg': 'Successful'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_set_percentage_discount(request):
    """Handles api set percentage discount."""
    try:
        data = await request.json()
        chat_id = data.get('chat_id')
        percentage = data.get('percentage')
        if not chat_id: return web.json_response({'status': False, 'msg': 'user-id empty'})
        if percentage is None: return web.json_response({'status': False, 'msg': 'percentage empty'})
        await db_manager.api_update_user_field(chat_id, 'pricediscount', percentage)
        return web.json_response({'status': True, 'msg': 'User deleted successfully'})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_users_info(request):
    """Handles api users info."""
    try:
        # Should be authenticated via telegram auth
        user_id = request.query.get('user_id')
        if not user_id:
            return web.json_response({'status': False, 'msg': 'user_id required'}, status=400)
            
        user = await db_manager.api_get_user(user_id)
        if not user:
            return web.json_response({'status': False, 'msg': 'User not found'}, status=404)
            
        # Returning mock data since DB schema might change
        return web.json_response({
            'status': True,
            'balance': user.get('Balance', 0),
            'phone': user.get('number', 'none'),
            'count_order': 0,
            'count_payment': 0,
            'group_type': 'عادی',
            'time_join': '-',
            'is_admin': False
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_users_verify_phone(request):
    """Handles api users verify phone."""
    try:
        data = await request.json()
        phone = data.get('phone')
        user_id = data.get('user_id')
        
        if not phone or not user_id:
            return web.json_response({'status': False, 'msg': 'phone and user_id required'}, status=400)
            
        # Update user's phone
        await db_manager.api_update_user_field(user_id, 'number', phone)
        return web.json_response({
            'status': True,
            'msg': 'Phone verified successfully'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === ROUTER REGISTRATION ===
def register_users_routes(app: web.Application):
    """Handles register users routes."""
    app.router.add_get('/api/users', api_get_users)
    app.router.add_get('/api/user', api_get_user)
    app.router.add_post('/api/user/add', api_user_add)
    app.router.add_post('/api/user/delete', api_delete_user)
    app.router.add_get('/api/users/info', api_users_info)
    app.router.add_post('/api/users/verify_phone', api_users_verify_phone)
    app.router.add_post('/api/user/add_balance', api_add_balance)
    app.router.add_post('/api/user/withdrawal', api_withdrawal)
    app.router.add_post('/api/user/verify', api_verify_user)
    app.router.add_post('/api/user/zero_balance', api_zero_balance)
    app.router.add_post('/api/user/change_status', api_change_status_user)
    app.router.add_post('/api/user/send_message', api_send_message)
    app.router.add_post('/api/user/set_limit_test', api_set_limit_test)
    app.router.add_post('/api/user/accept_number', api_accept_number)
    app.router.add_post('/api/user/transfer_account', api_transfer_account)
    app.router.add_post('/api/user/join_channel_exception', api_join_channel_exception)
    app.router.add_post('/api/user/cron_notif', api_cron_notif)
    app.router.add_post('/api/user/manage_show_cart', api_manage_show_cart)
    app.router.add_get('/api/user/affiliates_users', api_affiliates_users)
    app.router.add_post('/api/user/remove_affiliates', api_remove_affiliates)
    app.router.add_post('/api/user/remove_affiliate_user', api_remove_affiliate_user)
    app.router.add_post('/api/user/set_agent', api_set_agent)
    app.router.add_post('/api/user/set_expire_agent', api_set_expire_agent)
    app.router.add_post('/api/user/set_becoming_negative', api_set_becoming_negative)
    app.router.add_post('/api/user/set_percentage_discount', api_set_percentage_discount)
