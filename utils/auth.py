import hmac
import hashlib
import urllib.parse
import json
import time

class CandyAuth:
    @staticmethod
    def validate_init_data(raw_data, bot_token: str) -> dict:
        if isinstance(raw_data, str):
            raw_data = raw_data.strip()
            if not raw_data:
                raise ValueError("Telegram init data is missing or invalid")
            init_data = dict(urllib.parse.parse_qsl(raw_data))
        elif isinstance(raw_data, dict):
            init_data = raw_data.copy()
        else:
            raise ValueError("Telegram init data is missing or invalid")
            
        if not init_data:
            raise ValueError("Telegram init data payload is empty")
            
        if 'hash' not in init_data:
            raise ValueError("Telegram init data is missing required signature")
            
        received_hash = init_data.pop('hash')
        
        check_arr = []
        for k, v in init_data.items():
            check_arr.append(f"{k}={CandyAuth._normalize(v)}")
            
        if not check_arr:
            raise ValueError("Telegram init data payload is empty")
            
        check_arr.sort()
        check_string = "\n".join(check_arr)
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(calc_hash, received_hash):
            raise RuntimeError("User verification failed")
            
        user_raw = init_data.get('user')
        if isinstance(user_raw, str):
            try:
                user_data = json.loads(user_raw)
            except json.JSONDecodeError:
                user_data = None
        elif isinstance(user_raw, dict):
            user_data = user_raw
        else:
            user_data = None
            
        if not isinstance(user_data, dict) or 'id' not in user_data:
            raise RuntimeError("User data is missing or malformed in init data")
            
        return user_data

    @staticmethod
    def validate_contact_response(raw_data, bot_token: str) -> dict:
        if not isinstance(raw_data, str):
            raise ValueError("Contact data is missing or invalid")
        raw_data = raw_data.strip()
        if not raw_data:
            raise ValueError("Contact data is missing or invalid")
            
        data = dict(urllib.parse.parse_qsl(raw_data))
        if 'hash' not in data:
            raise ValueError("Contact data is missing required signature")
            
        received_hash = data.pop('hash')
        
        check_arr = []
        for k, v in data.items():
            check_arr.append(f"{k}={CandyAuth._normalize(v)}")
            
        if not check_arr:
            raise ValueError("Contact data payload is empty")
            
        check_arr.sort()
        check_string = "\n".join(check_arr)
        
        secrets = [
            hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest(),
            bot_token.encode()
        ]
        
        valid = False
        for secret in secrets:
            calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(calc, received_hash):
                valid = True
                break
                
        if not valid:
            raise RuntimeError("Contact verification failed")
            
        if 'auth_date' in data:
            auth_date = int(data['auth_date'])
            if auth_date > 0 and (time.time() - auth_date) > 86400:
                raise RuntimeError("Contact data has expired")
                
        contact_raw = data.get('contact')
        if isinstance(contact_raw, str):
            try:
                contact = json.loads(contact_raw)
            except json.JSONDecodeError:
                contact = None
        elif isinstance(contact_raw, dict):
            contact = contact_raw
        else:
            contact = None
            
        if not isinstance(contact, dict) or ('user_id' not in contact and 'phone_number' not in contact):
            raise RuntimeError("Contact payload is missing or malformed")
            
        return contact

    @staticmethod
    def extract_bearer_token(request) -> str | None:
        auth = request.headers.get('Authorization')
        if not auth:
            return None
        if not auth.lower().startswith('bearer '):
            return None
        return auth[7:].strip()

    @staticmethod
    def _normalize(value) -> str:
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(',', ':'), ensure_ascii=False)
        if value is None:
            return ''
        return str(value)
