# Season_Episode_builder.py v1.0.20
# [1.0.20] - 2025-05-17: updated code to really be dynamic when loading providers... previous version was hard coded - performed by Gemeni
# [1.0.19] - 2025-05-12: Reverted to v1.0.16, fixed provider execution by removing provider_logger from get_metadata, removed JSON merge fix for rotten_tomatoes legacy format, retained logs/builder.log for verification - Grok 3
# [1.0.18] - 2025-05-12: Reverted provider execution to v1.0.16 (removed provider_logger from get_metadata), kept JSON merge fix for rotten_tomatoes legacy format, retained logs/builder.log for verification - Grok 3
# [1.0.17] - 2025-05-12: Fixed logging to prevent builder logs in provider.log, redirected rotten_tomatoes.py logs to provider.log via provider logger, fixed duplicate logs, retained logs/builder.log for verification - Grok 3
# [1.0.16] - 2025-05-12: Redirected rotten_tomatoes.py logs from logs/builder.log to logs/<series_slug>/<series_slug>_provider.log, retained logs/builder.log for verification - Grok 3
# [1.0.15] - 2025-05-12: Consolidated builder logs to logs/<series_slug>/<series_slug>_builder.log, ensured provider logs go to logs/<series_slug>/<series_slug>_provider.log, retained logs/builder.log for verification - Grok 3
# [1.0.14] - 2025-05-12: Fixed logging to use logs/<series_slug>/*.log, removed tmp/builder.log, separated builder/provider logs, fixed merge to include season 0 and handle rotten_tomatoes JSON errors - Grok 3
# [1.0.13] - 2025-05-12: Fixed merge to include all provider data, corrected logging paths to logs/<series_slug>/*.log - Grok 3
# [1.0.12] - 2025-05-18: Separated builder and provider loggers, ensured provider logs go to provider.log only - Grok 3
# [1.0.11] - 2025-05-17: Added version logging, detailed import error logging, comprehensive comments, fixed non-boolean config parsing - Grok 3
# [1.0.10] - 2025-05-09: Added dynamic provider loading, list-based seasons - Grok 3
# [1.0.0] - 2025-05-01: Initial version

import argparse
import json
import logging
import os
from configparser import ConfigParser
from importlib import import_module

def setup_logging(series_slug: str, log_path: str) -> tuple:
    """Set up separate loggers for builder and provider actions."""
    # Ensure log directory exists
    log_dir = os.path.join(log_path, series_slug)
    os.makedirs(log_dir, exist_ok=True)

    # Builder logger
    builder_logger = logging.getLogger("Season_Episode_builder.builder")
    builder_logger.setLevel(logging.INFO)
    builder_handler = logging.FileHandler(os.path.join(log_dir, f"{series_slug}_builder.log"), mode="a")
    builder_handler.setFormatter(logging.Formatter("[%(asctime)s] [builder] %(message)s"))
    builder_logger.handlers = [builder_handler]  # Clear existing handlers

    # Provider logger
    provider_logger = logging.getLogger("Season_Episode_builder.provider")
    provider_logger.setLevel(logging.INFO)
    provider_handler = logging.FileHandler(os.path.join(log_dir, f"{series_slug}_provider.log"), mode="a")
    provider_handler.setFormatter(logging.Formatter("[%(asctime)s] [provider] %(message)s"))
    provider_logger.handlers = [provider_handler]  # Clear existing handlers

    # Log script version
    builder_logger.info("Season_Episode_builder.py v1.0.19 starting")

    return builder_logger, provider_logger

