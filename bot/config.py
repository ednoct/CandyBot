# === IMPORTS AND ENV LOAD ===
import os
from dotenv import load_dotenv

load_dotenv()

# === BOT CONFIGURATION ===
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id.isdigit()]
WEBHOOK_DOMAIN = os.getenv('WEBHOOK_DOMAIN', 'localhost')

# === WEB CONFIGURATION ===
WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
WEB_PORT = int(os.getenv('WEB_PORT', 8080))
CORS_ORIGIN = os.getenv('CORS_ORIGIN', '*')