import json

class CandyInput:
    @staticmethod
    async def payload(request) -> dict:
        method = request.method
        payload = dict(request.query)
        
        if method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            if request.can_read_body:
                try:
                    data = await request.json()
                    if isinstance(data, dict):
                        payload.update(data)
                except Exception:
                    pass
                
        return CandyInput.sanitise(payload)

    @staticmethod
    def int(data: dict, key: str, default: int = 0) -> int:
        if key not in data: return default
        try:
            return int(data[key])
        except (ValueError, TypeError):
            return default

    @staticmethod
    def int_min(data: dict, key: str, min_val: int, default: int) -> int:
        v = CandyInput.int(data, key, default)
        return default if v < min_val else v

    @staticmethod
    def int_range(data: dict, key: str, min_val: int, max_val: int, default: int) -> int:
        v = CandyInput.int(data, key, default)
        if v < min_val: return default
        if v > max_val: return max_val
        return v

    @staticmethod
    def string(data: dict, key: str, default: str = "") -> str:
        if key not in data: return default
        v = data[key]
        if isinstance(v, (str, int, float)):
            return str(v).strip()
        return default

    @staticmethod
    def nullable_string(data: dict, key: str) -> str | None:
        if key not in data: return None
        v = data[key]
        if not isinstance(v, (str, int, float)): return None
        v = str(v).strip()
        return v if v else None

    @staticmethod
    def array(data: dict, key: str) -> list:
        if key not in data: return []
        v = data[key]
        return v if isinstance(v, list) else []

    @staticmethod
    def sanitise(data):
        if isinstance(data, dict):
            return {k: CandyInput.sanitise(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [CandyInput.sanitise(v) for v in data]
        elif isinstance(data, str):
            return data.strip()
        return data
