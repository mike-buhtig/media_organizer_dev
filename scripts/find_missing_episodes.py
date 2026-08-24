# find_missing_episodes.py

import argparse
import configparser
import json
import os
import re
from pathlib import Path
import io

try:
    from series_completeness import (
        atomic_write_json,
        compatibility_projection,
        evaluate_series_completeness,
    )
except ImportError:  # Support import as scripts.find_missing_episodes in repository tests.
    from scripts.series_completeness import (
        atomic_write_json,
        compatibility_projection,
        evaluate_series_completeness,
    )

# --- Configuration Loading ---
def load_config(config_path="config/paths.txt"):
    """Loads the configuration from paths.txt."""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

# --- Argument Parsing ---
def parse_args():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Identifies missing episodes for a given series.")
    parser.add_argument("series_name", help="The name of the series (as defined in paths.txt).")
    return parser.parse_args()

# --- Data Loading Functions ---
def load_merged_metadata(config, series_name):
    """Loads the merged metadata JSON file from the series' data subdirectory."""
    json_folder = config["general"]["JSON_FOLDER"].strip()
    series_folder_name = series_name.replace(" ", "_").replace("-", "_").lower().strip()
    filename = series_name.replace(" ", "_").strip() + ".json"
    filepath_str = os.path.join(json_folder, series_folder_name, filename)
    filepath = Path(filepath_str)

    print(f"Debugging: json_folder: '{json_folder}'")
    print(f"Debugging: series_folder_name: '{series_folder_name}'")
    print(f"Debugging: filename: '{filename}'")
    print(f"Debugging: Attempting to open metadata file at (string): '{filepath_str}'")
    print(f"Debugging: Attempting to open metadata file at (Path): '{filepath}'")

    try:
        with open(filepath, "r", encoding="us-ascii") as f:  # Changed encoding to "us-ascii"
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Merged metadata file not found at {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while opening/reading {filepath}: {e}")
        return None


def load_kodi_watched_data(config):
    """Loads the kodi_watched.json file."""
    json_folder = config["general"]["JSON_FOLDER"]
    filepath = Path(json_folder) / "kodi_watched.json"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: kodi_watched.json not found at {filepath}. Skipping Kodi watched data.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}")
        return {}

# --- Identifying Existing Episodes ---
def get_existing_from_kodi(watched_data, series_name):
    """Extracts existing episode identifiers from kodi_watched.json."""
    existing_episodes = set()
    if series_name in watched_data:
        for item in watched_data[series_name]["episodes"]:
            season = item.get("season")
            episode = item.get("episode")
            if season is not None and episode is not None:
                existing_episodes.add(f"S{season:02d}E{episode:02d}")
    return existing_episodes

def get_existing_from_nfo(config, series_name):
    """Extracts existing episode identifiers from .nfo files in the output folder."""
    tv_library_path = config["library_paths"]["TV_LIBRARY_PATH"]
    output_folder = Path(tv_library_path) / series_name
    existing_episodes = set()

    if output_folder.is_dir():
        for nfo_file in output_folder.rglob("*.nfo"):
            try:
                with open(nfo_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    season_match = re.search(r"<season>(\d+)</season>", content)
                    episode_match = re.search(r"<episode>(\d+)</episode>", content)
                    if season_match and episode_match:
                        season = int(season_match.group(1))
                        episode = int(episode_match.group(1))
                        existing_episodes.add(f"S{season:02d}E{episode:02d}")
            except Exception as e:
                print(f"Warning: Error reading or parsing NFO file {nfo_file}: {e}")
    return existing_episodes

# --- Identifying All Expected Episodes with Metadata ---
def get_expected_episodes_with_metadata(metadata):
    """Extracts all expected episodes with their metadata."""
    expected_episodes = {}
    if metadata and "seasons" in metadata:
        for season in metadata["seasons"]:
            season_num = season.get("season_number")
            if "episodes" in season and season_num is not None:
                for episode in season["episodes"]:
                    episode_num = episode.get("episode_number")
                    title = episode.get("title", "")
                    overview = episode.get("overview", "")
                    air_date = episode.get("air_date", "")
                    if episode_num is not None:
                        identifier = f"S{season_num:02d}E{episode_num:02d}"
                        expected_episodes[identifier] = {
                            "season_number": season_num,
                            "episode_number": episode_num,
                            "title": title,
                            "overview": overview,
                            "air_date": air_date
                        }
    return expected_episodes

# --- Determining Missing Episodes ---
def find_missing_episodes(expected, existing):
    """Compares expected and existing episodes to find missing ones."""
    missing_episodes = []
    for identifier, metadata in expected.items():
        if identifier not in existing:
            missing_episodes.append(metadata)
    return missing_episodes

# --- Generating Output JSON ---
def write_missing_json(config, series_name, missing_episodes):
    """Writes the list of missing episodes to a JSON file in the series' data subdirectory."""
    json_folder = config["general"]["JSON_FOLDER"]
    series_folder_name = series_name.replace(" ", "_").lower()  # Create lowercase folder name
    output_filename = series_name.replace(" ", "_") + "_missing.json"
    output_dir = Path(json_folder) / series_folder_name
    output_path = output_dir / output_filename

    # Create the series subdirectory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    output_data = {
        "series_name": series_name,
        "missing_episodes": missing_episodes
    }
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        print(f"Missing episodes written to {output_path}")
    except IOError as e:
        print(f"Error writing to {output_path}: {e}")

# --- Main Function ---
def main():
    """Compatibility entry point backed by the authoritative completeness engine."""
    args = parse_args()
    print("DEPRECATION: find_missing_episodes.py now emits a compatibility projection; "
          "use the authoritative completeness.json for automation.")
    report = evaluate_series_completeness(args.series_name)
    projection = compatibility_projection(report)
    output_path = Path(report["compatibility_output_path"])
    atomic_write_json(output_path, projection)
    print(f"Compatibility missing-episode projection written to {output_path}")

if __name__ == "__main__":
    main()
