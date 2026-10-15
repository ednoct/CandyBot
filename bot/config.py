"""
config.py
---------
Module containing functionalities for config.
"""
# === IMPORTS AND ENV LOAD ===
# === IMPORTS ===
import os
from dotenv import load_dotenv

load_dotenv()

# === BOT CONFIGURATION ===
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

def _parse_admin_ids(raw_str: str) -> list[int]:
    cleaned = raw_str.replace('"', '').replace("'", '').replace(';', ',').replace(' ', ',')
    ids = []
    for part in cleaned.split(','):
        part = part.strip()
        if part.isdigit():
            val = int(part)
            if val not in ids:
                ids.append(val)
    return ids

ADMIN_IDS = _parse_admin_ids(os.getenv('ADMIN_IDS', ''))
WEBHOOK_DOMAIN = os.getenv('WEBHOOK_DOMAIN', 'localhost')

# === WEB CONFIGURATION ===
WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
WEB_PORT = int(os.getenv('WEB_PORT', 8080))
CORS_ORIGIN = os.getenv('CORS_ORIGIN', '*')