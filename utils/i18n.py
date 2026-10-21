"""
i18n.py
-------
Module containing functionalities for i18n.
"""

# === IMPORTS ===
import json
from pathlib import Path


# === LOCALIZATION (I18N) MANAGER ===
class I18nManager:
    """Class representing I18nManager."""

    def __init__(self, file_path: str = None, default_lang: str = "fa"):
        if not file_path:
            base_dir = Path(__file__).parent.parent
            file_path = base_dir / 'locales_fa.json'

        self.file_path = file_path
        self.default_lang = default_lang
        self._texts = {}
        self.load_texts()

    def load_texts(self):
        """Loads the JSON dictionary into memory."""
        try:
            with open(self.file_path, 'r', encoding='utf-8-sig') as f:
                self._texts = json.load(f)
        except Exception as e:
            print(f"[I18N ERROR] Failed to load texts from {self.file_path}: {e}")
            self._texts = {}

    def get(self, *keys, default=""):
        """
        Safely retrieves a nested key from the text dictionary.
        Supports both get('user', 'welcome') and get('fa', 'user', 'welcome').
        """
        if not keys or not isinstance(self._texts, dict):
            return default

        current = self._texts
        # Automatic language root unwrapping if first key is not at top-level
        if keys[0] not in current and self.default_lang in current and isinstance(current[self.default_lang], dict):
            current = current[self.default_lang]

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current if isinstance(current, str) else default


# Singleton instance
i18n = I18nManager()