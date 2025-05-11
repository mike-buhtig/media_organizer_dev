# Season_Episode_builder.py v1.0.12
# Fetches metadata from providers and merges into a single JSON file
#
# Requirements:
# - pip install requests
#
# Change Log:
# [1.0.0] - 2025-05-01: Initial version
# [1.0.10] - 2025-05-09: Added dynamic provider loading, list-based seasons
# [1.0.11] - 2025-05-17: Added version logging, detailed import error logging, comprehensive comments, fixed non-boolean config parsing
# [1.0.12] - 2025-05-18: Separated builder and provider loggers, ensured provider logs go to provider.log only

import argparse
import importlib
import json
import logging
import os
import sys
import traceback
from configparser import ConfigParser

# Initialize separate loggers
builder_logger = logging.getLogger('Season_Episode_builder.builder')
provider_logger = logging.getLogger('Season_Episode_builder.provider')

# Script version
SCRIPT_VERSION = "1.0.12"

def generate_slug(name: str) -> str:
    """Generate a slug from series name for file paths and logging.
    
    Args:
        name (str): Series name (e.g., "Ax Men").
    
    Returns:
        str: Lowercase slug with spaces, quotes, and apostrophes removed (e.g., "ax_men").
    """
    return name.lower().replace(' ', '_').replace("'", "").replace('"', '')

def main():
    """Main function to fetch and merge metadata from providers.
    
    Reads series name from command-line argument, loads configuration from paths.txt,
    sets up separate builder and provider logging, fetches metadata from enabled providers,
    merges data, and writes output JSON to data/<series_slug>/<series_name>.json.
    
    Args:
        None (uses sys.argv for --series argument).
    
    Outputs:
        - JSON file at data/<series_slug>/<series_name>.json with merged metadata.
        - Builder logs to logs/<series_slug>/<series_slug>_builder.log.
        - Provider logs to logs/<series_slug>/<series_slug>_provider.log.
    
    Raises:
        SystemExit: If required arguments are missing.
        Exception: For provider import or file operation failures (logged).
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Fetch and merge series metadata.')
    parser.add_argument('--series', required=True, help='Series name (e.g., "Ax Men")')
    args = parser.parse_args()
    series_name = args.series
    series_slug = generate_slug(series_name)
    
    # Log script version and start (builder logger)
    builder_logger.info(f"[builder] Season_Episode_builder.py v{SCRIPT_VERSION} starting")
    builder_logger.info(f"[builder] Starting metadata fetch for series: {series_name}")
    builder_logger.debug(f"[builder] Python executable: {sys.executable}")
    builder_logger.debug(f"[builder] sys.path: {sys.path}")
    builder_logger.debug(f"[builder] Current directory: {os.getcwd()}")

    # Load configuration from paths.txt
    config = ConfigParser()
    config.read('config/paths.txt')
    builder_logger.debug(f"[builder] Loaded configuration from config/paths.txt")

    # Set up logging directories
    log_dir = os.path.join(config['general']['LOG_PATH'], series_slug)
    os.makedirs(log_dir, exist_ok=True)
    builder_logger.debug(f"[builder] Created log directory: {log_dir}")

    # Builder log handler
    builder_log_file = os.path.join(log_dir, f"{series_slug}_builder.log")
    builder_handler = logging.FileHandler(builder_log_file, mode='a')
    builder_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    builder_logger.addHandler(builder_handler)
    builder_logger.debug(f"[builder] Added builder log handler: {builder_log_file}")

    # Provider log handler
    provider_log_file = os.path.join(log_dir, f"{series_slug}_provider.log")
    provider_handler = logging.FileHandler(provider_log_file, mode='a')
    provider_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    provider_logger.addHandler(provider_handler)
    builder_logger.debug(f"[builder] Added provider log handler: {provider_log_file}")

    # Console log handler (for both loggers)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
    builder_logger.addHandler(console_handler)
    provider_logger.addHandler(console_handler)
    builder_logger.debug(f"[builder] Added console log handler")

    # Fetch metadata from enabled providers
    provider_data = {}
    for provider_name in config['meta_providers']:
        # Check if provider is enabled (handle non-boolean values)
        provider_enabled = config['meta_providers'].get(provider_name, '').lower()
        if provider_enabled in ('true', 'yes', 'on', '1', 'enabled'):
            builder_logger.info(f"[builder] Fetching metadata from provider: {provider_name}")
            try:
                # Check if provider file exists
                provider_path = os.path.join('scripts', 'providers', f"{provider_name}.py")
                builder_logger.debug(f"[builder] Checking existence of {provider_path}")
                if not os.path.exists(provider_path):
                    builder_logger.error(f"[builder] Provider file {provider_path} does not exist")
                    raise FileNotFoundError(f"Provider file {provider_path} does not exist")
                
                # Import provider module
                builder_logger.debug(f"[builder] Attempting to import providers.{provider_name} from {provider_path}")
                module = importlib.import_module(f"providers.{provider_name}")
                
                # Execute provider's get_metadata
                module.get_metadata(series_name, config)
                builder_logger.info(f"[builder] Provider {provider_name} executed successfully")
                
                # Load provider's JSON output
                temp_path = os.path.join(config['general']['TEMP_FOLDER'], f"{provider_name}.json")
                if os.path.exists(temp_path):
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        provider_data[provider_name] = json.load(f)
                    builder_logger.info(f"[builder] Successfully loaded data from {temp_path}")
                else:
                    builder_logger.warning(f"[builder] No data file found for provider {provider_name} at {temp_path}")
            
            except Exception as e:
                builder_logger.error(f"[builder] Failed to process provider {provider_name}: {str(e)}")
                builder_logger.debug(f"[builder] Traceback: {traceback.format_exc()}")
                continue

    # Merge provider data into single output
    output = {
        "series_name": series_name,
        "seasons": []
    }
    for provider in ['tvmaze', 'tmdb', 'trakt', 'rotten_tomatoes']:
        if provider in provider_data:
            builder_logger.debug(f"[builder] Merging data from provider: {provider}")
            for season in provider_data[provider].get('seasons', []):
                output['seasons'].append(season)
    
    # Write merged output to JSON
    output_dir = os.path.join(config['general']['JSON_FOLDER'], series_slug)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{series_name}.json")
    builder_logger.debug(f"[builder] Writing output to: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    builder_logger.info(f"[builder] Successfully wrote output to: {output_path}")

if __name__ == "__main__":
    main()