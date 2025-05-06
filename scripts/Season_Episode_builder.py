import os
import json
import argparse
import logging
from datetime import datetime
import importlib
import sys
from pathlib import Path
from configparser import ConfigParser

# Defines the script's version, used in logs and for tracking changes.
__version__ = "1.0.10"

# Stores the changelog, documenting updates and fixes for each version.
# Helps track changes like provider loading improvements or bug fixes.
CHANGELOG = """
1.0.10 (2025-05-02):
- Fixed class name mismatch for tvmazec_provider (TvMazeProvider instead of TvmazeProvider)
- Added provider_class_names mapping to handle specific class names
- Ensure tmp/ folder exists before fetching metadata
- Added detailed error logging for function-based provider get_metadata() calls
1.0.9 (2025-05-01):
- Updated load_providers() to support class-based (<name>c_provider, e.g., tvmazec_provider) and function-based (<name>f_provider, e.g., tvmazef_provider) providers
- Class-based providers use get_series_metadata(series_name), return metadata directly
- Function-based providers use get_metadata(series_name, config), read tmp/providerf_<name>.json
- Prefix provider names in JSON output with providerc_ or providerf_ for clarity
- Added tvmazec_provider, kept tvmazef_provider, tmdbf_provider, traktf_provider, rotten_tomatoesf_provider
1.0.8 (2025-05-01):
- Updated load_providers() to use function-based providers (get_metadata) instead of classes
- Pass ConfigParser object to get_metadata()
1.0.7 (2025-05-01):
- Updated load_providers() to use class names (TvMazeProvider, TmdbProvider, TraktProvider, RottenTomatoesProvider)
1.0.6 (2025-04-30):
- Fixed provider imports by adding scripts/ to sys.path and using absolute paths
- Added __init__.py to scripts/ for package recognition
1.0.5 (2025-04-30):
- Fixed load_paths() to skip comments and blank lines in paths.txt
- Added logging for invalid provider entries
1.0.4 (2025-04-30):
- Updated to read [meta_providers] from paths.txt, supporting enabled/disabled status
1.0.3 (2025-04-30):
- Improved provider loading with detailed error logging
- Added support for flexible provider class names
- Ensured scripts/providers/ is a module with __init__.py
1.0.2 (2025-04-30):
- Updated provider imports to use scripts.providers.<provider_name>_provider
1.0.1 (2025-04-30):
- Updated to load paths.txt from config/ directory
1.0.0 (2025-04-30):
- Updated to use new folder structure: data/<series_slug>/ for JSON, logs/<series_slug>/ for logs
- Read JSON_FOLDER and LOG_PATH from paths.txt
- Added --series argument for specific series
- Standardized series slug (lowercase, underscore)
- Dynamically load providers from paths.txt [providers] section
0.9.2 (2025-04-01):
- Improved provider metadata fetching
- Initial version
"""

def setup_logging(series_name):
    # Sets up logging to record script activity (e.g., provider loads, errors).
    # Creates a log file specific to the series in logs/<series_slug>/.
    # How: Converts series name to a slug (lowercase, spaces to underscores),
    # creates the log directory if it doesn’t exist, and configures logging to
    # write to season_episode_builder.log with timestamps.
    series_slug = series_name.lower().replace(" ", "_")
    log_dir = os.path.join("logs", series_slug)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "season_episode_builder.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # Returns the slug for use in other functions (e.g., saving JSON).
    return series_slug

