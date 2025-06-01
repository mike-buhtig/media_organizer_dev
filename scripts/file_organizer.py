# file_organizer.py
# Version 0.9.6
# Orchestrates the organization of TV series media files, including NFO creation and optional file movement.
#
# Change Log:
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

import os
import json
import argparse
import logging
from datetime import datetime
import shutil
from pathlib import Path # Import Path for robust path handling
import configparser  # Add this import
import sys  # Import sys for stderr
import re   # Import the regular expression module

def setup_logging(series_name: str) -> str:
    """
    Sets up logging for the file_organizer script.
    Logs are directed to a series-specific file within the 'logs' directory.

    Args:
        series_name (str): The name of the TV series.

    Returns:
        str: The slugified version of the series name used for log directory.
    """
    series_slug = series_name.lower().replace(" ", "_").replace("-", "_") # Ensure consistency with folder names
    log_dir = Path("logs") / series_slug # Use Path for consistent robust joining
    os.makedirs(log_dir, exist_ok=True) # Ensure log directory exists
    log_file = log_dir / "file_organizer.log" # Use Path for robust joining
    
    # Configure logging. Clear existing handlers to prevent duplicate logs if called multiple times.
    # This ensures a clean slate for logging configuration.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.info(f"File Organizer v0.9.6 starting for series: '{series_name}'")
    return series_slug

def load_paths() -> dict:
    """
    Loads configuration paths from 'config/paths.txt'.
    """
    paths = {}
    config_parser = configparser.ConfigParser()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "..", "config", "paths.txt")

    if not os.path.exists(config_path):
        config_path = os.path.join("config", "paths.txt")
        if not os.path.exists(config_path):
            sys.stderr.write(f"ERROR: Configuration file not found at: {config_path}\n")
            sys.stderr.flush()
            raise FileNotFoundError(f"paths.txt not found at {config_path}")

    config_parser.read(config_path)
    logging.info(f"Loaded configuration from: {config_path}")

    try:
        paths["TV_LIBRARY_PATH"] = config_parser.get("library_paths", "TV_LIBRARY_PATH").strip('"').strip()
        paths["MOVIE_LIBRARY_PATH"] = config_parser.get("library_paths", "MOVIE_LIBRARY_PATH").strip('"').strip()
        paths["JSON_FOLDER"] = config_parser.get("general", "JSON_FOLDER", fallback="data").strip('"').strip()
        paths["LOG_PATH"] = config_parser.get("general", "LOG_PATH", fallback="logs").strip('"').strip()
        paths["TEMP_FOLDER"] = config_parser.get("general", "TEMP_FOLDER", fallback="tmp").strip('"').strip()
        paths["USE_KODI"] = config_parser.getboolean("general", "USE_KODI", fallback=False)
        paths["USE_NEXTPVR"] = config_parser.getboolean("general", "USE_NEXTPVR", fallback=False)
        paths["OPERATION_MODE"] = config_parser.get("general", "OPERATION_MODE", fallback="move").strip('"').strip()
        paths["CREATE_NFO"] = config_parser.getboolean("general", "CREATE_NFO", fallback=True)

    except configparser.NoSectionError as e:
        logging.error(f"Error loading configuration: Section '{e.section}' not found in {config_path}")
        raise
    except configparser.NoOptionError as e:
        logging.error(f"Error loading configuration: Option '{e.option}' not found in section '{e.section}' in {config_path}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading configuration: {e}")
        raise

    return paths

def load_processed_json(series_name: str, json_folder: str) -> list:
    """
    Loads the processed JSON metadata for a given series.
    This JSON contains details about episodes, including their original file paths.

    Args:
        series_name (str): The name of the TV series.
        json_folder (str): The base directory where JSON files are stored (e.g., 'data').

    Returns:
        list: A list of episode dictionaries, with season_number added to each episode.
    """
    series_slug_folder = series_name.lower().replace(" ", "_").replace("-", "_") # Consistent slug for folder
    json_path = Path(json_folder) / series_slug_folder / f"{series_name.replace(' ', '_')}_Processed.json"
    
    logging.info(f"Attempting to load processed JSON from: {json_path}")
    
    if not json_path.exists():
        logging.error(f"Processed JSON file not found: {json_path}")
        return []
    
    try:
        with open(json_path, "r", encoding="utf-8") as f: # Ensure UTF-8 encoding for reading
            data = json.load(f)
        
        episodes = []
        # Iterate through seasons and episodes to flatten the structure
        for season in data.get("seasons", []):
            season_num = season.get("season_number")
            if season_num is None:
                logging.warning(f"Skipping season with missing 'season_number' in {json_path}. Season data: {season}")
                continue
            for episode in season.get("episodes", []):
                episode["season_number"] = season_num # Add season_number to each episode for easier access
                episodes.append(episode)
        
        logging.info(f"Successfully loaded {len(episodes)} episodes from {json_path}")
        return episodes
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {json_path}: {e}")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading JSON from {json_path}: {e}")
        return []

