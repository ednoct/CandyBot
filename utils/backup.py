# === IMPORTS ===
import asyncio
import logging
import zipfile
import os
import shutil
from datetime import datetime
from ..database import db_manager

# === BACKUP UTILITY ===
async def create_database_backup() -> str:
    """
    Creates a zip backup of the SQLite database.
    Replaces legacy backupbot.php which relied on mysqldump.
    Returns the path to the zip file.
    """
    try:
        db_path = db_manager.DB_PATH
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found at {db_path}")

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        zip_filename = f"candy_backup_{timestamp}.zip"
        zip_path = os.path.join(backup_dir, zip_filename)

        # We can safely zip the SQLite db file. For higher consistency, we could use sqlite3 backup API.
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(db_path, arcname=f"candy.db")

        logging.info(f"Database backup created successfully at {zip_path}")
        return zip_path
    except Exception as e:
        logging.error(f"Failed to create database backup: {e}")
        raise e
