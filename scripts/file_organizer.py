# file_organizer.py
# Version 0.9.5
# Change Log:
# - Restored version with NFO writing only (no move/delete)
# - Uses paths.txt
# - Filters broken files
# - Groups by subtitle
# - Picks best file
# - Writes .nfo files to TV_LIBRARY_PATH
# - Logs KEEP/RENAME/NFO/DELETE candidates in file_organizer_actions_<series>.log
# - Cleans subtitle for use in filename
# - Fixes issue where titles list was not parsed correctly
# - 2025-04-18: Logging format restored with full traceability for each action
# - 2025-04-19: Normalize log file output to use / without a mix, which is unix style file address
# - 2025-04-22: Fixed AttributeError in group_and_write to handle new JSON structure with matches and unmatched sections
# - 2025-04-22: Updated write_nfo to place unmatched episodes in 'Unmatched Episodes' folder
# - 2025-04-30 Update .json format
# - 2025-04-30 Update to use a flag to make the script move the files into place.

import os
import json
import argparse
import logging
from datetime import datetime
import shutil

def setup_logging(series_name):
    series_slug = series_name.lower().replace(" ", "_")
    log_dir = os.path.join("logs", series_slug)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "file_organizer.log")
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return series_slug

def load_paths():
    paths = {}
    try:
        with open("paths.txt", "r") as f:
            current_section = None
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                elif "=" in line and current_section == "library_paths":
                    key, value = line.split("=", 1)
                    paths[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.error("paths.txt not found")
        raise
    paths["JSON_FOLDER"] = paths.get("JSON_FOLDER", "data")
    return paths

def load_processed_json(series_name, json_folder):
    series_slug = series_name.lower().replace(" ", "_")
    json_path = os.path.join(json_folder, series_slug, f"{series_name}_Processed.json")
    logging.info(f"Loading JSON from {json_path}")
    
    if not os.path.exists(json_path):
        logging.error(f"JSON file not found: {json_path}")
        return []
    
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        episodes = []
        for season in data.get("seasons", []):
            for episode in season.get("episodes", []):
                episode["season_number"] = season["season_number"]
                episodes.append(episode)
        logging.info(f"Loaded {len(episodes)} episodes from Processed.json")
        return episodes
    except Exception as e:
        logging.error(f"Error loading JSON: {str(e)}")
        return []

def create_nfo_file(series_name, episode, output_path):
    nfo_path = os.path.splitext(output_path)[0] + ".nfo"
    season = episode["season_number"]
    episode_num = episode["episode_number"]
    title = episode["titles"][0] if episode["titles"] else "Unknown"
    
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<episodedetails>
    <title>{title}</title>
    <season>{season}</season>
    <episode>{episode_num}</episode>
</episodedetails>
"""
    os.makedirs(os.path.dirname(nfo_path), exist_ok=True)
    with open(nfo_path, "w") as f:
        f.write(nfo_content)
    logging.info(f"Created NFO: {nfo_path}")

def organize_files(series_name, episodes, tv_library_path, move_files=False):
    for episode in episodes:
        season = episode["season_number"]
        episode_num = episode["episode_number"]
        title = episode["titles"][0] if episode["titles"] else "Unknown"
        season_str = f"Season {season:02d}"
        filename = f"{series_name} - S{season:02d}E{episode_num:02d} - {title}.ts"
        output_dir = os.path.join(tv_library_path, series_name, season_str)
        output_path = os.path.join(output_dir, filename)
        
        logging.info(f"Processing episode S{season:02d}E{episode_num:02d}: {title}")
        create_nfo_file(series_name, episode, output_path)
        
        if move_files:
            for file in episode.get("files", []):
                if not file["broken"]:
                    src_path = file["path"]
                    if os.path.exists(src_path):
                        os.makedirs(output_dir, exist_ok=True)
                        shutil.move(src_path, output_path)
                        logging.info(f"Moved file: {src_path} -> {output_path}")
                        
                        # Move associated .xml and .edl files
                        for ext in [".xml", ".edl"]:
                            src_ext = os.path.splitext(src_path)[0] + ext
                            dst_ext = os.path.splitext(output_path)[0] + ext
                            if os.path.exists(src_ext):
                                shutil.move(src_ext, dst_ext)
                                logging.info(f"Moved {ext}: {src_ext} -> {dst_ext}")
                    else:
                        logging.warning(f"Source file not found: {src_path}")

def main():
    parser = argparse.ArgumentParser(description="Organize media files for a series")
    parser.add_argument("series_name", help="Name of the series (e.g., The A-Team)")
    parser.add_argument("--move", action="store_true", help="Move files instead of just creating NFOs")
    args = parser.parse_args()
    
    series_slug = setup_logging(args.series_name)
    logging.info(f"=== File Organizer v1.0.0 Started for '{args.series_name}' ===")
    
    paths = load_paths()
    tv_library_path = paths.get("TV_LIBRARY_PATH", "E:/media_library/tv_series")
    json_folder = paths.get("JSON_FOLDER", "data")
    logging.info(f"Using TV_LIBRARY_PATH = {tv_library_path}")
    logging.info(f"Using JSON_FOLDER = {json_folder}")
    
    episodes = load_processed_json(args.series_name, json_folder)
    if not episodes:
        logging.warning("No episodes loaded. Exiting.")
        return
    
    organize_files(args.series_name, episodes, tv_library_path, args.move)
    logging.info("Processing complete.")

if __name__ == "__main__":
    main()