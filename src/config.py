"""Configuration management using Firebase Remote Config and environment variables."""

import os
import asyncio
import firebase_admin
from firebase_admin import credentials, remote_config
from dotenv import load_dotenv

from src.constants import ULTIMATE_FALLBACK_DEFAULTS

load_dotenv()


def initialize_firebase_and_load_config():
    """Initialize Firebase and load Remote Config template."""
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred)
    
    print("Initializing Remote Config server template...")
    template = remote_config.init_server_template(default_config=ULTIMATE_FALLBACK_DEFAULTS)
    
    print("Loading Remote Config template from Firebase backend...")
    try:
        asyncio.run(template.load())
        print("Remote Config template loaded successfully.")
    except Exception as e:
        print(f"ERROR loading Remote Config template from backend: {e}")
        print("Proceeding with ULTIMATE_FALLBACK_DEFAULTS.")

    print("Evaluating Remote Config template...")
    return template.evaluate()  # Returns a firebase_admin.remote_config.Config object


def get_config_value(evaluated_config, key, default_value=""):
    """Get config value prioritizing environment variables over Remote Config."""
    env_value = os.getenv(key)
    if env_value:
        return env_value
    try:
        value = evaluated_config.get_string(key)
        return value
    except ValueError:
        return default_value
    except Exception as e:
        print(f"Error fetching '{key}' from evaluated_config: {e}.")
        print(f"Using function default: '{default_value}'.")
        return default_value


def load_config():
    """Load and return all configuration values."""
    evaluated_remote_config = initialize_firebase_and_load_config()
    config = {
        'IMAGE_MODEL': get_config_value(evaluated_remote_config, 'IMAGE_MODEL', ULTIMATE_FALLBACK_DEFAULTS['IMAGE_MODEL']),
        'CONTENT_MODEL': get_config_value(evaluated_remote_config, 'CONTENT_MODEL', ULTIMATE_FALLBACK_DEFAULTS['CONTENT_MODEL']),
        'OPENROUTER_API': get_config_value(evaluated_remote_config, 'OPENROUTER_API', ULTIMATE_FALLBACK_DEFAULTS['OPENROUTER_API']),
        'CLOUDFLARE_ACCOUNT_ID': get_config_value(evaluated_remote_config, 'CLOUDFLARE_ACCOUNT_ID', ULTIMATE_FALLBACK_DEFAULTS['CLOUDFLARE_ACCOUNT_ID']),
        'CLOUDFLARE_API_TOKEN': get_config_value(evaluated_remote_config, 'CLOUDFLARE_API_TOKEN', ULTIMATE_FALLBACK_DEFAULTS['CLOUDFLARE_API_TOKEN']),
        'GSHEET_ID': get_config_value(evaluated_remote_config, 'GSHEET_ID', ULTIMATE_FALLBACK_DEFAULTS['GSHEET_ID']),
        'IMGBB_API_KEY': get_config_value(evaluated_remote_config, 'IMGBB_API_KEY', ULTIMATE_FALLBACK_DEFAULTS['IMGBB_API_KEY']),
        'POST_COUNT': int(get_config_value(evaluated_remote_config, 'POST_COUNT', ULTIMATE_FALLBACK_DEFAULTS['POST_COUNT'])),
        'LLM_CALL_DELAY_SECONDS': int(get_config_value(evaluated_remote_config, 'LLM_CALL_DELAY_SECONDS', ULTIMATE_FALLBACK_DEFAULTS['LLM_CALL_DELAY_SECONDS'])),
    }
    
    return config




