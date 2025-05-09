# Season_Episode_builder.py v1.0.14
# Total rewrite of the script to remove class providers, and reconfigure the function providers for metadata
import argparse
import configparser
import importlib
import json
import os
import re
from datetime import datetime

def slugify(text):
    """Convert text to a slug (e.g., 'Ax Men' -> 'ax_men')."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '_', text)
    return text.strip('_')

def log_message(log_path, message):
    """Log a message to the specified log file with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")

def load_provider_data(temp_file, provider_name, log_path):
    """Load provider data from tmp/<name>.json if it exists."""
    if not os.path.exists(temp_file):
        log_message(log_path, f"No data file found for provider {provider_name}: {temp_file}")
        return None
    try:
        with open(temp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log_message(log_path, f"Successfully loaded data from {temp_file}")
        return data
    except json.JSONDecodeError as e:
        log_message(log_path, f"Error decoding JSON from {temp_file}: {e}")
        return None

def merge_provider_data(all_data, provider_data, provider_name):
    if not provider_data or 'seasons' not in provider_data:
        return
    all_data.setdefault('series_name', provider_data.get('title', ''))
    all_data.setdefault('seasons', [])
    
    # Track seasons by number
    season_map = {s['season_number']: s for s in all_data['seasons']}
    
    for season in provider_data.get('seasons', []):
        season_num = season.get('season_number')
        if season_num is None:
            continue
            
        # Get or create season
        if season_num not in season_map:
            season_map[season_num] = {'season_number': season_num, 'episodes': []}
            all_data['seasons'].append(season_map[season_num])
        season_data = season_map[season_num]
        
        for episode in season.get('episodes', []):
            ep_num = episode.get('episode_number')
            if not ep_num:
                continue
                
            # Find or create episode
            ep_data = next((ep for ep in season_data['episodes'] if ep['episode_number'] == ep_num), None)
            if not ep_data:
                ep_data = {
                    'episode_number': ep_num,
                    'titles': {},
                    'overviews': {},
                    'ids': {},
                    'air_date': {}
                }
                season_data['episodes'].append(ep_data)
            
            # Merge provider data, preserving existing keys (for precedence)
            ep_data['titles'].setdefault(provider_name, episode.get('titles', {}).get(provider_name))
            ep_data['overviews'].setdefault(provider_name, episode.get('overviews', {}).get(provider_name))
            ep_data['ids'].setdefault(provider_name, episode.get('ids', {}).get(provider_name))
            ep_data['air_date'].setdefault(provider_name, episode.get('air_date'))

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Fetch and merge TV series metadata.")
    parser.add_argument('--series', required=True, help="Name of the series (e.g., 'Ax Men')")
    args = parser.parse_args()
    series_name = args.series

    # Load configuration
    config = configparser.ConfigParser()
    config_path = 'config/paths.txt'
    if not os.path.exists(config_path):
        print(f"Configuration file not found: {config_path}")
        return
    config.read(config_path)

    # Validate configuration
    if 'general' not in config or 'meta_providers' not in config or 'series' not in config:
        print("Missing required sections in paths.txt: [general], [meta_providers], [series]")
        return

    json_folder = config['general'].get('JSON_FOLDER', 'data')
    temp_folder = config['general'].get('TEMP_FOLDER', 'tmp')
    log_folder = config['general'].get('LOG_PATH', 'logs')

    # Validate series name against [series] section
    series_found = False
    for key, value in config['series'].items():
        if key.startswith('series_name_') and value == series_name:
            series_found = True
            break
    if not series_found:
        print(f"Series '{series_name}' not found in [series] section of paths.txt")
        return

    # Initialize paths
    series_slug = slugify(series_name)
    log_path = os.path.join(log_folder, series_slug, 'builder.log')
    output_path = os.path.join(json_folder, series_slug, f"{series_name}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    os.makedirs(temp_folder, exist_ok=True)

    log_message(log_path, f"Starting metadata fetch for series: {series_name}")

    # Initialize output data
    output_data = {
        'series_name': series_name,
        'seasons': []
    }

    # Process providers
    provider_data_found = False
    for provider_name, status in config['meta_providers'].items():
        if status.lower() != 'enabled':
            log_message(log_path, f"Skipping disabled provider: {provider_name}")
            continue

        log_message(log_path, f"Fetching metadata from provider: {provider_name}")
        temp_file = os.path.join(temp_folder, f"{provider_name}.json")

        # Delete existing temp file to ensure fresh data
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                log_message(log_path, f"Deleted existing temp file: {temp_file}")
            except OSError as e:
                log_message(log_path, f"Error deleting temp file {temp_file}: {e}")
                continue

        # Dynamically import provider module
        try:
            module = importlib.import_module(f"providers.{provider_name}")
            get_metadata = getattr(module, 'get_metadata', None)
            if not callable(get_metadata):
                log_message(log_path, f"Provider {provider_name} does not have a valid get_metadata function")
                continue
        except ImportError as e:
            log_message(log_path, f"Failed to import provider {provider_name}: {e}")
            continue

        # Call provider's get_metadata
        try:
            get_metadata(series_name, config)
            log_message(log_path, f"Provider {provider_name} executed successfully")
        except Exception as e:
            log_message(log_path, f"Error executing get_metadata for {provider_name}: {e}")
            continue

        # Load and merge provider data
        provider_data = load_provider_data(temp_file, provider_name, log_path)
        if provider_data:
            merge_provider_data(output_data, provider_data, provider_name)
            provider_data_found = True

    # Check if any data was collected
    if not provider_data_found:
        log_message(log_path, "No provider data available for series: {series_name}")
        print(f"No provider data available for series: {series_name}")
        return

    # Sort seasons and episodes
    output_data['seasons'].sort(key=lambda x: x['season_number'])
    for season in output_data['seasons']:
        season['episodes'].sort(key=lambda x: x['episode_number'])

    # Write output JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        log_message(log_path, f"Successfully wrote output to: {output_path}")
        print(f"Metadata written to: {output_path}")
    except OSError as e:
        log_message(log_path, f"Error writing output to {output_path}: {e}")
        print(f"Error writing output to {output_path}: {e}")

if __name__ == "__main__":
    main()