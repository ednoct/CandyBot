# === IMPORTS ===
"""
response.py
-----------
Module containing functionalities for response.
"""
from aiohttp import web

class CandyResponse:
    @staticmethod
    def ok(obj=None, msg="Successful", meta=None):
        """Handles ok."""
        return CandyResponse.send(200, True, msg, obj, meta)

    @staticmethod
    def fail(status_code: int, msg: str, obj=None):
        """Handles fail."""
        return CandyResponse.send(status_code, False, msg, obj, None)

    @staticmethod
    def bad_request(msg="Bad request", obj=None):
        """Handles bad request."""
        return CandyResponse.send(400, False, msg, obj, None)

    @staticmethod
    def unauthorized(msg="Authorization header missing"):
        """Handles unauthorized."""
        return CandyResponse.send(401, False, msg, None, None)

    @staticmethod
    def forbidden(msg="Forbidden"):
        """Handles forbidden."""
        return CandyResponse.send(403, False, msg, None, None)

    @staticmethod
    def not_found(msg="Not found"):
        """Handles not found."""
        return CandyResponse.send(404, False, msg, None, None)

    @staticmethod
    def method_not_allowed(expected: str):
        """Handles method not allowed."""
        return CandyResponse.send(405, False, f"Method invalid; must be {expected}", None, None)

    @staticmethod
    def server_error(msg="Internal server error"):
        """Handles server error."""
        return CandyResponse.send(500, False, msg, None, None)

    @staticmethod
    def send(status_code: int, status: bool, msg: str, obj, meta):
        """Handles send."""
        payload = {
            "status": status,
            "msg": msg
        }
        if obj is not None:
            payload["obj"] = obj
        elif not status:
            payload["obj"] = []
            
        if meta is not None:
            payload["meta"] = meta
            
        return web.json_response(payload, status=status_code)
