# === IMPORTS ===
from aiohttp import web

# Import Handlers
from .auth import login_get, login_post, logout, admin_auth_middleware
from .dashboard import dashboard_get
from .plans import plans_get, plans_post, plans_delete
from .licenses import licenses_get, licenses_post, licenses_delete
from .users import users_get
from .finance import finance_get
from .discounts import discounts_get
from .settings import settings_get, settings_post
from .broadcast import broadcast_get, broadcast_post

# === ROUTER REGISTRATION ===
def register_admin_routes(app: web.Application):
    """Register all web admin panel routes."""
    
    # Mount middleware (assuming app.middlewares.append is called elsewhere, or we do it here)
    if admin_auth_middleware not in app.middlewares:
        app.middlewares.append(admin_auth_middleware)

    # Auth
    app.router.add_get('/admin/login', login_get)
    app.router.add_post('/admin/login', login_post)
    app.router.add_get('/admin/logout', logout)
    
    # Dashboard
    app.router.add_get('/admin', dashboard_get) # Redirects/renders dashboard
    app.router.add_get('/admin/', dashboard_get)
    app.router.add_get('/admin/dashboard', dashboard_get)
    
    # Plans
    app.router.add_get('/admin/plans', plans_get)
    app.router.add_post('/admin/plans', plans_post)
    app.router.add_get('/admin/plans/delete/{id}', plans_delete)
    
    # Licenses
    app.router.add_get('/admin/licenses', licenses_get)
    app.router.add_post('/admin/licenses', licenses_post)
    app.router.add_get('/admin/licenses/delete/{id}', licenses_delete)
    
    # Users, Finance, Discounts, Settings, Broadcast
    app.router.add_get('/admin/users', users_get)
    app.router.add_get('/admin/finance', finance_get)
    app.router.add_get('/admin/discounts', discounts_get)
    app.router.add_get('/admin/settings', settings_get)
    app.router.add_post('/admin/settings', settings_post)
    app.router.add_get('/admin/broadcast', broadcast_get)
    app.router.add_post('/admin/broadcast', broadcast_post)
