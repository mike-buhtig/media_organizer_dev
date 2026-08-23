# file_organizer.py
# Version 0.9.15
# Orchestrates the organization of TV series media files, including NFO creation and optional file movement.
#
# Change Log:
#
# [0.9.5] - Restored version with NFO writing only (no move/delete)
#         - Uses paths.txt
#         - Filters broken files
#         - Groups by subtitle
#         - Picks best file
#         - Writes .nfo files to TV_LIBRARY_PATH
#         - Logs KEEP/RENAME/NFO/DELETE candidates in file_organizer_actions_<series>.log
#         - Cleans subtitle for use in filename
#         - Fixes issue where titles list was not parsed correctly
#         - 2025-04-18: Logging format restored with full traceability for each action
#         - 2025-04-19: Normalize log file output to use / without a mix, which is unix style file address
#         - 2025-04-22: Fixed AttributeError in group_and_write to handle new JSON structure with matches and unmatched sections
#         - 2025-04-22: Updated write_nfo to place unmatched episodes in 'Unmatched Episodes' folder
#         - 2025-04-30 Update .json format
#         - 2025-04-30 Update to use a flag to make the script move the files into place.
# [0.9.6] - 2025-05-31: Fixed FileNotFoundError for 'paths.txt' by adjusting its load path to 'config/paths.txt'.
#         - 2025-05-31: Corrected path construction for 'Processed.json' to use series-specific subdirectories (e.g., data/the_a_team/).
#         - 2025-05-31: Added comprehensive comments for clarity and maintainability.
# [0.9.7] - 2025-05-31: Modified paths.txt parsing to more robustly parse as series_folder_crawler.py does.
#         - 2025-05-31: Modified logs save path to conform to the current version of the organizer.
# [0.9.8] - 2025-06-01: Integrated Kodi watched status (playcount, lastplayed) into NFO files.
#         - Added loading of 'kodi_watched.json' from a configurable path in paths.txt.
#         - Modified 'create_nfo_file' to accept and include playcount and lastplayed.
#         - Modified 'organize_files' to look up and pass watched status to 'create_nfo_file'.
# [0.9.9] - 2025-06-01: Refined KODI_WATCHED_JSON_PATH fallback to use JSON_FOLDER for consistency.
# [0.9.10] - 2025-06-01: Corrected Kodi watched JSON path construction to strictly follow JSON_FOLDER/series_slug/filename convention.
#          - Removed KODI_WATCHED_JSON_PATH from paths.txt loading.
# [0.9.11] - 2025-06-01: Updated load_kodi_watched_data to handle the nested structure of kodi_watched.json.
# [0.9.12] - 2025-06-02: Debugging early failure in version 0.9.11.
# [0.9.13] - 2025-06-02: Added comprehensive try-except around main() and more robust early debug prints.
# [0.9.14] - 2025-06-02: Implemented "best file" selection logic (largest non-broken .ts).
#          - Added deletion logic for all other associated files (dry run logging and actual deletion).
#          - Enhanced overall script commenting and section headers for clarity.
# [0.9.15] - 2025-06-02: Modified title and overview selection in NFO creation and filename generation
#          - to use dynamic provider priority from paths.txt instead of hardcoded order.

import os
import json
import argparse
import logging
from datetime import datetime, timezone
import shutil
from pathlib import Path
import configparser
import sys
import re
import traceback # Import traceback for detailed error info
import copy
import uuid

try:
    from scripts.episode_history import (
        atomic_write_history,
        episode_key,
        load_history,
        merge_processed_episodes,
        normalize_windows_path,
        record_verified_transition,
    )
except ImportError:
    from episode_history import (
        atomic_write_history,
        episode_key,
        load_history,
        merge_processed_episodes,
        normalize_windows_path,
        record_verified_transition,
    )

PREVIEW_ROOT = Path(r"E:\MediaOrganizerWork\Preview")
QUARANTINE_ROOT = Path(r"E:\MediaOrganizerWork\Quarantine")

# --- Global Debug Print for Very Early Execution ---
sys.stdout.write("DEBUG: Script started. This should always appear.\n")
sys.stdout.flush()

# ==============================================================================
# Logging Setup
# ==============================================================================
def setup_logging(series_name: str) -> str:
    """
    Sets up logging for the file_organizer script.
    Logs are directed to a series-specific file within the 'logs' directory.

    Args:
        series_name (str): The name of the TV series.

    Returns:
        str: The slugified version of the series name used for log directory.
    """
    sys.stdout.write(f"DEBUG: Entering setup_logging with series_name: '{series_name}'\n")
    sys.stdout.flush()

    # Create a slug from the series name for consistent folder/file naming
    series_slug = series_name.lower().replace(" ", "_").replace("-", "_")
    log_dir = Path("logs") / series_slug # Construct log directory path

    try:
        # Ensure the log directory exists, create if not
        os.makedirs(log_dir, exist_ok=True)
        sys.stdout.write(f"DEBUG: Log directory ensured: '{log_dir}'\n")
        sys.stdout.flush()
    except Exception as e:
        # If directory creation fails, set up console logging as a fallback
        sys.stderr.write(f"ERROR: Could not create log directory '{log_dir}': {e}\n")
        sys.stderr.flush()
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logging.root.addHandler(console_handler) # Add to root logger
        logging.root.error(f"Failed to create log directory: {e}. Logging to console only.")
        return series_slug # Return early if directory creation failed

    # Clear existing handlers to prevent duplicate log entries on re-runs
    # This is crucial for basicConfig to work correctly if called multiple times
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close() # Ensure handler is closed to release file locks

    log_file = log_dir / "file_organizer.log" # Construct the full log file path
    try:
        # Configure the file logger
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO, # Set logging level to INFO
            format="[%(asctime)s] %(message)s", # Log format
            datefmt="%Y-%m-%d %H:%M:%S" # Date/time format
        )
        sys.stdout.write(f"DEBUG: File logger configured to: '{log_file}'\n")
        sys.stdout.flush()
    except Exception as e:
        # If file logging setup fails, fall back to console logging
        sys.stderr.write(f"ERROR: Failed to set up file logger at '{log_file}': {e}\n")
        sys.stderr.flush()
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logging.root.addHandler(console_handler)
        logging.root.error(f"Failed to set up file logger: {e}. Logging to console.")

    logging.info(f"File Organizer v0.9.15 starting for series: '{series_name}'")
    sys.stdout.write(f"DEBUG: Leaving setup_logging, series_slug: '{series_slug}'\n")
    sys.stdout.flush()
    return series_slug

