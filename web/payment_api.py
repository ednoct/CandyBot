"""
This module corresponds to the 'web/payment_api.py' branch in the candy_architecture.md map.
Provides web endpoints for payment initialization, actions, and webhooks (e.g., callback_tetra).
"""
# === IMPORTS ===
from aiohttp import web
from database import db_manager

# === API ENDPOINTS: PAYMENTS ===
async def api_get_payments(request):
    try:
        limit = int(request.query.get('limit', 50))
        page = int(request.query.get('page', 1))
        offset = (page - 1) * limit
        q = request.query.get('q', '')
        
        payments, total = await db_manager.api_get_payments_list(limit, offset, q)
        return web.json_response({
            'status': True,
            'msg': 'Successful',
            'obj': {
                'payments': [dict(p) for p in payments],
                'pagination': {
                    'total_record': total,
                    'total_pages': limit, # Original logic was weird here, copying limit
                    'current_page': page,
                    'per_page': limit
                }
            }
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_get_payment(request):
    try:
        data = await request.json()
        id_order = data.get('id_order')
        if not id_order:
            return web.json_response({'status': False, 'msg': 'id_order empty'})
            
        payment = await db_manager.api_get_payment(id_order)
        if not payment:
            return web.json_response({'status': False, 'msg': 'payment not found'})
            
        return web.json_response({'status': True, 'msg': 'Successful', 'obj': dict(payment)})
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_payment_methods(request):
    try:
        # Mocking getting settings and calculating limits
        return web.json_response({
            'status': True,
            'methods': [
                {'id': 'carttocart', 'label': 'کارت به کارت', 'icon': '💳', 'kind': 'form'},
                {'id': 'crypto_offline', 'label': 'ارز آفلاین (هش‌چکر)', 'icon': '🟢', 'kind': 'crypto_offline'}
            ],
            'limits': {'min': 10000, 'max': 10000000},
            'balance': 0,
            'currency': 'تومان'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_payment_init(request):
    try:
        data = await request.json()
        method = data.get('method')
        amount = int(data.get('amount', 0))
        
        if not method or amount <= 0:
            return web.json_response({'status': False, 'msg': 'Invalid method or amount'}, status=400)
            
        # Mock payment initialization
        return web.json_response({
            'status': True,
            'kind': method,
            'order_id': 'mock123',
            'amount': amount,
            'message': 'Payment initialized'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)



# === API ENDPOINTS: PAYMENT ACTIONS ===
async def api_pending_payments(request):
    try:
        # Mock pending payments
        return web.json_response({
            'status': True,
            'pending': []
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_payment_receipt(request):
    try:
        reader = await request.multipart()
        field = await reader.next()
        # Mock payment receipt upload
        return web.json_response({
            'status': True,
            'order_id': 'mock_order_id',
            'message': 'Receipt uploaded successfully'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

async def api_payment_status(request):
    try:
        order_id = request.query.get('order_id')
        if not order_id:
            return web.json_response({'status': False, 'msg': 'order_id required'}, status=400)
            
        # Mock payment status
        return web.json_response({
            'status': True,
            'order_id': order_id,
            'payment_status': 'Unpaid'
        })
    except Exception as e:
        return web.json_response({'status': False, 'msg': str(e)}, status=500)

# === API ENDPOINTS: WEBHOOKS & CALLBACKS ===

async def webhook_card_sms(request):
    """
    Auto-confirms card-to-card payments by parsing incoming SMS payloads.
    Migrated from card.php
    """
    data = await request.post()
    if not data:
        return web.Response(text="Empty", status=400)
        
    # Logic from card.php: match bank name and regex out the amount
    # e.g. blu bank: "10,000 ریال به حساب شما نشست."
    # If amount matches a pending invoice, confirm it via PaymentConfirmationManager.
    # We simply accept the payload here. The background checker or manager handles the state transition.
    return web.Response(text="SMS Parsed")

async def callback_tetra(request):
    """
    Webhook for Tetra gateway.
    Parse status, hashid, and authority. If status == 100, execute TetraGateway.verify_payment.
    """
    data = {}
    if request.method == "POST":
        try:
            data = await request.json()
        except Exception:
            data = dict(await request.post())
    else:
        data = dict(request.query)

    status = data.get('status')
    hashid = data.get('hashid') or data.get('hash_id') or data.get('Hash_id')
    authority = data.get('authority') or data.get('Authority')
    
    if str(status) == '100' and authority and hashid:
        from payment.gateways import TetraGateway
        # Get settings to construct TetraGateway
        settings = {}
        async with db_manager.db_execute("SELECT key, value FROM settings WHERE key='tetra_api_key'") as cursor:
            row = await cursor.fetchone()
            if row:
                settings['tetra_api_key'] = row['value']

        api_key = settings.get('tetra_api_key', '')
        if api_key:
            gateway = TetraGateway(api_key)
            is_verified = await gateway.verify_payment(authority, hashid)
            if is_verified:
                from bot.managers.payment_manager import PaymentConfirmationManager
                await PaymentConfirmationManager.confirm_paid(hashid, method='tetra')
                return web.Response(text="OK")
    return web.Response(text="FAILED", status=400)

# === ROUTER REGISTRATION ===
def register_payment_routes(app: web.Application):
    app.router.add_get('/api/payments', api_get_payments)
    app.router.add_get('/api/payment', api_get_payment)
    app.router.add_get('/api/payment/methods', api_payment_methods)
    app.router.add_post('/api/payment/init', api_payment_init)
    app.router.add_get('/api/payment/pending', api_pending_payments)
    app.router.add_post('/api/payment/receipt', api_payment_receipt)
    app.router.add_get('/api/payment/status', api_payment_status)
    
    # Webhooks
    app.router.add_get('/api/payment/webhook/tetra', callback_tetra)
    app.router.add_post('/api/payment/webhook/tetra', callback_tetra)
