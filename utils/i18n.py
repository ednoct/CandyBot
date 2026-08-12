# === IMPORTS ===
import json
import os
from pathlib import Path

# === LOCALIZATION (I18N) MANAGER ===
class I18nManager:
    def __init__(self, file_path: str = None):
        if not file_path:
            # Default to locales_fa.json in the project root
            base_dir = Path(__file__).parent.parent
            file_path = base_dir / 'locales_fa.json'
            
        self.file_path = file_path
        self._texts = {}
        self.load_texts()
        
    def load_texts(self):
        """Loads the JSON dictionary into memory."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._texts = json.load(f)
        except Exception as e:
            print(f"[I18N ERROR] Failed to load texts from {self.file_path}: {e}")
            self._texts = {}
            
    def get(self, *keys, default=""):
        """
        Safely retrieves a nested key from the text dictionary.
        Usage: get('User', 'Menu', 'start_text')
        """
        current = self._texts
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current if isinstance(current, str) else default

# Singleton instance
i18n = I18nManager()