# ==============================================================================
# Configuration Loading
# ==============================================================================
def load_paths() -> dict:
    """
    Loads configuration paths and matching thresholds from 'config/paths.txt'.
    Also loads the metadata provider priority order.

    Returns:
        dict: A dictionary containing loaded configuration paths and settings.
    """
    sys.stdout.write("DEBUG: Entering load_paths()\n")
    sys.stdout.flush()
    paths = {}
    config_parser = configparser.ConfigParser()

    # Determine the script's directory to build a robust path to config/paths.txt
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.stdout.write(f"DEBUG: Script directory: '{script_dir}'\n")
    sys.stdout.flush()
    
    # First attempt: relative to the script's parent directory (e.g., ../config/paths.txt)
    config_path = os.path.join(script_dir, "..", "config", "paths.txt")
    sys.stdout.write(f"DEBUG: Attempting to load config from: '{config_path}'\n")
    sys.stdout.flush()

    if not os.path.exists(config_path):
        # Second attempt: relative to the current working directory (e.g., config/paths.txt)
        config_path = os.path.join("config", "paths.txt")
        sys.stdout.write(f"DEBUG: First path not found, trying: '{config_path}'\n")
        sys.stdout.flush()
        if not os.path.exists(config_path):
            # If still not found, raise an error and exit
            sys.stderr.write(f"ERROR: Configuration file not found at: {config_path}\n")
            sys.stderr.flush()
            raise FileNotFoundError(f"paths.txt not found at {config_path}")

    try:
        # Read the configuration file
        config_parser.read(config_path)
        sys.stdout.write("DEBUG: config_parser.read() successful.\n")
        sys.stdout.flush()
        logging.info(f"Loaded configuration from: {config_path}")

        # Retrieve paths from the 'library_paths' section
        paths["TV_LIBRARY_PATH"] = config_parser.get("library_paths", "TV_LIBRARY_PATH").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded TV_LIBRARY_PATH: '{paths['TV_LIBRARY_PATH']}'\n")
        sys.stdout.flush()
        paths["MOVIE_LIBRARY_PATH"] = config_parser.get("library_paths", "MOVIE_LIBRARY_PATH").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded MOVIE_LIBRARY_PATH: '{paths['MOVIE_LIBRARY_PATH']}'\n")
        sys.stdout.flush()
        
        # Retrieve general settings from the 'general' section with fallbacks
        paths["JSON_FOLDER"] = config_parser.get("general", "JSON_FOLDER", fallback="data").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded JSON_FOLDER: '{paths['JSON_FOLDER']}'\n")
        sys.stdout.flush()
        paths["LOG_PATH"] = config_parser.get("general", "LOG_PATH", fallback="logs").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded LOG_PATH: '{paths['LOG_PATH']}'\n")
        sys.stdout.flush()
        paths["TEMP_FOLDER"] = config_parser.get("general", "TEMP_FOLDER", fallback="tmp").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded TEMP_FOLDER: '{paths['TEMP_FOLDER']}'\n")
        sys.stdout.flush()
        paths["USE_KODI"] = config_parser.getboolean("general", "USE_KODI", fallback=False)
        sys.stdout.write(f"DEBUG: Loaded USE_KODI: '{paths['USE_KODI']}'\n")
        sys.stdout.flush()
        paths["USE_NEXTPVR"] = config_parser.getboolean("general", "USE_NEXTPVR", fallback=False)
        sys.stdout.write(f"DEBUG: Loaded USE_NEXTPVR: '{paths['USE_NEXTPVR']}'\n")
        sys.stdout.flush()
        paths["OPERATION_MODE"] = config_parser.get("general", "OPERATION_MODE", fallback="move").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded OPERATION_MODE: '{paths['OPERATION_MODE']}'\n")
        sys.stdout.flush()
        paths["CREATE_NFO"] = config_parser.getboolean("general", "CREATE_NFO", fallback=True)
        sys.stdout.write(f"DEBUG: Loaded CREATE_NFO: '{paths['CREATE_NFO']}'\n")
        sys.stdout.flush()

        # Load metadata provider priority order from [meta_providers] section
        provider_priority_order = []
        if "meta_providers" in config_parser:
            for provider_name, status in config_parser.items("meta_providers"):
                if status.lower() == "enabled":
                    provider_priority_order.append(provider_name)
        paths["PROVIDER_PRIORITY_ORDER"] = provider_priority_order
        sys.stdout.write(f"DEBUG: Loaded PROVIDER_PRIORITY_ORDER: {paths['PROVIDER_PRIORITY_ORDER']}\n")
        sys.stdout.flush()

        sys.stdout.write("DEBUG: Successfully loaded paths from config.\n")
        sys.stdout.flush()

    except configparser.NoSectionError as e:
        # Handle missing sections in the config file
        logging.error(f"Error loading configuration: Section '{e.section}' not found in {config_path}")
        sys.stderr.write(f"DEBUG: configparser.NoSectionError: {e}\n")
        sys.stderr.flush()
        raise # Re-raise the exception after logging
    except configparser.NoOptionError as e:
        # Handle missing options within a section
        logging.error(f"Error loading configuration: Option '{e.option}' not found in section '{e.section}' in {config_path}")
        sys.stderr.write(f"DEBUG: configparser.NoOptionError: {e}\n")
        sys.stderr.flush()
        raise # Re-raise the exception after logging
    except Exception as e:
        # Catch any other unexpected errors during config loading
        logging.error(f"An unexpected error occurred while loading configuration: {e}")
        sys.stderr.write(f"DEBUG: Unexpected error in load_paths: {e}\n")
        sys.stderr.flush()
        raise # Re-raise the exception after logging

    sys.stdout.write(f"DEBUG: Leaving load_paths(), loaded paths: {paths}\n")
    sys.stdout.flush()
    return paths