def create_nfo_file(series_name: str, episode: dict, output_path: Path):
    """
    Creates an NFO (National File Organization) file for a given episode.
    The NFO file contains metadata like title, season, and episode number,
    which can be used by media center software like Kodi.

    Args:
        series_name (str): The name of the TV series.
        episode (dict): A dictionary containing episode metadata.
        output_path (Path): The intended path for the media file, used to derive NFO path.
    """
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
</episodedetails>
"""
    # Write the NFO content to the file, ensuring UTF-8 encoding
    try:
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(nfo_content)
        logging.info(f"Created NFO: {nfo_path}")
    except Exception as e:
        logging.error(f"Error creating NFO file {nfo_path}: {e}")


def organize_files(series_name: str, episodes: list, tv_library_path: str, move_files: bool):
    """
    Organizes media files by creating NFOs and optionally moving files
    to a standardized library structure.

    Args:
        series_name (str): The name of the TV series.
        episodes (list): A list of episode dictionaries from the processed JSON.
        tv_library_path (str): The base path for the TV series library.
        move_files (bool): If True, files will be moved; otherwise, only NFOs are created.
    """
    logging.info(f"Starting file organization for '{series_name}'. Move files: {move_files}")

    for episode in episodes:
        season = episode.get("season_number")
        episode_num = episode.get("episode_number")

        # Skip if essential episode numbers are missing
        if season is None or episode_num is None:
            logging.warning(f"Skipping episode due to missing season or episode number: {episode}")
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
        
        # Construct the new filename (e.g., "The A-Team - S01E01 - Pilot.ts")
        # Assuming original file extension needs to be preserved or is always .ts
        # For now, we'll assume .ts as per your example, but this should be dynamic
        # based on the best file's extension if we were to implement best file selection.
        # For this version, we'll use a placeholder extension or derive from source path.
        
        # Placeholder for actual file extension. In a real scenario, this would come from the 'file' info.
        # For now, we'll use '.ts' as a default or derive from the first 'best' file if available.
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
        
        # Create NFO file regardless of 'move_files' flag
        create_nfo_file(series_name, episode, output_path)
        
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
                    
                    # Move associated .xml and .edl files (assuming they are in the same directory as src_path)
                    for ext in [".xml", ".edl"]:
                        src_ext_path = Path(best_file_to_move).with_suffix(ext)
                        dst_ext_path = output_path.with_suffix(ext)
                        if src_ext_path.exists():
                            shutil.move(src_ext_path, dst_ext_path)
                            logging.info(f"Moved {ext}: '{src_ext_path}' -> '{dst_ext_path}'")
                except Exception as e:
                    logging.error(f"Error moving file '{best_file_to_move}' to '{output_path}': {e}")
            else:
                logging.warning(f"No valid source file found to move for S{season:02d}E{episode_num:02d} - '{title}'.")
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
                    for ext in [".xml", ".edl"]:
                        src_ext_path = Path(best_file_to_move).with_suffix(ext)
                        dst_ext_path = output_path.with_suffix(ext)
                        if src_ext_path.exists():
                            logging.info(f"DRY RUN: Would move {ext}: '{src_ext_path}' -> '{dst_ext_path}'")
                else:
                    logging.info(f"DRY RUN: No valid source file found to move for S{season:02d}E{episode_num:02d} - '{title}'.")
            else:
                logging.info(f"DRY RUN: No 'files' information available for S{season:02d}E{episode_num:02d} - '{title}'. No files to move.")


def main():
    """Main function to parse arguments, load data, and organize files."""
    parser = argparse.ArgumentParser(description="Organize media files for a TV series.")
    parser.add_argument("series_name", help="Name of the series (e.g., 'The A-Team').")
    parser.add_argument("--move", action="store_true", help="If set, files will be moved; otherwise, only NFOs are created (dry run).")
    args = parser.parse_args()
    
    # Setup logging for the specific series
    series_slug = setup_logging(args.series_name)
    logging.info(f"=== File Organizer v0.9.6 Started for '{args.series_name}' ===")
    
    # Load paths from config/paths.txt
    paths = load_paths()
    tv_library_path = paths.get("TV_LIBRARY_PATH")
    json_folder = paths.get("JSON_FOLDER")
    
    # Check if essential paths are loaded
    if not tv_library_path:
        logging.error("TV_LIBRARY_PATH not found in paths.txt. Cannot proceed.")
        return
    if not json_folder:
        logging.error("JSON_FOLDER not found in paths.txt. Cannot proceed.")
        return

    logging.info(f"Using TV_LIBRARY_PATH = '{tv_library_path}'")
    logging.info(f"Using JSON_FOLDER = '{json_folder}'")
    
    # Load the processed JSON data for the series
    episodes = load_processed_json(args.series_name, json_folder)
    if not episodes:
        logging.warning("No episodes loaded from processed JSON. Exiting.")
        return
    
    # Perform the file organization
    organize_files(args.series_name, episodes, tv_library_path, args.move)
    logging.info("File organization complete.")

if __name__ == "__main__":
    main()