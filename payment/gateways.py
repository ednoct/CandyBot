"""
This module corresponds to the 'payment/gateways.py' branch in the candy_architecture.md map.
Contains the base PaymentGateway interface and specific online gateways like FrenzyExGateway.
"""
# === IMPORTS ===
import aiohttp
import uuid
import hashlib
import hmac

# === BASE GATEWAY CLASS ===
class PaymentGateway:
    """Class representing PaymentGateway."""
    async def create_payment(self, amount: int, description: str, callback_url: str):
        """Handles create payment."""
        raise NotImplementedError
        
    async def verify_payment(self, payment_id: str, amount: int, **kwargs):
        """Handles verify payment."""
        raise NotImplementedError

class FrenzyExGateway(PaymentGateway):
    """Class representing FrenzyExGateway."""
    def __init__(self, api_key: str, base_url: str = "https://frenzy.fastsnap.info"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        
    async def create_payment(self, order_id: str, amount: int, callback_url: str, amount_ccy: str = "TMN", description: str = ""):
        """Handles create payment."""
        url = f"{self.base_url}/api/v1/payment-requests"
        payload = {
            "amount": amount,
            "amount_ccy": amount_ccy,
            "order_ref": order_id,
            "description": description,
            "payment_method": "auto",
            "callback_url": callback_url
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # httpx for better async support, aiohttp also fine
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    # Example response body fields: request_id, status, order_ref, checkout_url, pay_url, bot_pay_url
                    return {
                        'success': True,
                        'request_id': data.get('request_id'),
                        'payment_url_web': data.get('checkout_url'),
                        'payment_url_bot': data.get('bot_pay_url') or data.get('pay_url')
                    }
                else:
                    return {'success': False, 'error': f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}
                
    async def get_payment_status(self, request_id: str):
        """Retrieves payment status."""
        url = f"{self.base_url}/api/v1/payment-requests/{request_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return {'success': True, 'status': data.get('status')} # paid, expired, canceled
                return {'success': False, 'error': f"HTTP {response.status_code}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def cancel_payment(self, request_id: str):
        """Cancels a payment request."""
        url = f"{self.base_url}/api/v1/payment-requests/{request_id}/cancel"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers)
                if response.status_code == 200:
                    return True
                return False
        except:
            return False
