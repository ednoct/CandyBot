"""
This module corresponds to the 'payment/gateways.py' branch in the candy_architecture.md map.
Contains the base PaymentGateway interface and specific online gateways like TetraGateway.
"""
# === IMPORTS ===
import aiohttp
import uuid
import hashlib
import hmac

# === BASE GATEWAY CLASS ===
class PaymentGateway:
    async def create_payment(self, amount: int, description: str, callback_url: str):
        raise NotImplementedError
        
    async def verify_payment(self, payment_id: str, amount: int, **kwargs):
        raise NotImplementedError

class TetraGateway(PaymentGateway):
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    async def create_payment(self, invoice_id: str, amount_toman: int, callback_url: str):
        url = "https://tetra98.com/api/create_order"
        amount_rial = amount_toman * 10
        payload = {
            "ApiKey": self.api_key,
            "Hash_id": invoice_id,
            "Amount": amount_rial,
            "CallbackURL": callback_url
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if str(data.get('status')) == "100":
                        return {
                            'success': True,
                            'payment_url_web': data.get('payment_url_web'),
                            'payment_url_bot': data.get('payment_url_bot'),
                            'authority': data.get('Authority')
                        }
                text = await response.text()
                return {'success': False, 'error': text}
                
    async def verify_payment(self, authority: str, invoice_id: str):
        url = "https://tetra98.com/api/verify"
        payload = {
            "ApiKey": self.api_key,
            "authority": authority
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if str(data.get('status')) == "100":
                        verified_hash = data.get('hash_id') or data.get('hashid')
                        if not verified_hash or verified_hash == invoice_id:
                            return True
                return False
