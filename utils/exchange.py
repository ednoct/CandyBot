"""
exchange.py
-----------
Module containing functionalities for exchange.
"""
# === IMPORTS ===
import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

# === CONSTANTS ===
# Cloaked User-Agent to mimic a standard Google Chrome browser on Windows 10/11
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'

# === EXCHANGE RATE FETCHERS ===
async def get_arz_usdt_rate() -> int | None:
    """
    Fetches the current USDT/IRT exchange rate using multiple providers with fallback.
    Translated from legacy PHP script.
    """
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {'User-Agent': USER_AGENT}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        # --- Provider 1: Exir (Main) ---
        try:
            async with session.get('https://api.exir.io/v2/tickers', ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'usdt-irt' in data and 'last' in data['usdt-irt']:
                        raw = str(data['usdt-irt']['last']).replace(',', '')
                        toman_price = int(float(raw))
                        if toman_price > 0:
                            return toman_price
        except Exception as e:
            logger.warning(f"Exir API failed: {e}")

        # --- Provider 2: Bitpin (Fallback 1) ---
        try:
            async with session.get('https://api.bitpin.org/api/v1/mkt/tickers/', ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        for market in data:
                            if market.get('symbol') == 'USDT_IRT':
                                raw = str(market.get('price', '0')).replace(',', '')
                                toman_price = int(float(raw))
                                if toman_price > 0:
                                    return toman_price
        except Exception as e:
            logger.warning(f"Bitpin API failed: {e}")

        # --- Provider 3: Wallex (Fallback 2) ---
        try:
            async with session.get('https://api.wallex.ir/hector/web/v1/markets', ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get('result', {}).get('markets', [])
                    # Wallex sometimes returns a dict where keys are symbols
                    if isinstance(markets, dict):
                        markets = markets.values()
                        
                    for market in markets:
                        if market.get('symbol') == 'USDTTMN':
                            raw = str(market.get('price', '0')).replace(',', '')
                            toman_price = int(float(raw))
                            if toman_price > 0:
                                return toman_price
        except Exception as e:
            logger.warning(f"Wallex API failed: {e}")

    # Return None if all endpoints fail
    return None


async def get_gram_irt_price() -> int | None:
    """
    Fetches the current TON/IRT (GRAM) exchange rate using DiaData and local USDT rate.
    """
    usdt_irt_price = await get_arz_usdt_rate()
    if usdt_irt_price is None:
        return None

    timeout = aiohttp.ClientTimeout(total=5)
    headers = {'User-Agent': USER_AGENT}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        try:
            url = 'https://api.diadata.org/v1/assetQuotation/Ton/0x0000000000000000000000000000000000000000'
            async with session.get(url, ssl=False) as resp:
                if resp.status == 200:
                    ton_data = await resp.json()
                    if 'Price' in ton_data:
                        ton_usd_price = float(ton_data['Price'])
                        gram_irt_price = round(ton_usd_price * usdt_irt_price)
                        return gram_irt_price
        except Exception as e:
            logger.warning(f"DiaData API failed: {e}")

    return None