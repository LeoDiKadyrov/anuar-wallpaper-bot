# app/config.py
import os
import logging
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env variables immediately
load_dotenv(os.path.join(BASE_DIR, ".env"))

class ConfigError(Exception):
    """Exception raised for missing configuration."""
    pass

def _require_env(key: str) -> str:
    """Fail fast if required env var is missing."""
    val = os.getenv(key)
    if not val:
        raise ConfigError(f"Missing required environment variable: {key}")
    return val

def _resolve_path(path: str) -> str:
    """
    Превращает путь в абсолютный относительно BASE_DIR, 
    если он еще не является абсолютным.
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path
    # Если путь начинается с ./, убираем это для чистоты, хотя join переварит и так
    if path.startswith("./"):
        path = path[2:]
    return os.path.join(BASE_DIR, path) 

# --- Configuration ---

# Required Secrets
TELEGRAM_TOKEN = _require_env("TELEGRAM_TOKEN")
GOOGLE_API_KEY = _require_env("GOOGLE_API_KEY") # For Gemini
SPREADSHEET_NAME = _require_env("SPREADSHEET_NAME")

# Admin Settings (for error notifications in Phase 3)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# Optional / Defaults
_raw_creds = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
GOOGLE_CREDENTIALS_JSON = _resolve_path(_raw_creds)
STT_BACKEND = os.getenv("STT_BACKEND", "vosk")

# Paths
# Assuming running from project root, models are in app/services/models/
_raw_model = os.getenv("VOSK_MODEL_PATH", os.path.join("app", "services", "models", "vosk-model-small-ru-0.22"))
VOSK_MODEL_PATH = _resolve_path(_raw_model)

# --- Centralized Logging Configuration ---
def setup_logging():
    """Configures standard logging for the application."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    # Reduce noise from third-party libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logging.info(f"Config loaded. Credentials path: {GOOGLE_CREDENTIALS_JSON}")