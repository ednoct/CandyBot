# === IMPORTS ===
import aiohttp_cors
from aiohttp import web
from ..database import db_manager
from ..utils.error_handler import error_middleware
from .users_api import register_users_routes
from .invoice_api import register_invoice_routes
from .discount_api import register_discount_routes
from .payment_api import register_payment_routes
from .settings_api import register_settings_routes
from .misc_api import register_misc_routes
from .admin import register_admin_routes

# === API ENDPOINTS ===
async def get_plans_api(request):
    plans = await db_manager.get_plans()
    return web.json_response([dict(p) for p in plans])

# === WEB APP INITIALIZATION ===
async def init_web_app():
    app = web.Application(middlewares=[error_middleware])
    
    # Add routes
    app.router.add_get('/api/plans', get_plans_api)
    register_users_routes(app)
    register_invoice_routes(app)
    register_discount_routes(app)
    register_payment_routes(app)
    register_settings_routes(app)
    register_misc_routes(app)
    register_admin_routes(app)
    
    # Configure default CORS settings
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    # Configure CORS on all routes
    for route in list(app.router.routes()):
        cors.add(route)
        
    return app
