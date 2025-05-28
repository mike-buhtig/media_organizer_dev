# Season_Episode_builder.py v1.0.29
# Orchestrates fetching and merging TV series metadata from multiple providers.
#
# Change Log:
# [1.0.29] - 2025-05-22: Corrected Season 0 episode merging to retain ALL provider-specific
#                      data within 'titles', 'overviews', 'ids', and 'air_date' dictionaries,
#                      mirroring the structure of regular season episodes.
#                      - Removed the "best_episode_data" fields (single title, overview, etc.)
#                        from the intermediate Season 0 processing, as these are not part of
#                        the final desired JSON structure.
#                      - The logic for assigning synthetic episode numbers and the 'synthetic' flag
#                        to unnumbered specials remains as intended.
# [1.0.28] - 2025-05-22: Implemented advanced merging strategy for Season 0 (specials)
#                      to prioritize data completeness and provider preference.
#                      - `unique_season_0_episodes_map` now stores a list of all provider
#                        versions for each unique special.
#                      - For each special, fields are merged based on rules:
#                        - `title`, `air_date`, `id`: Highest preference provider with data wins.
#                        - `overview`: Longest overview wins; ties broken by provider preference.
#                      - Retains existing integer `episode_number` and `synthetic` flag if present.
#                      - Ensures all `titles`, `overviews`, `ids`, `air_date` fields are populated
#                        with provider-specific data in the final merged output.
# [1.0.27] - 2025-05-22: Implemented robust deduplication for Season 0 (specials).
#                      - Uses a dictionary (keyed by normalized title and air_date) to collect
#                        unique specials from all providers, preventing duplicates.
#                      - Ensures that each unique special appears only once in the final Season 0 list.
#                      - The logic for assigning synthetic numbers to unnumbered specials
#                        now operates on a deduplicated set.
#                      - Added a helper function `_normalize_special_title` for consistent comparison.
# [1.0.26] - 2025-05-22: Implemented intelligent numbering and merging for Season 0 (specials).
#                      - Collects all season 0 episodes from all providers.
#                      - Separates already numbered specials from unnumbered (null_X) specials.
#                      - Determines the highest existing special episode number.
#                      - Sorts unnumbered specials by air_date (if available), then by title.
#                      - Assigns sequential integer episode numbers to unnumbered specials,
#                        starting after the highest existing special number.
#                      - Adds a "synthetic": True flag to newly numbered specials.
#                      - Consolidates and re-sorts all Season 0 episodes.
#                      - Merges top-level 'genres' (collecting unique values) and 'mpa_rating'
#                        from provider JSONs.
#                      - Added comprehensive comments and updated versioning.
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
import re
from configparser import ConfigParser
from importlib import import_module

def setup_logging(series_slug: str, log_path: str) -> tuple:
    """
    Set up separate loggers for builder and provider actions.
    Logs are directed to specific files within a series-specific subdirectory.
    """
    # Ensure log directory exists
    log_dir = os.path.join(log_path, series_slug)
    os.makedirs(log_dir, exist_ok=True)

    # Builder logger setup
    builder_logger = logging.getLogger("Season_Episode_builder.builder")
    builder_logger.setLevel(logging.INFO) # Set default level for builder
    # Clear existing handlers to prevent duplicate logs if called multiple times
    builder_logger.handlers = [] 
    builder_handler = logging.FileHandler(os.path.join(log_dir, f"{series_slug}_builder.log"), mode="a")
    builder_handler.setFormatter(logging.Formatter("[%(asctime)s] [builder] %(message)s"))
    builder_logger.addHandler(builder_handler)

    # Provider logger setup
    provider_logger = logging.getLogger("Season_Episode_builder.provider")
    provider_logger.setLevel(logging.DEBUG) # Set to DEBUG for detailed merging logs
    # Clear existing handlers to prevent duplicate logs if called multiple times
    provider_logger.handlers = [] 
    provider_handler = logging.FileHandler(os.path.join(log_dir, f"{series_slug}_provider.log"), mode="a")
    provider_handler.setFormatter(logging.Formatter("[%(asctime)s] [provider] %(message)s"))
    provider_logger.addHandler(provider_handler)

    # Log script version
    builder_logger.info("Season_Episode_builder.py v1.0.29 starting")

    return builder_logger, provider_logger

