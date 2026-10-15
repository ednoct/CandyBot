"""
backup.py
---------
Module containing functionalities for backup.
"""
# === IMPORTS ===
import asyncio
import logging
import zipfile
import os
import shutil
from datetime import datetime
from database import db_manager

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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_dir = os.path.join(base_dir, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        zip_filename = f"candy_backup_{timestamp}.zip"
        zip_path = os.path.join(backup_dir, zip_filename)

        # Flush any uncommitted SQLite WAL pages to ensure consistent snapshot
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception as e:
            logging.warning(f"WAL checkpoint before backup warning: {e}")

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(db_path, arcname=os.path.basename(db_path))

        logging.info(f"Database backup created successfully at {zip_path}")
        return zip_path
    except Exception as e:
        logging.error(f"Failed to create database backup: {e}")
        raise e
