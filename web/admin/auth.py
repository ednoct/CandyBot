# === IMPORTS ===
import aiosqlite
from aiohttp import web
import aiohttp_jinja2
from database import db_manager

# === AUTHENTICATION HANDLERS ===
async def login_get(request):
    """Render the admin login page."""
    # If already logged in, redirect to dashboard
    if request.cookies.get("admin_session") == "authenticated":
        return web.HTTPFound('/admin/dashboard')
    return aiohttp_jinja2.render_template('admin/login.html', request, {})

async def login_post(request):
    """Process admin login."""
    data = await request.post()
    username = data.get("username", "")
    password = data.get("password", "")

    async with aiosqlite.connect(db_manager.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Legacy passwords might be plaintext or hashed. We assume plaintext for this migration unless there's a specific hashing method.
        # Ideally, this should use proper hashing (e.g. bcrypt).
        async with db.execute("SELECT * FROM admin WHERE username = ? AND password = ?", (username, password)) as cursor:
            admin = await cursor.fetchone()
            
    if admin:
        response = web.HTTPFound('/admin/dashboard')
        # Setting a simple cookie for demonstration. In production, use aiohttp_session or signed cookies.
        response.set_cookie("admin_session", "authenticated", max_age=86400, httponly=True)
        return response
    else:
        context = {"error": "نام کاربری یا رمز عبور اشتباه است."}
        return aiohttp_jinja2.render_template('admin/login.html', request, context)

async def logout(request):
    """Process admin logout."""
    response = web.HTTPFound('/admin/login')
    response.del_cookie("admin_session")
    return response

# === AUTH MIDDLEWARE ===
@web.middleware
async def admin_auth_middleware(request, handler):
    """Middleware to protect /admin routes (except login)."""
    if request.path.startswith('/admin') and not request.path.startswith('/admin/login'):
        if request.cookies.get("admin_session") != "authenticated":
            return web.HTTPFound('/admin/login')
    return await handler(request)
