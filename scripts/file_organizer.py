# file_organizer.py
# Version 0.9.13 (DEBUGGING EARLY FAILURE)
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

import os
import json
import argparse
import logging
from datetime import datetime
import shutil
from pathlib import Path
import configparser
import sys
import re
import traceback # Import traceback for detailed error info

sys.stdout.write("DEBUG: Script started. This should always appear.\n")
sys.stdout.flush()

def setup_logging(series_name: str) -> str:
    sys.stdout.write(f"DEBUG: Entering setup_logging with series_name: '{series_name}'\n")
    sys.stdout.flush()
    series_slug = series_name.lower().replace(" ", "_").replace("-", "_")
    log_dir = Path("logs") / series_slug
    
    try:
        os.makedirs(log_dir, exist_ok=True)
        sys.stdout.write(f"DEBUG: Log directory ensured: '{log_dir}'\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"ERROR: Could not create log directory '{log_dir}': {e}\n")
        sys.stderr.flush()
        # Fallback to console handler if directory creation fails
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logging.root.addHandler(console_handler) # Add to root logger
        logging.root.error(f"Failed to create log directory: {e}. Logging to console only.")
        return series_slug # Return early if directory creation failed

    # Clear existing handlers to prevent duplicate log entries on re-runs
    # This should be done on the root logger for basicConfig to work correctly
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()

    log_file = log_dir / "file_organizer.log"
    try:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="[%(asctime)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        sys.stdout.write(f"DEBUG: File logger configured to: '{log_file}'\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to set up file logger at '{log_file}': {e}\n")
        sys.stderr.flush()
        # Fallback to console logging if file logging fails
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logging.root.addHandler(console_handler)
        logging.root.error(f"Failed to set up file logger: {e}. Logging to console.")

    logging.info(f"File Organizer v0.9.13 starting for series: '{series_name}'")
    sys.stdout.write(f"DEBUG: Leaving setup_logging, series_slug: '{series_slug}'\n")
    sys.stdout.flush()
    return series_slug

def load_paths() -> dict:
    sys.stdout.write("DEBUG: Entering load_paths()\n")
    sys.stdout.flush()
    paths = {}
    config_parser = configparser.ConfigParser()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.stdout.write(f"DEBUG: Script directory: '{script_dir}'\n")
    sys.stdout.flush()
    config_path = os.path.join(script_dir, "..", "config", "paths.txt")
    sys.stdout.write(f"DEBUG: Attempting to load config from: '{config_path}'\n")
    sys.stdout.flush()

    if not os.path.exists(config_path):
        config_path = os.path.join("config", "paths.txt")
        sys.stdout.write(f"DEBUG: First path not found, trying: '{config_path}'\n")
        sys.stdout.flush()
        if not os.path.exists(config_path):
            sys.stderr.write(f"ERROR: Configuration file not found at: {config_path}\n")
            sys.stderr.flush()
            raise FileNotFoundError(f"paths.txt not found at {config_path}")

    try:
        config_parser.read(config_path)
        sys.stdout.write("DEBUG: config_parser.read() successful.\n")
        sys.stdout.flush()

        paths["TV_LIBRARY_PATH"] = config_parser.get("library_paths", "TV_LIBRARY_PATH").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded TV_LIBRARY_PATH: '{paths['TV_LIBRARY_PATH']}'\n")
        sys.stdout.flush()
        paths["MOVIE_LIBRARY_PATH"] = config_parser.get("library_paths", "MOVIE_LIBRARY_PATH").strip('"').strip()
        sys.stdout.write(f"DEBUG: Loaded MOVIE_LIBRARY_PATH: '{paths['MOVIE_LIBRARY_PATH']}'\n")
        sys.stdout.flush()
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

        sys.stdout.write("DEBUG: Successfully loaded paths from config.\n")
        sys.stdout.flush()

    except configparser.NoSectionError as e:
        logging.error(f"Error loading configuration: Section '{e.section}' not found in {config_path}")
        sys.stderr.write(f"DEBUG: configparser.NoSectionError: {e}\n")
        sys.stderr.flush()
        raise
    except configparser.NoOptionError as e:
        logging.error(f"Error loading configuration: Option '{e.option}' not found in section '{e.section}' in {config_path}")
        sys.stderr.write(f"DEBUG: configparser.NoOptionError: {e}\n")
        sys.stderr.flush()
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading configuration: {e}")
        sys.stderr.write(f"DEBUG: Unexpected error in load_paths: {e}\n")
        sys.stderr.flush()
        raise

    sys.stdout.write(f"DEBUG: Leaving load_paths(), loaded paths: {paths}\n")
    sys.stdout.flush()
    return paths

def load_processed_json(series_name: str, json_folder: str) -> list:
    sys.stdout.write(f"DEBUG: Entering load_processed_json with series_name: '{series_name}', json_folder: '{json_folder}'\n")
    sys.stdout.flush()
    series_slug_folder = series_name.lower().replace(" ", "_").replace("-", "_")
    json_path = Path(json_folder) / series_slug_folder / f"{series_name.replace(' ', '_')}_Processed.json"
    sys.stdout.write(f"DEBUG: Attempting to load processed JSON from: '{json_path}'\n")
    sys.stdout.flush()
    
    if not json_path.exists():
        logging.error(f"Processed JSON file not found: {json_path}")
        sys.stdout.write(f"DEBUG: Processed JSON file not found: {json_path}\n")
        sys.stdout.flush()
        return []
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        episodes = []
        # Iterate through seasons and episodes to flatten the structure
        for season in data.get("seasons", []):
            season_num = season.get("season_number")
            if season_num is None:
                logging.warning(f"Skipping season with missing 'season_number' in {json_path}. Season data: {season}")
                sys.stdout.write(f"DEBUG: Skipping season with missing 'season_number': {season}\n")
                sys.stdout.flush()
                continue
            for episode in season.get("episodes", []):
                episode["season_number"] = season_num # Add season_number to each episode for easier access
                episodes.append(episode)
        
        logging.info(f"Successfully loaded {len(episodes)} episodes from {json_path}")
        sys.stdout.write(f"DEBUG: Successfully loaded {len(episodes)} episodes from {json_path}\n")
        sys.stdout.flush()
        return episodes
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {json_path}: {e}")
        sys.stderr.write(f"DEBUG: Error decoding JSON from {json_path}: {e}\n")
        sys.stderr.flush()
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading JSON from {json_path}: {e}")
        sys.stderr.write(f"DEBUG: Unexpected error loading JSON from {json_path}: {e}\n")
        sys.stderr.flush()
        return []

def load_kodi_watched_data(kodi_watched_json_path: str) -> dict:
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
        return {}

    try:
        with open(kodi_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "series_name" not in data or "seasons" not in data:
            logging.error(f"Kodi watched JSON has unexpected top-level structure. Expected a dict with 'series_name' and 'seasons'. Skipping watched status loading.")
            sys.stderr.write(f"DEBUG: Kodi watched JSON unexpected structure: {type(data)}\n")
            sys.stderr.flush()
            return {}

        series_name_kodi_base = data.get("series_name", "").lower()
        seasons_data = data.get("seasons", [])

        for season in seasons_data:
            season_num_kodi = season.get("season_number")
            episodes_data = season.get("episodes", [])

            if season_num_kodi is not None and isinstance(episodes_data, list):
                for episode in episodes_data:
                    episode_num_kodi = episode.get("episode_number")
                    watched = episode.get("watched", False)
                    last_played = episode.get("last_played", "")

                    if episode_num_kodi is not None:
                        key = (series_name_kodi_base, int(season_num_kodi), int(episode_num_kodi))
                        watched_data[key] = {
                            "playcount": 1 if watched else 0,  # Assuming 'watched: true' means playcount = 1
                            "lastplayed": last_played
                        }
                    else:
                        logging.warning(f"Skipping Kodi watched entry due to missing essential fields: {episode}")
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
        logging.error(f"Error decoding Kodi watched JSON from {kodi_json_path}: {e}. Skipping watched status loading.")
        sys.stderr.write(f"DEBUG: Error decoding Kodi watched JSON: {e}\n")
        sys.stderr.flush()
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading Kodi watched data from {kodi_json_path}: {e}. Skipping watched status loading.")
        sys.stderr.write(f"DEBUG: Unexpected error loading Kodi watched data: {e}\n")
        sys.stderr.flush()
        return {}


def create_nfo_file(series_name: str, episode: dict, output_path: Path, playcount: int = 0, lastplayed: str = ""):
    sys.stdout.write(f"DEBUG: Entering create_nfo_file for episode: {episode.get('episode_number')}\n")
    sys.stdout.flush()
    # NFO file will have the same base name as the media file, but with a .nfo extension
    nfo_path = output_path.with_suffix(".nfo")

    season = episode.get("season_number")
    episode_num = episode.get("episode_number")

    # Titles is a dictionary of provider-specific titles. We need to pick one.
    # Prioritize 'tvmaze', 'tmdb', 'trakt', then any available, or default to "Unknown".
    title_dict = episode.get("titles", {})
    if isinstance(title_dict, dict):
        title = title_dict.get("tvmaze") or title_dict.get("tmdb") or title_dict.get("trakt")
        if not title:
            # Fallback to the first title found if specific providers are not available
            title = next(iter(title_dict.values()), "Unknown")
    else: # Fallback for old format if titles is a list or string
        title = title_dict[0] if isinstance(title_dict, list) and title_dict else "Unknown"
        title = str(title) if title is not None else "Unknown" # Ensure title is string

    overview_dict = episode.get("overviews", {})
    overview = ""
    if isinstance(overview_dict, dict):
        overview = overview_dict.get("tvmaze") or overview_dict.get("tmdb") or overview_dict.get("trakt")
        if not overview:
            overview = next(iter(overview_dict.values()), "")
    else: # Fallback for old format if overviews is a list or string
        overview = overview_dict[0] if isinstance(overview_dict, list) and overview_dict else ""
        overview = str(overview) if overview is not None else ""

    # Ensure output directory for NFO exists
    os.makedirs(nfo_path.parent, exist_ok=True)

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


def organize_files(series_name: str, episodes: list, tv_library_path: str, move_files: bool, kodi_watched_data: dict):
    sys.stdout.write(f"DEBUG: Entering organize_files for series: '{series_name}', move_files: {move_files}\n")
    sys.stdout.flush()
    logging.info(f"Starting file organization for '{series_name}'. Move files: {move_files}")

    for episode in episodes:
        season = episode.get("season_number")
        episode_num = episode.get("episode_number")

        # Skip if essential episode numbers are missing
        if season is None or episode_num is None:
            logging.warning(f"Skipping episode due to missing season or episode number: {episode}")
            sys.stdout.write(f"DEBUG: Skipping episode missing season/episode number: {episode}\n")
            sys.stdout.flush()
            continue

        # Titles is a dictionary of provider-specific titles. We need to pick one.
        # Prioritize 'tvmaze', 'tmdb', 'trakt', then any available, or default to "Unknown".
        title_dict = episode.get("titles", {})
        if isinstance(title_dict, dict):
            title = title_dict.get("tvmaze") or title_dict.get("tmdb") or title_dict.get("trakt")
            if not title:
                title = next(iter(title_dict.values()), "Unknown")
        else: # Fallback for old format if titles is a list or string
            title = title_dict[0] if isinstance(title_dict, list) and title_dict else "Unknown"
            title = str(title) if title is not None else "Unknown" # Ensure title is string

        # Clean title for filename (remove problematic characters)
        cleaned_title = re.sub(r'[\\/:*?"<>|]', '', title).strip()
        
        season_str = f"Season {season:02d}" # Format season folder name (e.g., "Season 01")
        
        # Placeholder for actual file extension. In a real scenario, this would come from the 'file' info.
        file_ext = ".ts" # Default, assuming common recording format
        if episode.get("files"):
            # Try to get the extension from the first valid file if available
            for f_info in episode["files"]:
                if not f_info.get("broken") and f_info.get("path"):
                    file_ext = Path(f_info["path"]).suffix
                    break
        
        filename = f"{series_name} - S{season:02d}E{episode_num:02d} - {cleaned_title}{file_ext}"
        
        # Construct the full output directory path for the episode
        output_dir = Path(tv_library_path) / series_name / season_str
        # Construct the full output path for the media file
        output_path = output_dir / filename
        
        logging.info(f"Processing episode S{season:02d}E{episode_num:02d}: '{title}'")
        sys.stdout.write(f"DEBUG: Processing episode S{season:02d}E{episode_num:02d}: '{title}'\n")
        sys.stdout.flush()
        
        # --- Kodi Watched Status Lookup ---
        # Create a lookup key for the current episode
        episode_lookup_key = (series_name.lower(), season, episode_num)
        watched_status = kodi_watched_data.get(episode_lookup_key, {"playcount": 0, "lastplayed": ""})
        
        current_playcount = watched_status["playcount"]
        current_lastplayed = watched_status["lastplayed"]

        # Create NFO file regardless of 'move_files' flag, passing watched status
        create_nfo_file(series_name, episode, output_path,
                        playcount=current_playcount,
                        lastplayed=current_lastplayed)
        
        if move_files:
            # Ensure the output directory exists before moving
            os.makedirs(output_dir, exist_ok=True)
            
            # Find the best file to move (assuming 'files' list exists and contains 'path' and 'broken' status)
            best_file_to_move = None
            if episode.get("files"):
                # Simple logic: pick the first non-broken file. More complex logic might be needed.
                for file_info in episode["files"]:
                    if not file_info.get("broken") and file_info.get("path"):
                        best_file_to_move = file_info["path"]
                        break
            
            if best_file_to_move and os.path.exists(best_file_to_move):
                try:
                    shutil.move(best_file_to_move, output_path)
                    logging.info(f"Moved file: '{best_file_to_move}' -> '{output_path}'")
                    sys.stdout.write(f"DEBUG: Moved file: '{best_file_to_move}' -> '{output_path}'\n")
                    sys.stdout.flush()
                    
                    # Move associated .xml and .edl files (assuming they are in the same directory as src_path)
                    for ext in [".xml", ".edl"]:
                        src_ext_path = Path(best_file_to_move).with_suffix(ext)
                        dst_ext_path = output_path.with_suffix(ext)
                        if src_ext_path.exists():
                            shutil.move(src_ext_path, dst_ext_path)
                            logging.info(f"Moved {ext}: '{src_ext_path}' -> '{dst_ext_path}'")
                            sys.stdout.write(f"DEBUG: Moved {ext}: '{src_ext_path}' -> '{dst_ext_path}'\n")
                            sys.stdout.flush()
                except Exception as e:
                    logging.error(f"Error moving file '{best_file_to_move}' to '{output_path}': {e}")
                    sys.stderr.write(f"DEBUG: Error moving file '{best_file_to_move}' to '{output_path}': {e}\n")
                    sys.stderr.flush()
            else:
                logging.warning(f"No valid source file found to move for S{season:02d}E{episode_num:02d} - '{title}'.")
                sys.stdout.write(f"DEBUG: No valid source file to move for S{season:02d}E{episode_num:02d}\n")
                sys.stdout.flush()
        else:
            # Log what would happen if move_files was True (Dry Run)
            if episode.get("files"):
                best_file_to_move = None
                for file_info in episode["files"]:
                    if not file_info.get("broken") and file_info.get("path"):
                        best_file_to_move = file_info["path"]
                        break
                if best_file_to_move:
                    logging.info(f"DRY RUN: Would move file: '{best_file_to_move}' -> '{output_path}'")
                    sys.stdout.write(f"DEBUG: DRY RUN: Would move file: '{best_file_to_move}' -> '{output_path}'\n")
                    sys.stdout.flush()
                    for ext in [".xml", ".edl"]:
                        src_ext_path = Path(best_file_to_move).with_suffix(ext)
                        dst_ext_path = output_path.with_suffix(ext)
                        if src_ext_path.exists():
                            logging.info(f"DRY RUN: Would move {ext}: '{src_ext_path}' -> '{dst_ext_path}'")
                            sys.stdout.write(f"DEBUG: DRY RUN: Would move {ext}: '{src_ext_path}' -> '{dst_ext_path}'\n")
                            sys.stdout.flush()
                else:
                    logging.info(f"DRY RUN: No valid source file found to move for S{season:02d}E{episode_num:02d} - '{title}'.")
                    sys.stdout.write(f"DEBUG: DRY RUN: No valid source file to move for S{season:02d}E{episode_num:02d}\n")
                    sys.stdout.flush()
            else:
                logging.info(f"DRY RUN: No 'files' information available for S{season:02d}E{episode_num:02d} - '{title}'. No files to move.")
                sys.stdout.write(f"DEBUG: DRY RUN: No 'files' info for S{season:02d}E{episode_num:02d}\n")
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Organize media files for a TV series.")
    parser.add_argument("series_name", help="Name of the series (e.g., 'The A-Team').")
    parser.add_argument("--move", action="store_true", help="If set, files will be moved; otherwise, only NFOs are created (dry run).")
    args = parser.parse_args()

    # --- Start of main logic, wrapped in try-except for robust error reporting ---
    try:
        series_slug = setup_logging(args.series_name)
        sys.stdout.write(f"DEBUG: Returned from setup_logging, series_slug: '{series_slug}'\n")
        sys.stdout.flush()
        # logging.info is now handled within setup_logging for the initial message
        # logging.info(f"=== File Organizer v0.9.13 Started for '{args.series_name}' ===")

        paths = load_paths()
        sys.stdout.write(f"DEBUG: Returned from load_paths, loaded paths: {paths}\n")
        sys.stdout.flush()
        tv_library_path = paths.get("TV_LIBRARY_PATH")
        json_folder = paths.get("JSON_FOLDER")

        if not tv_library_path:
            logging.error("TV_LIBRARY_PATH not found in paths.txt. Cannot proceed.")
            sys.stdout.write("DEBUG: TV_LIBRARY_PATH missing. Exiting.\n")
            sys.stdout.flush()
            return
        if not json_folder:
            logging.error("JSON_FOLDER not found in paths.txt. Cannot proceed.")
            sys.stdout.write("DEBUG: JSON_FOLDER missing. Exiting.\n")
            sys.stdout.flush()
            return

        logging.info(f"Using TV_LIBRARY_PATH = '{tv_library_path}'")
        logging.info(f"Using JSON_FOLDER = '{json_folder}'")
        sys.stdout.write(f"DEBUG: Using TV_LIBRARY_PATH = '{tv_library_path}'\n")
        sys.stdout.flush()
        sys.stdout.write(f"DEBUG: Using JSON_FOLDER = '{json_folder}'\n")
        sys.stdout.flush()

        series_slug_folder = args.series_name.lower().replace(" ", "_").replace("-", "_")
        kodi_watched_json_filename = f"{series_slug_folder}_kodi_watched.json"
        kodi_watched_json_path = Path(json_folder) / series_slug_folder / kodi_watched_json_filename

        sys.stdout.write(f"DEBUG: Constructed Kodi watched JSON path: '{kodi_watched_json_path}'\n")
        sys.stdout.flush()

        episodes = load_processed_json(args.series_name, json_folder)
        sys.stdout.write(f"DEBUG: Returned from load_processed_json, loaded {len(episodes)} episodes.\n")
        sys.stdout.flush()
        if not episodes:
            logging.warning("No episodes loaded from processed JSON. Exiting.")
            sys.stdout.write("DEBUG: No episodes loaded. Exiting.\n")
            sys.stdout.flush()
            return

        kodi_watched_data = {}
        if paths.get("USE_KODI"):
            kodi_watched_data = load_kodi_watched_data(str(kodi_watched_json_path))
            sys.stdout.write(f"DEBUG: Returned from load_kodi_watched_data, loaded {len(kodi_watched_data)} watched entries.\n")
            sys.stdout.flush()
        else:
            logging.info("USE_KODI is False in paths.txt. Skipping Kodi watched data loading.")
            sys.stdout.write("DEBUG: USE_KODI is False.\n")
            sys.stdout.flush()
        
        # Verify the --move flag's value here
        sys.stdout.write(f"DEBUG: Value of args.move: {args.move}\n")
        sys.stdout.flush()

        organize_files(args.series_name, episodes, tv_library_path, args.move, kodi_watched_data)
        sys.stdout.write("DEBUG: Returned from organize_files.\n")
        sys.stdout.flush()
        logging.info("File organization complete.")

    except Exception as e:
        logging.exception(f"An unhandled error occurred during script execution for '{args.series_name}': {e}")
        sys.stderr.write(f"\nERROR: An unhandled error occurred during script execution for '{args.series_name}': {e}\n")
        sys.stderr.write(traceback.format_exc()) # Print full traceback to stderr
        sys.stderr.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()