# ==============================================================================
# JSON Data Loading Functions
# ==============================================================================
def load_processed_json(series_name: str, json_folder: str) -> list:
    """
    Loads the processed JSON metadata for a given series.
    This JSON contains details about episodes, including their original file paths
    and merged metadata from various providers.

    Args:
        series_name (str): The name of the TV series.
        json_folder (str): The base directory where JSON files are stored (e.g., 'data').

    Returns:
        list: A list of episode dictionaries, with season_number added to each episode.
              Returns an empty list if the file is not found or an error occurs.
    """
    sys.stdout.write(f"DEBUG: Entering load_processed_json with series_name: '{series_name}', json_folder: '{json_folder}'\n")
    sys.stdout.flush()

    # Create a slug for the series folder (lowercase, underscores for spaces/hyphens)
    series_slug_folder = series_name.lower().replace(" ", "_").replace("-", "_")
    # Construct the full path to the processed JSON file
    json_path = Path(json_folder) / series_slug_folder / f"{series_name.replace(' ', '_')}_Processed.json"
    
    sys.stdout.write(f"DEBUG: Attempting to load processed JSON from: '{json_path}'\n")
    sys.stdout.flush()
    
    if not json_path.exists():
        logging.error(f"Processed JSON file not found: {json_path}")
        sys.stdout.write(f"DEBUG: Processed JSON file not found: {json_path}\n")
        sys.stdout.flush()
        return [] # Return empty list if file doesn't exist
    
    try:
        with open(json_path, "r", encoding="utf-8") as f: # Ensure UTF-8 encoding for reading
            data = json.load(f)
        
        episodes = []
        # Iterate through seasons and episodes to flatten the structure for easier processing
        for season in data.get("seasons", []):
            season_num = season.get("season_number")
            if season_num is None:
                logging.warning(f"Skipping season with missing 'season_number' in {json_path}. Season data: {season}")
                sys.stdout.write(f"DEBUG: Skipping season with missing 'season_number': {season}\n")
                sys.stdout.flush()
                continue
            for episode in season.get("episodes", []):
                # Add season_number to each episode dictionary for easier access later
                episode["season_number"] = season_num
                episodes.append(episode)
        
        logging.info(f"Successfully loaded {len(episodes)} episodes from {json_path}")
        sys.stdout.write(f"DEBUG: Successfully loaded {len(episodes)} episodes from {json_path}\n")
        sys.stdout.flush()
        return episodes
    except json.JSONDecodeError as e:
        # Handle JSON parsing errors
        logging.error(f"Error decoding JSON from {json_path}: {e}")
        sys.stderr.write(f"DEBUG: Error decoding JSON from {json_path}: {e}\n")
        sys.stderr.flush()
        return []
    except Exception as e:
        # Catch any other unexpected errors during JSON loading
        logging.error(f"An unexpected error occurred while loading JSON from {json_path}: {e}")
        sys.stderr.write(f"DEBUG: Unexpected error loading JSON from {json_path}: {e}\n")
        sys.stderr.flush()
        return []

