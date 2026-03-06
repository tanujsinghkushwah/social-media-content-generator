"""Test Firebase Remote Config integration."""

import asyncio
import traceback

import firebase_admin
from firebase_admin import credentials, remote_config

EXPECTED_KEYS_TO_TEST = [
    'IMAGE_MODEL',
    'CONTENT_MODEL',
    'OPENROUTER_API',
    'CLOUDFLARE_ACCOUNT_ID',
    'CLOUDFLARE_API_TOKEN',
    'GSHEET_ID',
    'GOOGLE_DRIVE_FOLDER_ID',
    'POST_COUNT',
    'LLM_CALL_DELAY_SECONDS',
]


def initialize_firebase():
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred)


def get_and_print_config_values():
    try:
        initialize_firebase()
        
        local_test_defaults = {
            "POST_COUNT": "3",
            "LLM_CALL_DELAY_SECONDS": "15",
        }
        print(f"Initializing ServerTemplate with local_test_defaults: {local_test_defaults}")
        template = remote_config.init_server_template(default_config=local_test_defaults)
        
        print("\nLoading Remote Config template from Firebase backend...")
        asyncio.run(template.load())
        print("Template loaded from backend.")

        print("\nEvaluating the loaded template to get effective values...")
        evaluated_config = template.evaluate()

        print("\nAttempting to get values for EXPECTED_KEYS_TO_TEST:")
        found_any_remote_key = False

        for key in EXPECTED_KEYS_TO_TEST:
            try:
                value = evaluated_config.get_string(key)
                source = evaluated_config.get_value_source(key)
                display_value = value[:20] + "..." if len(value) > 20 else value
                print(f"  - Key '{key}': '{display_value}' (Source: {source})")
                if source == 'remote':
                    found_any_remote_key = True
            except ValueError as ve:
                print(f"  - Key '{key}': Could not get as STRING. Error: {ve}")
            except Exception as e:
                print(f"  - Key '{key}': UNEXPECTED error. Error: {e}")
        
        if not found_any_remote_key:
            print("\nWARNING: No keys were reported with source 'remote'.")
            print("Ensure server-side Remote Config in Firebase console has parameters published.")
            
        return True

    except Exception as e:
        print(f"\nMAJOR ERROR in test script execution: {e}")
        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    print("--- Firebase Remote Config Test Script ---")
    success = get_and_print_config_values()
    if success:
        print("\n--- Test script finished. Please review the output above. ---")
    else:
        print("\n--- Test script FAILED due to a major error. Please review errors. ---")