def load_paths():
    # Loads configuration from config/paths.txt, including provider settings and folders.
    # How: Uses ConfigParser to read paths.txt, which has sections like [general],
    # [library_paths], and [meta_providers]. Extracts folder paths (e.g., JSON_FOLDER)
    # and enabled providers (e.g., providerc_tvmaze=enabled). Logs provider additions
    # and errors. Returns paths dict, provider list with priorities, and config object.
    paths = {}
    providers = []
    config = ConfigParser()
    paths_file = os.path.join("config", "paths.txt")
    try:
        config.read(paths_file)
        for section in config.sections():
            if section in ("library_paths", "general"):
                for key, value in config[section].items():
                    paths[key] = value
            elif section == "meta_providers":
                for key, value in config[section].items():
                    if value.lower() == "enabled":
                        providers.append((key, len(providers) + 1))
                        logging.info(f"Added provider: {key} (priority {len(providers)})")
                    else:
                        logging.warning(f"Skipping invalid provider entry: {key} = {value}")
    except Exception as e:
        logging.error(f"Failed to read paths.txt at {paths_file}: {str(e)}")
        raise
    # Sets default JSON_FOLDER to "data" if not specified.
    paths["JSON_FOLDER"] = paths.get("JSON_FOLDER", "data")
    paths["LOG_PATH"] = paths.get("LOG_PATH", "logs")
    logging.info(f"Loaded {len(providers)} provider configs from paths.txt")
    return paths, providers, config

def load_providers(provider_configs, config):
    # Loads provider scripts (class-based or function-based) dynamically.
    # How: Iterates through provider configs from paths.txt (e.g., providerc_tvmaze).
    # Determines provider type (class or function) from the prefix (providerc_ or providerf_).
    # Imports the provider module (e.g., providers.tvmazec_provider) and loads the class
    # or function. Logs successes and failures. Returns a list of provider instances,
    # types, names, and priorities.
    providers = []
    script_dir = Path(__file__).parent
    sys.path.append(str(script_dir))

    # Maps provider names to their class names (e.g., tvmaze -> TvMazeProvider).
    # Fixes mismatches like TvMazeProvider vs. TvmazeProvider (v1.0.10 changelog).
    provider_class_names = {
        "tvmaze": "TvMazeProvider",
        "tmdb": "TmdbProvider",
        "trakt": "TraktProvider",
        "rotten_tomatoes": "RottenTomatoesProvider"
    }

    for provider_key, priority in provider_configs:
        # Parses provider key to determine type and name (e.g., providerc_tvmaze -> tvmaze, class).
        if provider_key.startswith("providerc_"):
            provider_name = provider_key.replace("providerc_", "")
            provider_type = "class"
            module_name = f"{provider_name}c_provider"
        elif provider_key.startswith("providerf_"):
            provider_name = provider_key.replace("providerf_", "")
            provider_type = "function"
            module_name = f"{provider_name}f_provider"
        else:
            logging.error(f"Invalid provider key: {provider_key}. Must start with providerc_ or providerf_")
            continue

        provider_instance = None

        # Attempts to load the provider module and instance.
        try:
            module_path = f"providers.{module_name}"
            logging.info(f"Attempting to import {module_path}")
            module = importlib.import_module(module_path)

            if provider_type == "class":
                # For class-based providers, gets the class (e.g., TvMazeProvider) and creates an instance.
                class_name = provider_class_names.get(provider_name, f"{provider_name.capitalize()}Provider")
                provider_class = getattr(module, class_name, None)
                if provider_class:
                    provider_instance = provider_class(config)
                    logging.info(f"Loaded class-based provider: providerc_{provider_name} (priority {priority})")
                else:
                    logging.error(f"No class {class_name} found in {module_path}")
                    continue
            else:
                # For function-based providers, gets the get_metadata function.
                get_metadata_func = getattr(module, "get_metadata", None)
                if get_metadata_func:
                    provider_instance = get_metadata_func
                    logging.info(f"Loaded function-based provider: providerf_{provider_name} (priority {priority})")
                else:
                    logging.error(f"No get_metadata function found in {module_path}")
                    continue

            providers.append((provider_instance, provider_type, provider_name, priority))

        except (ImportError, AttributeError) as e:
            logging.error(f"Failed to load provider {provider_key}: {str(e)}")

    return providers