def load_kodi_watched_data(kodi_watched_json_path: str) -> dict:
    """
    Loads the Kodi watched status data from the specified JSON file.
    The data is expected to be a nested dictionary:
    {
        "series_name": "...",
        "seasons": [
            {
                "season_number": ...,
                "episodes": [
                    { "episode_number": ..., "watched": true/false, "last_played": "YYYY-MM-DD HH:MM:SS" },
                    ...
                ]
            },
            ...
        ]
    }
    It's converted into a flat dictionary for quick lookup using (series_name_lower, season_num, episode_num) as keys.

    Args:
        kodi_watched_json_path (str): The file path to the kodi_watched.json.

    Returns:
        dict: A dictionary mapping (series_name_lower, season_num, episode_num)
              to a dict containing 'playcount' (1 if watched, 0 otherwise) and 'lastplayed'.
              Returns an empty dict if the file is not found or an error occurs.
    """
    sys.stdout.write(f"DEBUG: Entering load_kodi_watched_data with path: '{kodi_watched_json_path}'\n")
    sys.stdout.flush()
    watched_data = {}
    kodi_json_path = Path(kodi_watched_json_path)

    logging.info(f"Attempting to load Kodi watched data from: {kodi_json_path}")
    sys.stdout.write(f"DEBUG: Attempting to load Kodi watched data from: '{kodi_json_path}'\n")
    sys.stdout.flush()

    if not kodi_json_path.exists():
        logging.warning(f"Kodi watched JSON file not found: {kodi_json_path}. NFOs will not include watched status.")
        sys.stdout.write(f"DEBUG: Kodi watched JSON file not found: {kodi_json_path}\n")
        sys.stdout.flush()
        return {} # Return empty dict if file doesn't exist

    try:
        with open(kodi_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate the top-level structure of the Kodi watched JSON
        if not isinstance(data, dict) or "series_name" not in data or "seasons" not in data:
            logging.error(f"Kodi watched JSON has unexpected top-level structure. Expected a dict with 'series_name' and 'seasons'. Skipping watched status loading.")
            sys.stderr.write(f"DEBUG: Kodi watched JSON unexpected structure: {type(data)}\n")
            sys.stderr.flush()
            return {}

        series_name_kodi_base = data.get("series_name", "").lower() # Get series name and convert to lowercase for key
        seasons_data = data.get("seasons", []) # Get the list of seasons

        for season in seasons_data:
            season_num_kodi = season.get("season_number")
            episodes_data = season.get("episodes", [])

            if season_num_kodi is not None and isinstance(episodes_data, list):
                for episode in episodes_data:
                    episode_num_kodi = episode.get("episode_number")
                    watched = episode.get("watched", False) # Default to False if 'watched' is missing
                    last_played = episode.get("last_played", "") # Default to empty string if 'last_played' is missing

                    if episode_num_kodi is not None:
                        # Create a unique key for the episode: (series_slug, season_number, episode_number)
                        key = (series_name_kodi_base, int(season_num_kodi), int(episode_num_kodi))
                        watched_data[key] = {
                            "playcount": 1 if watched else 0,  # Set playcount to 1 if watched, 0 otherwise
                            "lastplayed": last_played
                        }
                    else:
                        logging.warning(f"Skipping Kodi watched episode entry due to missing 'episode_number': {episode}")
                        sys.stdout.write(f"DEBUG: Skipping Kodi watched entry missing episode_number: {episode}\n")
                        sys.stdout.flush()
            else:
                logging.warning(f"Skipping Kodi watched season entry due to missing 'season_number' or invalid 'episodes': {season}")
                sys.stdout.write(f"DEBUG: Skipping Kodi watched season entry: {season}\n")
                sys.stdout.flush()

        logging.info(f"Successfully loaded watched status for {len(watched_data)} episodes from {kodi_json_path}.")
        sys.stdout.write(f"DEBUG: Successfully loaded watched status for {len(watched_data)} episodes.\n")
        sys.stdout.flush()
        return watched_data

    except json.JSONDecodeError as e:
        # Handle JSON parsing errors
        logging.error(f"Error decoding Kodi watched JSON from {kodi_json_path}: {e}. Skipping watched status loading.")
        sys.stderr.write(f"DEBUG: Error decoding Kodi watched JSON: {e}\n")
        sys.stderr.flush()
        return {}
    except Exception as e:
        # Catch any other unexpected errors during Kodi watched data loading
        logging.error(f"An unexpected error occurred while loading Kodi watched data from {kodi_json_path}: {e}. Skipping watched status loading.")
        sys.stderr.write(f"DEBUG: Unexpected error loading Kodi watched data: {e}\n")
        sys.stderr.flush()
        return {}

# ==============================================================================
# NFO File Creation
# ==============================================================================
def create_nfo_file(series_name: str, episode: dict, output_path: Path, playcount: int = 0, lastplayed: str = "", provider_priority_order: list = None):
    """
    Creates an NFO (National File Organization) file for a given episode,
    including playcount and last played information for Kodi.
    Selects title and overview based on the provided provider priority order.

    Args:
        series_name (str): The name of the TV series.
        episode (dict): A dictionary containing episode metadata (from processed JSON).
        output_path (Path): The intended path for the media file, used to derive NFO path.
                            The NFO file will have the same base name as this path.
        playcount (int, optional): The number of times the episode has been played. Defaults to 0.
        lastplayed (str, optional): The date the episode was last played (YYYY-MM-DD HH:MM:SS). Defaults to "".
        provider_priority_order (list, optional): Ordered list of provider names (e.g., ['tvmaze', 'tmdb']).
                                                  Used to prioritize title/overview selection.
    """
    sys.stdout.write(f"DEBUG: Entering create_nfo_file for episode: {episode.get('episode_number')}\n")
    sys.stdout.flush()

    # NFO file will have the same base name as the media file, but with a .nfo extension
    nfo_path = output_path.with_suffix(".nfo")

    season = episode.get("season_number")
    episode_num = episode.get("episode_number")

    # Initialize title and overview
    title = "Unknown"
    overview = ""

    # Get provider-specific titles and overviews from the episode dictionary
    title_dict = episode.get("titles", {})
    overview_dict = episode.get("overviews", {})

    # Use provider priority order to select the best title and overview
    if provider_priority_order:
        for provider in provider_priority_order:
            if provider in title_dict and title_dict[provider]:
                title = title_dict[provider]
                break # Found a title from a preferred provider, stop searching
        for provider in provider_priority_order:
            if provider in overview_dict and overview_dict[provider]:
                overview = overview_dict[provider]
                break # Found an overview from a preferred provider, stop searching
    
    # Fallback if no title/overview found from preferred providers (e.g., if provider_priority_order is empty or no data)
    if title == "Unknown" and isinstance(title_dict, dict):
        title = next(iter(title_dict.values()), "Unknown")
    elif title == "Unknown" and isinstance(title_dict, list) and title_dict: # Old format fallback
        title = title_dict[0]
    title = str(title) if title is not None else "Unknown" # Ensure title is string

    if not overview and isinstance(overview_dict, dict):
        overview = next(iter(overview_dict.values()), "")
    elif not overview and isinstance(overview_dict, list) and overview_dict: # Old format fallback
        overview = overview_dict[0]
    overview = str(overview) if overview is not None else ""


    # Ensure the output directory for the NFO file exists
    os.makedirs(nfo_path.parent, exist_ok=True)

    # NFO file content structure
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<episodedetails>
    <title>{title}</title>
    <season>{season}</season>
    <episode>{episode_num}</episode>
    <plot>{overview}</plot>
    <playcount>{playcount}</playcount>
    <lastplayed>{lastplayed}</lastplayed>
</episodedetails>
"""

    # Write the NFO content to the file, ensuring UTF-8 encoding
    try:
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(nfo_content)
        logging.info(f"Created NFO: {nfo_path}")
        sys.stdout.write(f"DEBUG: Created NFO: {nfo_path}\n")
        sys.stdout.flush()
    except Exception as e:
        logging.error(f"Error creating NFO file {nfo_path}: {e}")
        sys.stderr.write(f"DEBUG: Error creating NFO file {nfo_path}: {e}\n")
        sys.stderr.flush()

# ==============================================================================
# File Organization Logic
# ==============================================================================
def move_selected_recording_with_verification(source_path: Path, destination_path: Path) -> tuple:
    """Move the selected recording without overwriting and verify its recorded size."""
    if destination_path.exists():
        return False, "destination_collision", None
    source_size = source_path.stat().st_size
    try:
        shutil.move(str(source_path), str(destination_path))
    except Exception as exc:
        return False, f"move_failed: {exc}", source_size
    try:
        if not destination_path.is_file():
            return False, "verification_failed: destination file does not exist", source_size
        if destination_path.stat().st_size != source_size:
            return False, "verification_failed: destination size does not match source size", source_size
    except OSError as exc:
        return False, f"verification_failed: {exc}", source_size
    return True, "moved_and_verified", source_size


def unique_quarantine_path(path: Path) -> Path:
    """Return a non-existing quarantine path so an earlier quarantine is never overwritten."""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def quarantine_file(source_path: Path, quarantine_dir: Path) -> Path:
    """Move one rejected file to quarantine and return its recoverable location."""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_quarantine_path(quarantine_dir / source_path.name)
    shutil.move(str(source_path), str(destination))
    return destination


def write_action_manifest(manifest_path: Path, manifest: dict) -> None:
    """Atomically write a validated action manifest without damaging a prior manifest."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("actions"), list):
        raise ValueError("Action manifest must be an object containing an actions list")
    for required_field in ("schema_version", "run_id", "started_at", "updated_at",
                           "series", "mode", "run_status"):
        if not manifest.get(required_field):
            raise ValueError(f"Action manifest requires {required_field}")
    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    reparsed = json.loads(payload)
    if not isinstance(reparsed, dict) or not isinstance(reparsed.get("actions"), list):
        raise ValueError("Serialized action manifest has an invalid structure")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp_path, "x", encoding="utf-8", newline="\n") as manifest_file:
            manifest_file.write(payload)
            manifest_file.write("\n")
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        os.replace(temp_path, manifest_path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def utc_manifest_timestamp() -> str:
    """Return a sortable UTC timestamp suitable for JSON and filenames."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def create_action_manifest(series_name: str, move_files: bool, manifest_root: Path) -> tuple:
    """Create one retained run journal plus the compatibility latest-manifest path."""
    run_id = str(uuid.uuid4())
    started_at = utc_manifest_timestamp()
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "started_at": started_at,
        "updated_at": started_at,
        "series": series_name,
        "mode": "move" if move_files else "preview",
        "run_status": "in_progress",
        "actions": [],
    }
    series_manifest_root = Path(manifest_root) / series_name
    filename_timestamp = started_at.replace("-", "").replace(":", "").replace(".", "")
    run_path = series_manifest_root / "manifests" / f"{filename_timestamp}_{run_id}.json"
    latest_path = series_manifest_root / "file_organizer_manifest.json"
    return manifest, run_path, latest_path


def checkpoint_action_manifest(manifest: dict, run_path: Path, latest_path: Path) -> None:
    """Durably checkpoint the retained run journal, then its latest snapshot."""
    manifest["updated_at"] = utc_manifest_timestamp()
    write_action_manifest(run_path, manifest)
    write_action_manifest(latest_path, manifest)


def organize_files(series_name: str, episodes: list, tv_library_path: str, move_files: bool,
                   kodi_watched_data: dict, provider_priority_order: list,
                   preview_root: Path = PREVIEW_ROOT, quarantine_root: Path = QUARANTINE_ROOT):
    """
    Organizes media files by creating NFOs, selecting the best file,
    and optionally moving/deleting files to a standardized library structure.

    Args:
        series_name (str): The name of the TV series.
        episodes (list): A list of episode dictionaries from the processed JSON.
        tv_library_path (str): The base path for the TV series library.
        move_files (bool): If True, files will be moved and others deleted;
                           otherwise, only NFOs are created (dry run).
        kodi_watched_data (dict): A dictionary containing Kodi watched status for episodes.
        provider_priority_order (list): Ordered list of provider names (e.g., ['tvmaze', 'tmdb']).
                                        Used to prioritize title/overview selection for filenames.
    """
    sys.stdout.write(f"DEBUG: Entering organize_files for series: '{series_name}', move_files: {move_files}\n")
    sys.stdout.flush()
    logging.info(f"Starting file organization for '{series_name}'. Move files: {move_files}")
    manifest_root = Path(quarantine_root) if move_files else Path(preview_root)
    action_manifest, run_manifest_path, latest_manifest_path = create_action_manifest(
        series_name, move_files, manifest_root)
    checkpoint_action_manifest(action_manifest, run_manifest_path, latest_manifest_path)
    actions = action_manifest["actions"]

    # Import the current processed snapshot before any filesystem action. Preview reads
    # existing production history but writes only a proposed copy under Preview.
    production_history_path = (Path(tv_library_path) / series_name /
                               ".media_organizer" / "episode_history.json")
    history = load_history(production_history_path, series_name)
    merge_processed_episodes(history, episodes)
    history_path = (production_history_path if move_files else
                    Path(preview_root) / series_name / ".media_organizer" / "episode_history.json")
    atomic_write_history(history_path, history)

    for episode in episodes:
        season = episode.get("season_number")
        episode_num = episode.get("episode_number")

        # Skip if essential episode numbers are missing
        if season is None or episode_num is None:
            logging.warning(f"Skipping episode due to missing season or episode number: {episode}")
            sys.stdout.write(f"DEBUG: Skipping episode missing season/episode number: {episode}\n")
            sys.stdout.flush()
            continue

        # Titles is a dictionary of provider-specific titles. We need to pick one for filename.
        title_dict = episode.get("titles", {})
        title_for_filename = "Unknown"
        if provider_priority_order:
            for provider in provider_priority_order:
                if provider in title_dict and title_dict[provider]:
                    title_for_filename = title_dict[provider]
                    break
        # Fallback if no title found from preferred providers
        if title_for_filename == "Unknown" and isinstance(title_dict, dict):
            title_for_filename = next(iter(title_dict.values()), "Unknown")
        elif title_for_filename == "Unknown" and isinstance(title_dict, list) and title_dict: # Old format fallback
            title_for_filename = title_dict[0]
        title_for_filename = str(title_for_filename) if title_for_filename is not None else "Unknown"


        # Clean title for filename (remove problematic characters)
        cleaned_title = re.sub(r'[\\/:*?"<>|]', '', title_for_filename).strip()
        
        season_str = f"Season {season:02d}" # Format season folder name (e.g., "Season 01")
        
        logging.info(f"Processing episode S{season:02d}E{episode_num:02d}: '{title_for_filename}'")
        sys.stdout.write(f"DEBUG: Processing episode S{season:02d}E{episode_num:02d}: '{title_for_filename}'\n")
        sys.stdout.flush()
        
        # --- Kodi Watched Status Lookup ---
        # Create a lookup key for the current episode using series_name (lowercase), season, and episode number
        episode_lookup_key = (series_name.lower(), season, episode_num)
        # Retrieve watched status, defaulting to 0 playcount and empty lastplayed if not found
        watched_status = kodi_watched_data.get(episode_lookup_key, {"playcount": 0, "lastplayed": ""})
        
        current_playcount = watched_status["playcount"]
        current_lastplayed = watched_status["lastplayed"]

        # --- Best File Selection ---
        best_file_to_move_info = None
        # Filter out broken files and ensure they have a path and size
        files_to_consider = [f for f in episode.get("files", []) if not f.get("broken") and f.get("path") and f.get("size") is not None]

        if files_to_consider:
            # Sort by size in descending order to pick the largest non-broken file
            best_file_to_move_info = max(files_to_consider, key=lambda x: x.get("size", 0))
            logging.info(f"Selected best file for S{season:02d}E{episode_num:02d}: '{best_file_to_move_info.get('path')}' (Size: {best_file_to_move_info.get('size')} bytes)")
            sys.stdout.write(f"DEBUG: Selected best file: '{best_file_to_move_info.get('path')}'\n")
            sys.stdout.flush()
        else:
            logging.warning(f"No valid (non-broken) source files found for S{season:02d}E{episode_num:02d} - '{title_for_filename}'. Cannot move any file.")
            sys.stdout.write(f"DEBUG: No valid source files for S{season:02d}E{episode_num:02d}\n")
            sys.stdout.flush()

        # Determine the final file extension based on the best file, or a default
        file_ext = Path(best_file_to_move_info["path"]).suffix if best_file_to_move_info else ".ts"
        
        # Construct the new filename (e.g., "The A-Team - S01E01 - Pilot.ts")
        filename = f"{series_name} - S{season:02d}E{episode_num:02d} - {cleaned_title}{file_ext}"
        
        # Preview mirrors the real naming tree but is isolated from the TV library.
        output_root = Path(tv_library_path) if move_files else Path(preview_root)
        output_dir = output_root / series_name / season_str
        # Construct the full output path for the media file
        output_path = output_dir / filename
        
        # Preview NFOs are safe to create now. Move-mode NFOs wait for a verified media move.
        if not move_files:
            create_nfo_file(series_name, episode, output_path,
                            playcount=current_playcount,
                            lastplayed=current_lastplayed,
                            provider_priority_order=provider_priority_order)
        
        # --- File Movement and Deletion Logic ---
        if best_file_to_move_info: # Only proceed if a best file was identified
            best_file_to_move_path = best_file_to_move_info["path"]
            files_to_delete_paths = []

            # Identify all other files associated with this episode that are NOT the best file
            for file_info in episode.get("files", []):
                current_file_path = file_info["path"]
                # Ensure the file exists on disk before considering it for deletion
                if current_file_path != best_file_to_move_path and os.path.exists(current_file_path):
                    files_to_delete_paths.append(current_file_path)
                    # Also add associated .xml and .edl files for deletion if they exist
                    base_name_to_delete = Path(current_file_path).stem
                    xml_to_delete = Path(current_file_path).with_name(f"{base_name_to_delete}.xml")
                    edl_to_delete = Path(current_file_path).with_name(f"{base_name_to_delete}.edl")
                    if xml_to_delete.exists():
                        files_to_delete_paths.append(str(xml_to_delete))
                    if edl_to_delete.exists():
                        files_to_delete_paths.append(str(edl_to_delete))
            
            if move_files:
                if not os.path.exists(best_file_to_move_path):
                    logging.error(f"Source file for move not found: '{best_file_to_move_path}'.")
                    actions.append({"episode": f"S{season:02d}E{episode_num:02d}",
                                    "status": "source_missing", "source": best_file_to_move_path,
                                    "destination": str(output_path)})
                    checkpoint_action_manifest(
                        action_manifest, run_manifest_path, latest_manifest_path)
                    continue

                # A collision blocks every write and cleanup action for this episode.
                if output_path.exists():
                    logging.error(f"Destination collision blocks episode: '{output_path}'")
                    actions.append({"episode": f"S{season:02d}E{episode_num:02d}",
                                    "status": "destination_collision", "source": best_file_to_move_path,
                                    "destination": str(output_path)})
                    checkpoint_action_manifest(
                        action_manifest, run_manifest_path, latest_manifest_path)
                    continue

                os.makedirs(output_dir, exist_ok=True)
                verified, status, source_size = move_selected_recording_with_verification(
                    Path(best_file_to_move_path), output_path)
                physical_move_succeeded = not status.startswith("move_failed")
                action = {
                    "episode": f"S{season:02d}E{episode_num:02d}",
                    "status": status,
                    "source": best_file_to_move_path,
                    "intended_destination": str(output_path),
                    "actual_destination": str(output_path) if physical_move_succeeded else None,
                    "expected_size": source_size,
                    "physical_action_succeeded": physical_move_succeeded,
                    "history_recorded": False,
                    "error": None if verified else status,
                    "selected_sidecars": [],
                    "quarantined": [],
                }
                actions.append(action)
                # The physical selected-move result is durable before history is attempted.
                checkpoint_action_manifest(
                    action_manifest, run_manifest_path, latest_manifest_path)
                if not verified:
                    logging.error(f"Selected recording was not verified; preserving all alternatives: {status}")
                    continue

                logging.info(f"Moved and verified file: '{best_file_to_move_path}' -> '{output_path}'")
                current_episode_key = episode_key(season, episode_num)
                try:
                    history_candidate = copy.deepcopy(history)
                    selected_recording_id = record_verified_transition(
                        history_candidate, current_episode_key, best_file_to_move_path, str(output_path),
                        "library", "verified_selected_move", selected=True)
                    atomic_write_history(history_path, history_candidate)
                except Exception as exc:
                    action["status"] = "selected_move_succeeded_history_write_failed"
                    action["error"] = str(exc)
                    action["cleanup_stopped"] = True
                    checkpoint_action_manifest(
                        action_manifest, run_manifest_path, latest_manifest_path)
                    logging.error(
                        "Verified move was not recorded in durable history; preserving all alternatives: %s", exc)
                    continue
                history = history_candidate
                action["selected_recording_id"] = selected_recording_id
                action["history_recorded"] = True
                action["status"] = "selected_move_and_history_recorded"
                checkpoint_action_manifest(
                    action_manifest, run_manifest_path, latest_manifest_path)

                create_nfo_file(series_name, episode, output_path,
                                playcount=current_playcount, lastplayed=current_lastplayed,
                                provider_priority_order=provider_priority_order)

                # Selected sidecars move only after the selected media has been verified.
                selected_sidecar_failed = False
                for ext in [".xml", ".edl"]:
                    src_ext_path = Path(best_file_to_move_path).with_suffix(ext)
                    dst_ext_path = output_path.with_suffix(ext)
                    if not src_ext_path.exists():
                        continue
                    sidecar_action = {
                        "source": str(src_ext_path),
                        "intended_destination": str(dst_ext_path),
                        "actual_destination": None,
                        "physical_action_succeeded": False,
                        "history_recorded": False,
                        "error": None,
                    }
                    action["selected_sidecars"].append(sidecar_action)
                    if dst_ext_path.exists():
                        sidecar_action["status"] = "selected_sidecar_destination_collision"
                        sidecar_action["error"] = "destination already exists"
                        action["status"] = "selected_sidecar_move_failed"
                        action["error"] = sidecar_action["error"]
                        action["cleanup_stopped"] = True
                        selected_sidecar_failed = True
                        checkpoint_action_manifest(
                            action_manifest, run_manifest_path, latest_manifest_path)
                        break
                    try:
                        shutil.move(str(src_ext_path), str(dst_ext_path))
                        sidecar_action["status"] = "selected_sidecar_moved"
                        sidecar_action["actual_destination"] = str(dst_ext_path)
                        sidecar_action["physical_action_succeeded"] = True
                        checkpoint_action_manifest(
                            action_manifest, run_manifest_path, latest_manifest_path)
                    except Exception as exc:
                        sidecar_action["status"] = "selected_sidecar_move_failed"
                        sidecar_action["error"] = str(exc)
                        action["status"] = "selected_sidecar_move_failed"
                        action["error"] = str(exc)
                        action["cleanup_stopped"] = True
                        selected_sidecar_failed = True
                        logging.error(
                            "Selected sidecar move failed; preserving all alternatives: %s", exc)
                        checkpoint_action_manifest(
                            action_manifest, run_manifest_path, latest_manifest_path)
                        break

                if selected_sidecar_failed:
                    continue

                # Rejected recordings and sidecars are quarantined, never deleted.
                quarantine_dir = (Path(quarantine_root) / series_name / season_str /
                                  f"S{season:02d}E{episode_num:02d}")
                recording_source_paths = {
                    normalize_windows_path(file_info.get("path", ""))
                    for file_info in episode.get("files", []) if file_info.get("path")
                }
                for rejected_path_text in files_to_delete_paths:
                    rejected_path = Path(rejected_path_text)
                    if rejected_path.exists():
                        intended_quarantine_path = quarantine_dir / rejected_path.name
                        quarantine_action = {
                            "episode": current_episode_key,
                            "source": str(rejected_path),
                            "intended_destination": str(intended_quarantine_path),
                            "actual_destination": None,
                            "physical_action_succeeded": False,
                            "history_recorded": False,
                            "error": None,
                        }
                        action["quarantined"].append(quarantine_action)
                        checkpoint_action_manifest(
                            action_manifest, run_manifest_path, latest_manifest_path)
                        try:
                            quarantined_path = quarantine_file(rejected_path, quarantine_dir)
                        except Exception as exc:
                            quarantine_action["status"] = "physical_quarantine_failed"
                            quarantine_action["error"] = str(exc)
                            action["status"] = "physical_quarantine_failed"
                            action["error"] = str(exc)
                            action["cleanup_stopped"] = True
                            logging.error(f"Physical quarantine failed for '{rejected_path}': {exc}")
                            checkpoint_action_manifest(
                                action_manifest, run_manifest_path, latest_manifest_path)
                            break

                        quarantine_action["status"] = "physical_quarantine_succeeded"
                        quarantine_action["actual_destination"] = str(quarantined_path)
                        quarantine_action["physical_action_succeeded"] = True
                        # Record the physical move before attempting its history transition.
                        checkpoint_action_manifest(
                            action_manifest, run_manifest_path, latest_manifest_path)
                        if normalize_windows_path(str(rejected_path)) in recording_source_paths:
                            try:
                                history_candidate = copy.deepcopy(history)
                                quarantine_recording_id = record_verified_transition(
                                    history_candidate, current_episode_key, str(rejected_path), str(quarantined_path),
                                    "quarantine", "verified_quarantine")
                                atomic_write_history(history_path, history_candidate)
                            except Exception as exc:
                                quarantine_action["status"] = (
                                    "physical_quarantine_succeeded_history_write_failed")
                                quarantine_action["error"] = str(exc)
                                action["status"] = (
                                    "physical_quarantine_succeeded_history_write_failed")
                                action["error"] = str(exc)
                                action["cleanup_stopped"] = True
                                logging.error(
                                    "Physical quarantine succeeded but durable history write failed "
                                    "for '%s' at '%s'; stopping cleanup: %s",
                                    rejected_path, quarantined_path, exc)
                                checkpoint_action_manifest(
                                    action_manifest, run_manifest_path, latest_manifest_path)
                                break
                            history = history_candidate
                            quarantine_action["recording_id"] = quarantine_recording_id
                            quarantine_action["history_recorded"] = True
                            quarantine_action["status"] = "quarantined_and_history_recorded"
                            checkpoint_action_manifest(
                                action_manifest, run_manifest_path, latest_manifest_path)
                        else:
                            quarantine_action["status"] = "companion_quarantined"
                            checkpoint_action_manifest(
                                action_manifest, run_manifest_path, latest_manifest_path)
                        logging.info(f"Quarantined file: '{rejected_path}' -> '{quarantined_path}'")
                if not action.get("cleanup_stopped"):
                    action["status"] = "episode_completed"
                    checkpoint_action_manifest(
                        action_manifest, run_manifest_path, latest_manifest_path)

            else: # Dry Run
                actions.append({"episode": f"S{season:02d}E{episode_num:02d}",
                                "status": "preview", "source": best_file_to_move_path,
                                "destination": str(Path(tv_library_path) / series_name / season_str / filename),
                                "preview_nfo": str(output_path.with_suffix('.nfo')),
                                "would_quarantine": files_to_delete_paths})
                checkpoint_action_manifest(
                    action_manifest, run_manifest_path, latest_manifest_path)
                # Log what would happen (move)
                if os.path.exists(best_file_to_move_path):
                    logging.info(f"DRY RUN: Would move file: '{best_file_to_move_path}' -> '{output_path}'")
                    sys.stdout.write(f"DEBUG: DRY RUN: Would move file: '{best_file_to_move_path}' -> '{output_path}'\n")
                    sys.stdout.flush()
                    # Log associated .xml and .edl files for the best file that would be moved
                    for ext in [".xml", ".edl"]:
                        src_ext_path = Path(best_file_to_move_path).with_suffix(ext)
                        dst_ext_path = output_path.with_suffix(ext)
                        if src_ext_path.exists():
                            logging.info(f"DRY RUN: Would move {ext}: '{src_ext_path}' -> '{dst_ext_path}'")
                            sys.stdout.write(f"DEBUG: DRY RUN: Would move {ext}: '{src_ext_path}' -> '{dst_ext_path}'\n")
                            sys.stdout.flush()
                else:
                    logging.info(f"DRY RUN: Source file for move not found: '{best_file_to_move_path}'. Skipping dry run move.")
                    sys.stdout.write(f"DEBUG: DRY RUN: Source file for move not found: '{best_file_to_move_path}'\n")
                    sys.stdout.flush()

                # Log what would happen (delete)
                for file_to_delete_path in files_to_delete_paths:
                    if os.path.exists(file_to_delete_path):
                        logging.info(f"DRY RUN: Would quarantine file: '{file_to_delete_path}'")
                        sys.stdout.write(f"DEBUG: DRY RUN: Would quarantine file: '{file_to_delete_path}'\n")
                        sys.stdout.flush()
                    else:
                        logging.debug(f"DRY RUN: File to delete not found (already gone?): '{file_to_delete_path}'")
                        sys.stdout.write(f"DEBUG: DRY RUN: File to delete not found: '{file_to_delete_path}'\n")
                        sys.stdout.flush()
        else:
            logging.info(f"No best file identified for S{season:02d}E{episode_num:02d} - '{title_for_filename}'. No files to move or delete.")
            sys.stdout.write(f"DEBUG: No best file identified for S{season:02d}E{episode_num:02d}\n")
            sys.stdout.flush()
            actions.append({"episode": f"S{season:02d}E{episode_num:02d}",
                            "status": "episode_completed_no_valid_recording"})
            checkpoint_action_manifest(
                action_manifest, run_manifest_path, latest_manifest_path)

    action_manifest["run_status"] = "completed"
    checkpoint_action_manifest(action_manifest, run_manifest_path, latest_manifest_path)


# ==============================================================================
# Main Execution
# ==============================================================================
def main():
    """Main function to parse arguments, load data, and organize files."""
    parser = argparse.ArgumentParser(description="Organize media files for a TV series.")
    parser.add_argument("series_name", help="Name of the series (e.g., 'The A-Team').")
    parser.add_argument("--move", action="store_true", help="If set, files will be moved and others deleted; otherwise, only NFOs are created (dry run).")
    args = parser.parse_args()

    # --- Start of main logic, wrapped in try-except for robust error reporting ---
    try:
        # Setup logging for the specific series
        series_slug = setup_logging(args.series_name)
        sys.stdout.write(f"DEBUG: Returned from setup_logging, series_slug: '{series_slug}'\n")
        sys.stdout.flush()
        # Initial logging info about script start is now handled within setup_logging

        # Load paths from config/paths.txt
        paths = load_paths()
        sys.stdout.write(f"DEBUG: Returned from load_paths, loaded paths: {paths}\n")
        sys.stdout.flush()
        
        tv_library_path = paths.get("TV_LIBRARY_PATH")
        json_folder = paths.get("JSON_FOLDER")
        provider_priority_order = paths.get("PROVIDER_PRIORITY_ORDER", []) # Get the new provider priority list

        # Validate essential paths
        if not tv_library_path:
            logging.error("TV_LIBRARY_PATH not found in paths.txt. Cannot proceed.")
            sys.stdout.write("DEBUG: TV_LIBRARY_PATH missing. Exiting.\n")
            sys.stdout.flush()
            return # Exit if critical path is missing
        if not json_folder:
            logging.error("JSON_FOLDER not found in paths.txt. Cannot proceed.")
            sys.stdout.write("DEBUG: JSON_FOLDER missing. Exiting.\n")
            sys.stdout.flush()
            return # Exit if critical path is missing
        if not provider_priority_order:
            logging.warning("No enabled metadata providers found in paths.txt [meta_providers] section. Defaulting to no specific provider priority for titles/overviews.")
            sys.stdout.write("DEBUG: No PROVIDER_PRIORITY_ORDER found. Titles/Overviews may not be optimal.\n")
            sys.stdout.flush()


        logging.info(f"Using TV_LIBRARY_PATH = '{tv_library_path}'")
        logging.info(f"Using JSON_FOLDER = '{json_folder}'")
        sys.stdout.write(f"DEBUG: Using TV_LIBRARY_PATH = '{tv_library_path}'\n")
        sys.stdout.flush()
        sys.stdout.write(f"DEBUG: Using JSON_FOLDER = '{json_folder}'\n")
        sys.stdout.flush()

        # Construct the full path to the Kodi watched JSON file
        # This path follows the convention: <JSON_FOLDER>/<series_slug>/<series_slug>_kodi_watched.json
        series_slug_folder = args.series_name.lower().replace(" ", "_").replace("-", "_")
        kodi_watched_json_filename = f"{series_slug_folder}_kodi_watched.json"
        kodi_watched_json_path = Path(json_folder) / series_slug_folder / kodi_watched_json_filename

        sys.stdout.write(f"DEBUG: Constructed Kodi watched JSON path: '{kodi_watched_json_path}'\n")
        sys.stdout.flush()

        # Load the processed JSON data for the series (contains episode metadata and file info)
        episodes = load_processed_json(args.series_name, json_folder)
        sys.stdout.write(f"DEBUG: Returned from load_processed_json, loaded {len(episodes)} episodes.\n")
        sys.stdout.flush()
        if not episodes:
            logging.warning("No episodes loaded from processed JSON. Exiting.")
            sys.stdout.write("DEBUG: No episodes loaded. Exiting.\n")
            sys.stdout.flush()
            return # Exit if no episode data is loaded

        # Load Kodi watched data if USE_KODI is enabled in paths.txt
        kodi_watched_data = {}
        if paths.get("USE_KODI"):
            kodi_watched_data = load_kodi_watched_data(str(kodi_watched_json_path))
            sys.stdout.write(f"DEBUG: Returned from load_kodi_watched_data, loaded {len(kodi_watched_data)} watched entries.\n")
            sys.stdout.flush()
        else:
            logging.info("USE_KODI is False in paths.txt. Skipping Kodi watched data loading.")
            sys.stdout.write("DEBUG: USE_KODI is False.\n")
            sys.stdout.flush()
        
        # Verify the --move flag's value for debugging
        sys.stdout.write(f"DEBUG: Value of args.move: {args.move}\n")
        sys.stdout.flush()

        # Perform the file organization (NFO creation, optional move/delete)
        organize_files(args.series_name, episodes, tv_library_path, args.move, kodi_watched_data, provider_priority_order)
        sys.stdout.write("DEBUG: Returned from organize_files.\n")
        sys.stdout.flush()
        logging.info("File organization complete.")

    except Exception as e:
        # Catch any unhandled exception during script execution
        logging.exception(f"An unhandled error occurred during script execution for '{args.series_name}': {e}")
        sys.stderr.write(f"\nERROR: An unhandled error occurred during script execution for '{args.series_name}': {e}\n")
        sys.stderr.write(traceback.format_exc()) # Print full traceback to stderr
        sys.stderr.flush()
        sys.exit(1) # Exit with an error code

if __name__ == "__main__":
    main()