def _normalize_special_title(title: str) -> str:
    """Normalizes a special title for consistent comparison (lowercase, alphanumeric only)."""
    if not title:
        return ""
    # Remove non-alphanumeric characters and convert to lowercase
    return re.sub(r'[^a-z0-9]', '', title.lower())

def merge_provider_data(provider_files: list, output_json: str, config: ConfigParser) -> None:
    """
    Merges provider JSONs into a single JSON, handling season 0 (specials) numbering.
    Each episode's metadata is stored under provider-specific keys (e.g., titles: {tvmaze: "...", tmdb: "..."}).
    """
    merged_data = {
        "series_name": "",
        "seasons": [],
        "genres": [], # Initialize top-level genres list
        "mpa_rating": "" # Initialize top-level mpa_rating
    }
    builder_logger = logging.getLogger("Season_Episode_builder.builder")
    provider_logger = logging.getLogger("Season_Episode_builder.provider")

    # Get the list of enabled providers from the config to establish preference order
    providers_in_preference_order = []
    for provider_name in config["meta_providers"]:
        if config["meta_providers"].get(provider_name).lower() == "enabled":
            providers_in_preference_order.append(provider_name)
    provider_logger.debug(f"Provider preference order: {providers_in_preference_order}")

    # Temporary storage for all season 0 episodes from all providers, keyed by (normalized_title, air_date)
    # Value will be a list of episode dictionaries, each from a different provider.
    unique_season_0_episodes_versions = {} # Key: (normalized_title, air_date), Value: list of episode_dict (with 'provider' field)

    for provider in providers_in_preference_order: # Iterate through providers in preference order
        json_file = next((f for f in provider_files if f.endswith(f"{provider}.json")), None)
        if not json_file or not os.path.exists(json_file):
            provider_logger.error(f"Missing or invalid JSON for {provider}")
            continue

        provider_logger.debug(f"Attempting to load JSON from {json_file}")
        data = {} # Initialize data to an empty dict
        try:
            with open(json_file, "r", encoding="utf-8") as f: # Specify encoding for safety
                data = json.load(f)
            provider_logger.info(f"Loaded {provider} JSON")

            # Explicitly check if data is a dictionary
            if not isinstance(data, dict):
                provider_logger.error(f"Invalid JSON format for {provider}: expected dict, got {type(data).__name__}. Content (first 100 chars): {str(data)[:100]}")
                continue # Skip to next provider if data is not a dict
            
            # --- Merge top-level series metadata (genres, mpa_rating, series_name) ---
            # Set series name from first valid provider that has it
            if not merged_data["series_name"] and data.get("series_name"):
                merged_data["series_name"] = data["series_name"]
            elif not merged_data["series_name"] and data.get("title"): # Fallback for title if series_name is missing
                merged_data["series_name"] = data["title"]

            # Merge genres (collect all unique genres)
            provider_genres = data.get("genres", [])
            provider_logger.debug(f"Extracted provider_genres for {provider}: {provider_genres}, type: {type(provider_genres).__name__}")
            
            if isinstance(provider_genres, str): # Handle case where genre might be a single string
                provider_genres = [provider_genres]
            elif not isinstance(provider_genres, list):
                provider_logger.warning(f"Genres for {provider} is not a list or string. Skipping genre merging. Type: {type(provider_genres).__name__}, Value: {provider_genres}")
                provider_genres = [] # Reset to empty list to avoid errors in loop

            for genre in provider_genres:
                if genre and genre not in merged_data["genres"]:
                    merged_data["genres"].append(genre)
            
            # Merge MPA rating (take the first one found, or refine logic if multiple are possible)
            provider_mpa_rating = data.get("mpa_rating", "")
            if provider_mpa_rating and not merged_data["mpa_rating"]:
                merged_data["mpa_rating"] = provider_mpa_rating

            # Process seasons - handle both list and dictionary formats
            seasons_data = data.get("seasons", [])
            
            # Convert dictionary format to list of season dictionaries for consistent processing
            if isinstance(seasons_data, dict):
                provider_logger.debug(f"Seasons for {provider} is a dictionary. Converting to list.")
                converted_seasons = []
                for key, season_dict in seasons_data.items():
                    # Handle the "specials" key for old RT format, assigning it season 0
                    if key.lower() == "specials": 
                        season_dict['season_number'] = 0 
                        converted_seasons.append(season_dict)
                    elif isinstance(season_dict, dict) and 'season_number' in season_dict:
                        converted_seasons.append(season_dict)
                    elif isinstance(season_dict, dict) and key.isdigit(): # If key is digit, assume it's season_number
                         season_dict['season_number'] = int(key)
                         converted_seasons.append(season_dict)
                    else:
                        provider_logger.warning(f"Skipping unexpected season entry in dictionary format for {provider}: Key='{key}', Value='{season_dict}'")
                seasons_data = converted_seasons
            
            if not isinstance(seasons_data, list): # Final check after potential conversion
                provider_logger.warning(f"Seasons for {provider} is not a list after conversion attempt. Skipping season processing. Type: {type(seasons_data).__name__}, Value: {seasons_data}")
                seasons_data = []

            for season in seasons_data:
                season_num = season.get("season_number")
                if season_num is None: # Skip if season_number is missing
                    provider_logger.warning(f"Skipping season from {provider} due to missing 'season_number'. Season data: {season}")
                    continue

                if season_num == 0:
                    # Collect all season 0 episodes for later consolidated processing
                    episodes_for_season_0 = season.get("episodes", [])
                    # Handle if episodes for season 0 is a dictionary (old RT format)
                    if isinstance(episodes_for_season_0, dict):
                        provider_logger.debug(f"Episodes for Season 0 from {provider} is a dictionary. Converting to list.")
                        episodes_for_season_0 = list(episodes_for_season_0.values())

                    if not isinstance(episodes_for_season_0, list):
                        provider_logger.warning(f"Episodes for Season 0 from {provider} is not a list. Skipping. Type: {type(episodes_for_season_0).__name__}, Value: {episodes_for_season_0}")
                        episodes_for_season_0 = []
                    
                    for episode in episodes_for_season_0:
                        # Create a unique key for deduplication
                        normalized_title = _normalize_special_title(episode.get('title', ''))
                        air_date = episode.get('air_date', '')
                        special_key = (normalized_title, air_date)

                        # Add episode version to the list for this special key
                        if special_key not in unique_season_0_episodes_versions:
                            unique_season_0_episodes_versions[special_key] = []
                        
                        episode_copy = episode.copy()
                        episode_copy['provider'] = provider # Store provider for later merging
                        unique_season_0_episodes_versions[special_key].append(episode_copy)
                        provider_logger.debug(f"Collected special '{episode.get('title')}' from {provider} (key: {special_key})")

                else:
                    # Find or create the merged season
                    merged_season = next((s for s in merged_data["seasons"] if s["season_number"] == season_num), None)
                    if not merged_season:
                        merged_season = {"season_number": season_num, "episodes": []}
                        merged_data["seasons"].append(merged_season)

                    # Merge episodes for regular seasons
                    episodes_for_regular_season = season.get("episodes", [])
                    # Handle if episodes for regular season is a dictionary (old RT format)
                    if isinstance(episodes_for_regular_season, dict):
                        provider_logger.debug(f"Episodes for Season {season_num} from {provider} is a dictionary. Converting to list.")
                        episodes_for_regular_season = list(episodes_for_regular_season.values())

                    if not isinstance(episodes_for_regular_season, list):
                        provider_logger.warning(f"Episodes for Season {season_num} from {provider} is not a list. Skipping. Type: {type(episodes_for_regular_season).__name__}, Value: {episodes_for_regular_season}")
                        episodes_for_regular_season = []

                    for episode in episodes_for_regular_season:
                        episode_num = episode.get("episode_number")
                        if episode_num is None: # Skip if episode_number is missing for regular season
                            provider_logger.warning(f"Skipping episode from {provider} (Season {season_num}) due to missing 'episode_number'. Episode data: {episode}")
                            continue
                        
                        # Ensure episode_num is an integer for comparison
                        try:
                            episode_num = int(episode_num)
                        except (ValueError, TypeError):
                            provider_logger.warning(f"Invalid episode_number '{episode_num}' from {provider} (Season {season_num}), skipping.")
                            continue

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

                        # Add provider-specific data to the merged episode
                        episode_title = episode.get("title", "")
                        episode_overview = episode.get("overview", "")
                        episode_id = episode.get("id")
                        episode_air_date = episode.get("air_date", "")

                        merged_episode["titles"][provider] = episode_title or ""
                        merged_episode["overviews"][provider] = episode_overview or ""
                        merged_episode["ids"][provider] = str(episode_id) if episode_id else ""
                        merged_episode["air_date"][provider] = episode_air_date or ""

        except json.JSONDecodeError as e:
            provider_logger.error(f"Failed to parse JSON for {provider}: {type(e).__name__}: {e}", exc_info=True)
            continue
        except Exception as e:
            # Catch any other unexpected errors during processing
            provider_logger.error(f"An unexpected error occurred while processing {provider} JSON: {type(e).__name__}: {e}", exc_info=True)
            continue

    # --- Consolidate and Number Season 0 Episodes (Specials) ---
    final_season_0_episodes_for_numbering = []

    for special_key, episode_versions in unique_season_0_episodes_versions.items():
        # Initialize the merged episode data for this special, with all provider-specific dictionaries
        merged_special_episode = {
            "episode_number": None, # Will be assigned later (existing or synthetic)
            "titles": {},
            "overviews": {},
            "ids": {},
            "air_date": {},
            "synthetic": False # Will be set to True if assigned synthetically
        }
        
        # Track existing episode number and synthetic flag from any version
        found_existing_ep_num = None
        found_synthetic_flag = False

        # Populate provider-specific dictionaries and find existing episode number/synthetic flag
        for ep_version in episode_versions:
            provider = ep_version['provider']

            merged_special_episode["titles"][provider] = ep_version.get("title", "")
            merged_special_episode["overviews"][provider] = ep_version.get("overview", "")
            merged_special_episode["ids"][provider] = str(ep_version.get("id")) if ep_version.get("id") else ""
            merged_special_episode["air_date"][provider] = ep_version.get("air_date", "")

            # Preserve existing integer episode_number if it's positive
            if isinstance(ep_version.get("episode_number"), int) and ep_version["episode_number"] > 0:
                found_existing_ep_num = ep_version["episode_number"]
            
            # Preserve synthetic flag if any provider marked it synthetic
            if ep_version.get("synthetic"):
                found_synthetic_flag = True
        
        # Apply the found existing episode number and synthetic flag
        if found_existing_ep_num is not None:
            merged_special_episode["episode_number"] = found_existing_ep_num
        if found_synthetic_flag:
            merged_special_episode["synthetic"] = True

        final_season_0_episodes_for_numbering.append(merged_special_episode)

    # Now, proceed with the numbering and sorting logic for Season 0
    max_existing_ep_num = 0

    # Separate already numbered specials from unnumbered (those that still have None as episode_number)
    numbered_specials = []
    unnumbered_specials = [] 

    for ep in final_season_0_episodes_for_numbering:
        ep_num = ep.get("episode_number")
        if isinstance(ep_num, int) and ep_num > 0:
            numbered_specials.append(ep)
            if ep_num > max_existing_ep_num:
                max_existing_ep_num = ep_num
        else:
            # These are the ones that didn't have a positive integer episode_number from any provider
            unnumbered_specials.append(ep)
            provider_logger.debug(f"Identified unnumbered special for synthetic numbering: '{ep['titles'].get(list(ep['titles'].keys())[0], 'unknown title')}'") # Log first available title


    # Sort unnumbered specials by air_date (if available), then by title (using the first available title)
    # This ensures consistent ordering for synthetic numbering
    unnumbered_specials.sort(key=lambda x: (x["air_date"].get(list(x["air_date"].keys())[0], "") or "", 
                                            x["titles"].get(list(x["titles"].keys())[0], "")))

    # Assign synthetic episode numbers to unnumbered specials
    current_synthetic_ep_num = max_existing_ep_num + 1
    for ep in unnumbered_specials:
        ep["episode_number"] = current_synthetic_ep_num
        ep["synthetic"] = True # Explicitly mark as synthetic
        current_synthetic_ep_num += 1
        provider_logger.info(f"Assigned synthetic episode number {ep['episode_number']} to special: '{ep['titles'].get(list(ep['titles'].keys())[0], 'unknown title')}' (Air Date: {ep['air_date'].get(list(ep['air_date'].keys())[0], '')})")

    # Combine all season 0 episodes and sort by their final episode number
    final_season_0_episodes = numbered_specials + unnumbered_specials
    final_season_0_episodes.sort(key=lambda x: x["episode_number"])

    # Find or create the merged season 0 structure in merged_data
    merged_season_0 = next((s for s in merged_data["seasons"] if s["season_number"] == 0), None)
    if not merged_season_0:
        merged_season_0 = {"season_number": 0, "episodes": []}
        merged_data["seasons"].append(merged_season_0)
    else:
        # Clear existing episodes in season 0 if it was found, to replace with fully processed ones
        merged_season_0["episodes"] = []

    # Add the final, processed season 0 episodes to the merged_season_0
    for episode in final_season_0_episodes:
        merged_season_0["episodes"].append(episode)

    # Ensure season 0 is in the final list only if it has episodes
    merged_data["seasons"] = [s for s in merged_data["seasons"] if s["season_number"] != 0]
    if final_season_0_episodes:
        merged_data["seasons"].append(merged_season_0)

    # Sort all seasons (including the newly processed season 0)
    merged_data["seasons"].sort(key=lambda x: x["season_number"])
    # Sort episodes within each season
    for season in merged_data["seasons"]:
        season["episodes"].sort(key=lambda x: x["episode_number"])

    # Write merged JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    try:
        with open(output_json, "w", encoding="utf-8") as f: # Specify encoding for safety
            json.dump(merged_data, f, indent=4)
        builder_logger.info(f"Wrote merged JSON to {output_json}")
    except Exception as e:
        builder_logger.error(f"Failed to write merged JSON to {output_json}: {type(e).__name__}: {e}", exc_info=True)


