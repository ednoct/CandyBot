"""
panel_api.py
------------
Module containing functionalities for panel_api.
"""
# === IMPORTS ===
import os
import aiohttp_cors
import aiohttp_jinja2
import jinja2
from aiohttp import web
from database import db_manager
from utils.error_handler import error_middleware
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
    
    # 1. Setup Jinja2 Template Engine
    template_path = os.path.join(os.path.dirname(__file__), 'templates')
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_path))
    
    # 2. Setup Static Files (CSS/JS)
    static_path = os.path.join(os.path.dirname(__file__), 'static')
    app.router.add_static('/static/', path=static_path, name='static')
    
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