def fetch_metadata(series_name, providers, config):
    # Fetches metadata from all providers and merges it into a single structure.
    # How: Initializes a metadata dict with series_name and empty seasons.
    # Ensures the temp folder (from paths.txt) exists. For each provider:
    # - Class-based: Calls get_series_metadata, gets data directly.
    # - Function-based: Calls get_metadata, reads tmp/providerf_<name>.json.
    # Merges seasons and episodes, logs progress, and sorts the result.
    metadata = {"series_name": series_name, "seasons": []}
    temp_folder = config["general"]["TEMP_FOLDER"]

    # Creates temp folder if it doesn’t exist (v1.0.10 fix).
    os.makedirs(temp_folder, exist_ok=True)
    logging.info(f"Ensured temp folder exists: {temp_folder}")

    for provider_instance, provider_type, provider_name, priority in providers:
        provider_key = f"provider{provider_type[0]}_{provider_name}"
        logging.info(f"Fetching metadata from provider: {provider_key} ({provider_type})")
        try:
            if provider_type == "class":
                # Calls the provider’s get_series_metadata method (e.g., TvMazeProvider.get_series_metadata).
                provider_data = provider_instance.get_series_metadata(series_name)
            else:
                # Calls the provider’s get_metadata function, which writes to a temp file.
                try:
                    provider_instance(series_name, config)
                except Exception as e:
                    logging.error(f"Error in {provider_key} get_metadata(): {str(e)}")
                    continue
                temp_file = os.path.join(temp_folder, f"providerf_{provider_name}.json")
                if os.path.exists(temp_file):
                    with open(temp_file, "r", encoding="utf-8") as f:
                        provider_data = json.load(f)
                else:
                    logging.warning(f"No temp file found for providerf_{provider_name} at {temp_file}")
                    continue

            # Merges provider data into metadata, combining seasons and episodes.
            for season_num, episodes in provider_data.get("seasons", {}).items():
                season_num = int(season_num)
                existing_season = next((s for s in metadata["seasons"] if s["season_number"] == season_num), None)
                if not existing_season:
                    metadata["seasons"].append({
                        "season_number": season_num,
                        "episodes": episodes
                    })
                else:
                    existing_season["episodes"].extend(episodes)

            logging.info(f"Processed metadata from {provider_key} ({provider_type})")

        except Exception as e:
            logging.error(f"Error fetching from {provider_key} ({provider_type}): {str(e)}")

    # Sorts seasons by number and episodes by episode number for consistency.
    metadata["seasons"].sort(key=lambda x: x["season_number"])
    for season in metadata["seasons"]:
        season["episodes"].sort(key=lambda x: x["episode_number"])

    return metadata

def save_metadata(series_name, metadata, json_folder):
    # Saves the merged metadata to data/<series_slug>/<series_name>.json.
    # How: Creates the output directory (e.g., data/the_a_team/), writes the metadata
    # as JSON with indentation, and logs the save. Uses the series slug for the folder.
    series_slug = series_name.lower().replace(" ", "_")
    output_dir = os.path.join(json_folder, series_slug)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{series_name}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logging.info(f"Saved metadata to {output_path}")

def main():
    # Entry point for the script, handling command-line arguments and workflow.
    # How: Parses the --series argument (e.g., "The A-Team"), sets up logging,
    # loads paths and providers, fetches metadata, and saves it. Logs the start
    # and checks for provider loading success.
    parser = argparse.ArgumentParser(description="Build episode metadata for a series")
    parser.add_argument("--series", required=True, help="Name of the series (e.g., The A-Team)")
    args = parser.parse_args()

    series_slug = setup_logging(args.series)
    logging.info(f"=== Season Episode Builder v{__version__} Started for '{args.series}' ===")

    paths, provider_configs, config = load_paths()
    json_folder = paths["JSON_FOLDER"]
    logging.info(f"Using JSON_FOLDER = {json_folder}")

    providers = load_providers(provider_configs, config)
    if not providers:
        logging.error("No providers loaded. Exiting.")
        return

    metadata = fetch_metadata(args.series, providers, config)
    save_metadata(args.series, metadata, json_folder)

if __name__ == "__main__":
    main()