def main():
    """Main function to orchestrate metadata fetching and merging."""
    parser = argparse.ArgumentParser(description="Fetch and merge TV series metadata.")
    parser.add_argument("--series", required=True, help="Series name (e.g., Ax Men)")
    args = parser.parse_args()

    # Load configuration
    config = ConfigParser()
    config_path = "config/paths.txt"
    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at {config_path}")
        return
    config.read(config_path)
    
    temp_folder = config.get("general", "TEMP_FOLDER", fallback="tmp")
    json_folder = config.get("general", "JSON_FOLDER", fallback="data")
    log_path = config.get("general", "LOG_PATH", fallback="logs")

    # Initialize logging
    series_slug = args.series.lower().replace(" ", "_").replace("'", "") # Clean slug for log paths
    series_slug = series_slug.replace('-', '_')
    builder_logger, provider_logger = setup_logging(series_slug, log_path)

    # Load enabled providers
    providers = []
    if "meta_providers" in config:
        for provider_name, status in config.items("meta_providers"):
            if status.lower() == "enabled":
                providers.append(provider_name)
    else:
        builder_logger.warning("No [meta_providers] section found in config/paths.txt. No providers will be run.")
        return # Exit if no providers are configured

    builder_logger.info(f"Enabled providers: {', '.join(providers)}")

    # Fetch metadata from providers
    provider_files = []
    for provider in providers:
        builder_logger.info(f"Fetching metadata from provider: {provider}")
        try:
            # Dynamically import the provider module
            module = import_module(f"providers.{provider}")
            
            # Call the get_metadata function from the provider module
            # The provider_logger is already set up globally via logging.getLogger
            # and will automatically direct logs from provider scripts to the correct file.
            module.get_metadata(args.series, config) 
            
            # Check for the generated JSON file
            provider_json = os.path.join(temp_folder, f"{provider}.json")
            if os.path.exists(provider_json):
                provider_files.append(provider_json)
                builder_logger.info(f"Successfully generated {provider_json}")
            else:
                builder_logger.warning(f"No JSON file generated for {provider}")
        except ImportError:
            builder_logger.error(f"Provider module not found: providers.{provider}. Please ensure the file exists and is in the correct path.")
        except AttributeError:
            builder_logger.error(f"Provider module 'providers.{provider}' does not have a 'get_metadata' function.")
        except Exception as e:
            builder_logger.error(f"Failed to run provider {provider}: {type(e).__name__}: {e}", exc_info=True)
            continue

    # Merge provider data
    output_json_dir = os.path.join(json_folder, series_slug)
    output_json_file = os.path.join(output_json_dir, f"{args.series}.json")
    merge_provider_data(provider_files, output_json_file, config)

if __name__ == "__main__":
    main()
