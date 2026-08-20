# === IMPORTS ===
"""
error_handler.py
----------------
Module containing functionalities for error_handler.
"""
from aiohttp import web
from .logger import CandyLogger

@web.middleware
async def error_middleware(request, handler):
    """Handles error middleware."""
    try:
        response = await handler(request)
        return response
    except web.HTTPException as ex:
        return web.json_response({'status': False, 'msg': ex.reason}, status=ex.status)
    except Exception as e:
        CandyLogger.exception(e, "Uncaught exception in web handler", {
            "method": request.method,
            "uri": request.path,
            "ip": request.remote
        })
        return web.json_response({
            'status': False,
            'msg': 'Internal server error'
        }, status=500)
