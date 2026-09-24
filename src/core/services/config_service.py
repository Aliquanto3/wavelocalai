"""
Config Service - Centralized configuration management.
Handles loading YAML/JSON assets to keep code clean.
"""

import logging
import threading
from pathlib import Path
from typing import Any

import yaml

# Global lock for thread safety in Streamlit
_config_lock = threading.Lock()


class ConfigService:
    _instance = None
    _prompts_cache: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            with _config_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Define path relative to project root
        self.config_dir = Path("src/config")
        self.prompts_file = self.config_dir / "prompts.yaml"

    def load_prompts(self) -> dict[str, Any]:
        """
        Loads prompts from YAML. Returns cached version if available.
        """
        if self._prompts_cache:
            return self._prompts_cache

        if not self.prompts_file.exists():
            logging.error(f"Prompts file not found: {self.prompts_file}")
            return {}

        try:
            with open(self.prompts_file, encoding="utf-8") as f:
                self._prompts_cache = yaml.safe_load(f) or {}
            logging.info("✅ Prompts loaded from YAML")
        except Exception as e:
            logging.error(f"Failed to load prompts: {e}")
            return {}

        return self._prompts_cache

    def get_agent_config(self, agent_type: str, key: str) -> dict | None:
        """
        Helper to get specific config.
        Usage: get_agent_config('agent_crew', 'market_analyst')
        """
        data = self.load_prompts()
        return data.get(agent_type, {}).get(key)


# Singleton Accessor
def get_config_service() -> ConfigService:
    return ConfigService()