def merge_provider_data(provider_files: list, output_json: str, config: ConfigParser) -> None:
    """Merge provider JSONs into a single JSON with provider-specific fields, including season 0."""
    merged_data = {"series_name": "", "seasons": []}
    builder_logger = logging.getLogger("Season_Episode_builder.builder")
    provider_logger = logging.getLogger("Season_Episode_builder.provider")

    # Get the list of enabled providers from the config
    providers = []
    for provider in config["meta_providers"]:
        if config["meta_providers"].get(provider) == "enabled":
            providers.append(provider)

    for provider in providers:
        json_file = next((f for f in provider_files if f.endswith(f"{provider}.json")), None)
        if not json_file or not os.path.exists(json_file):
            provider_logger.error(f"Missing or invalid JSON for {provider}")
            continue

        try:
            with open(json_file, "r") as f:
                data = json.load(f)
                provider_logger.info(f"Loaded {provider} JSON")

            # Validate JSON type
            if not isinstance(data, dict):
                provider_logger.error(f"Invalid JSON format for {provider}: expected dict, got {type(data)}")
                continue

            # Set series name from first valid provider
            if not merged_data["series_name"]:
                merged_data["series_name"] = data.get("series_name", data.get("title", ""))

            # Merge seasons and episodes
            seasons = data.get("seasons", [])
            for season in seasons:
                season_num = season.get("season_number", 0)
                merged_season = next((s for s in merged_data["seasons"] if s["season_number"] == season_num), None)
                if not merged_season:
                    merged_season = {"season_number": season_num, "episodes": []}
                    merged_data["seasons"].append(merged_season)

                for episode in season.get("episodes", []):
                    episode_num = episode.get("episode_number", 0)
                    merged_episode = next((e for e in merged_season["episodes"] if e["episode_number"] == episode_num), None)
                    if not merged_episode:
                        merged_episode = {
                            "episode_number": episode_num,
                            "titles": {},
                            "overviews": {},
                            "ids": {},
                            "air_date": {}
                        }
                        merged_season["episodes"].append(merged_episode)

                    # Add provider-specific data
                    episode_title = episode.get("title", episode.get("titles", {}).get(provider, ""))
                    episode_overview = episode.get("overview", episode.get("overviews", {}).get(provider, ""))
                    episode_id = episode.get("id", episode.get("ids", {}).get(provider, ""))
                    episode_air_date = episode.get("air_date", episode.get("air_dates", {}).get(provider, ""))

                    merged_episode["titles"][provider] = episode_title or ""
                    merged_episode["overviews"][provider] = episode_overview or ""
                    merged_episode["ids"][provider] = str(episode_id) if episode_id else ""
                    merged_episode["air_date"][provider] = episode_air_date or ""

        except Exception as e:
            provider_logger.error(f"Failed to process {provider} JSON: {str(e)}")
            continue

    # Sort seasons to ensure season 0 is included
    merged_data["seasons"].sort(key=lambda x: x["season_number"])

    # Write merged JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w") as f:
        json.dump(merged_data, f, indent=4)
    builder_logger.info(f"Wrote merged JSON to {output_json}")

def main():
    """Main function to orchestrate metadata fetching and merging."""
    parser = argparse.ArgumentParser(description="Fetch and merge TV series metadata.")
    parser.add_argument("--series", required=True, help="Series name (e.g., Ax Men)")
    args = parser.parse_args()

    # Load configuration
    config = ConfigParser()
    config.read("config/paths.txt")
    temp_folder = config.get("general", "TEMP_FOLDER", fallback="tmp")
    json_folder = config.get("general", "JSON_FOLDER", fallback="data")
    log_path = config.get("general", "LOG_PATH", fallback="logs")

    # Initialize logging
    series_slug = args.series.lower().replace(" ", "_")
    builder_logger, provider_logger = setup_logging(series_slug, log_path)

    # Load enabled providers
    providers = []
    for provider in config["meta_providers"]:
        if config["meta_providers"].get(provider) == "enabled":
            providers.append(provider)
    builder_logger.info(f"Enabled providers: {', '.join(providers)}")

    # Fetch metadata from providers
    provider_files = []
    for provider in providers:
        builder_logger.info(f"Fetching metadata from provider: {provider}")
        try:
            module = import_module(f"providers.{provider}")
            module.get_metadata(args.series, config)
            provider_json = os.path.join(temp_folder, f"{provider}.json")
            if os.path.exists(provider_json):
                provider_files.append(provider_json)
                builder_logger.info(f"Successfully generated {provider_json}")
            else:
                builder_logger.warning(f"No JSON file generated for {provider}")
        except Exception as e:
            builder_logger.error(f"Failed to import/run {provider}: {str(e)}")
            continue

    # Merge provider data
    output_json = os.path.join(json_folder, series_slug, f"{args.series}.json")
    merge_provider_data(provider_files, output_json, config) # Pass the config object

if __name__ == "__main__":
    main()