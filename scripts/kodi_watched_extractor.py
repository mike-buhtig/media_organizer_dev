#!/usr/bin/env python3

"""
kodi_watched_extractor.py
Version: 0.1.0
Date: 2025-05-26
Author: Your Name (or Placeholder)
Description:
  Extracts watched status for TV show episodes from the Kodi database(s).
  It connects to Kodi via ADB, pulls all MyVideos*.db files, queries them
  for watched status, and outputs a JSON file mapping episode identifiers
  to their watched status and metadata.

Changelog:
  v0.1.0 (2025-05-26):
    - Initial version with ADB connection, database pulling for all MyVideos*.db files,
      and basic structure for mapping watched status to episodes.
    - Implemented logging to the logs/<series_slug>/ directory.
    - Added versioning and basic comments.
"""

import sqlite3
import subprocess
import json
import os
from configparser import ConfigParser
import argparse
import logging
from datetime import datetime

# Script version
__version__ = "0.1.0"

def read_config():
    """Reads configuration from paths.txt."""
    config = ConfigParser()
    config.read('config/paths.txt')
    return config

def establish_adb_connection(kodi_ip):
    """Attempts to establish an ADB connection to the Kodi device."""
    logging.info(f"Attempting ADB connection to: {kodi_ip}")
    try:
        result = subprocess.run(['adb', 'connect', kodi_ip], capture_output=True, text=True, check=True)
        logging.info(f"ADB Connection successful: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error connecting to ADB: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        logging.error("Error: ADB command not found. Ensure ADB is installed and in your system's PATH.")
        return False

def list_remote_kodi_databases(kodi_ip, remote_db_path):
    """Lists all MyVideos*.db files in the Kodi database directory."""
    logging.info(f"Listing Kodi databases in: {kodi_ip}:{remote_db_path}")
    try:
        result = subprocess.run(['adb', 'shell', f'ls {remote_db_path}/MyVideos*.db'], capture_output=True, text=True, check=True)
        databases = [db.replace('//', '/') for db in result.stdout.strip().split('\n') if db.endswith('.db')] # Added replace
        logging.info(f"Found Kodi databases: {databases}")
        return databases
    except subprocess.CalledProcessError as e:
        logging.error(f"Error listing remote databases: {e.stderr.strip()}")
        return []
    except FileNotFoundError:
        logging.error("Error: ADB command not found.")
        return []

def pull_kodi_database(kodi_ip, remote_path, local_db_dir):
    """Pulls a single Kodi database file from the Android device."""
    local_filename = os.path.basename(remote_path)
    local_path = os.path.join(local_db_dir, local_filename).replace('\\', '/')
    logging.info(f"Pulling Kodi database from {kodi_ip}:{remote_path} to {local_path}")
    try:
        adb_command = ['adb', 'pull', remote_path, local_path] # Removed kodi_ip: from remote_path
        logging.debug(f"Executing ADB command: {' '.join(adb_command)}")
        result = subprocess.run(adb_command, capture_output=True, text=True, check=True)
        logging.info(f"Database pulled successfully to: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip()
        logging.error(f"Error pulling database from {remote_path}: {error_output}")
        logging.error(f"ADB Error Output: {error_output}")
        return False
    except FileNotFoundError:
        logging.error("Error: ADB command not found.")
        return False

def query_kodi_watched_status(db_path, kodi_network_path):
    """Queries a single Kodi database for watched status of files in the given network path."""
    watched_files = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql_query = """
            SELECT
                p.strPath || f.strFilename AS KodiFilePath,
                f.playCount,
                f.lastPlayed
            FROM files f
            JOIN path p ON f.idPath = p.idPath
            WHERE p.strPath LIKE ?
        """
        cursor.execute(sql_query, (kodi_network_path + '%',))
        results = cursor.fetchall()
        for row in results:
            kodi_file_path = row[0]
            play_count = row[1]
            last_played = row[2]
            watched = play_count > 0
            watched_files[kodi_file_path] = {"watched": watched, "last_played": last_played}
    except sqlite3.Error as e:
        logging.error(f"Database error in {db_path}: {e}")
    finally:
        if conn:
            conn.close()
    return watched_files

def load_processed_data(processed_file_path):
    """Loads the _processed.json file."""
    try:
        with open(processed_file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Error: {processed_file_path} not found.")
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"Error: Could not decode JSON from {processed_file_path}: {e}")
        return {}

def map_watched_status_to_episodes(all_watched_data, processed_data, series_path, kodi_network_base_path, config):
    """
    Maps watched status from Kodi data to episodes in the processed data.
    """
    episode_watched_status = {'series_name': processed_data.get('series_name', ''), 'seasons': []}

    for season_data in processed_data.get('seasons', []):
        season_number = season_data.get('season_number')
        episodes = []
        for episode in season_data.get('episodes', []):
            episode_number = episode.get('episode_number')
            watched = False
            last_played = None

            for file_info in episode.get('files', []):
                local_file_path = file_info.get('path', '').replace('\\', '/')
                local_filename_base, _ = os.path.splitext(os.path.basename(local_file_path).lower())

                for kodi_path, kodi_watched_info in all_watched_data.items():
                    kodi_filename_base, _ = os.path.splitext(os.path.basename(kodi_path).lower())

                    if local_filename_base == kodi_filename_base:
                        watched = kodi_watched_info['watched']
                        last_played = kodi_watched_info.get('last_played')
                        break  # Found a match, no need to check other Kodi paths
                if watched:
                    break # Found a watched file for this episode, move to the next

            episodes.append({
                'episode_number': episode_number,
                'watched': watched,
                'last_played': last_played
            })
        episode_watched_status['seasons'].append({'season_number': season_number, 'episodes': episodes})

    return episode_watched_status

def save_kodi_watched_data(output_file, data):
    """Saves the Kodi watched data to a JSON file."""
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4)
        logging.info(f"Kodi watched data saved to: {output_file}")
    except Exception as e:
        logging.error(f"Error saving Kodi watched data: {e}")

def save_kodi_watched_data(output_file_path, watched_data):
    """Saves the Kodi watched data to a JSON file."""
    with open(output_file_path, 'w') as f:
        json.dump(watched_data, f, indent=4)
    logging.info(f"Kodi watched data saved to: {output_file_path}")

def query_kodi_watched_status(db_path):
    """Queries a single Kodi database for watched files (playCount > 0) and their full paths."""
    watched_files = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql_query = """
            SELECT
                p.strPath || f.strFilename AS KodiFilePath,
                f.playCount,
                f.lastPlayed
            FROM files f
            JOIN path p ON f.idPath = p.idPath
            WHERE f.playCount > 0
        """
        cursor.execute(sql_query)
        results = cursor.fetchall()
        for row in results:
            kodi_file_path = row[0]
            play_count = row[1]
            last_played = row[2]
            watched_files[kodi_file_path] = {"watched": True, "last_played": last_played}
    except sqlite3.Error as e:
        logging.error(f"Database error in {db_path}: {e}")
    finally:
        if conn:
            conn.close()
    return watched_files

def main():
    parser = argparse.ArgumentParser(description='Extract watched status from Kodi for a specific TV series.')
    parser.add_argument('series_name', help='The name of the TV series to process (as defined in paths.txt).')
    args = parser.parse_args()
    series_name = args.series_name

    config = read_config()
    kodi_ip = config.get('kodi', 'kodi_ip')
    series_config = config['series']
    network_config = config['network_config']
    kodi_share_name = network_config.get('kodi_shares', '').split(',')[0].strip() # Using the first Kodi share for base path
    remote_db_path = '/storage/emulated/0/Android/data/org.xbmc.kodi/files/.kodi/userdata/Database/'
    local_db_dir = 'tmp/kodi_db'
    os.makedirs(local_db_dir, exist_ok=True)

    # Generate consistent series slug
    series_slug = series_name.lower().replace(' ', '_').replace('.', '_').replace('-', '_')

    # Configure logging to the correct directory
    log_dir = os.path.join('logs', series_slug)
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(filename=os.path.join(log_dir, 'kodi_watched_extractor.log'),
                        level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    logging.info(f"Processing series: {series_name} (Slug: {series_slug})")

    # Find the series path based on the provided series_name
    series_path = None
    for i in range(1, len(series_config) // 2 + 1):
        name_key = f'series_name_{i}'
        path_key = f'series_path_{i}'
        if name_key in series_config and series_config[name_key] == series_name:
            series_path = series_config[path_key]
            break

    if not series_path:
        logging.error(f"Series '{series_name}' not found in paths.txt.")
        return

    if not establish_adb_connection(kodi_ip):
        return

    remote_databases = list_remote_kodi_databases(kodi_ip, remote_db_path)
    all_watched_data = {}

    # Clean up existing databases in the local directory
    for filename in os.listdir(local_db_dir):
        if filename.startswith("MyVideos") and filename.endswith(".db"):
            os.remove(os.path.join(local_db_dir, filename))
            logging.info(f"Deleted old database file: {os.path.join(local_db_dir, filename)}")

    for remote_db in remote_databases:
        local_filename = os.path.basename(remote_db)
        local_db_file_path = os.path.join(local_db_dir, local_filename)
        if pull_kodi_database(kodi_ip, remote_db, local_db_dir): # Using remote_db directly
            logging.info(f"Querying watched status in {local_db_file_path} for watched files.")
            watched_data = query_kodi_watched_status(local_db_file_path) # Corrected call: only pass the database path
            all_watched_data.update(watched_data)

    processed_file = f'data/{series_slug}/{series_name.replace(" ", "_")}_Processed.json'
    processed_data = load_processed_data(processed_file)

    print(f"DEBUG: Type of processed_data: {type(processed_data)}")
    print(f"DEBUG: Content of processed_data (first 500 chars): {str(processed_data)[:500]}")

    if processed_data:
        episode_watched_status = map_watched_status_to_episodes(all_watched_data, processed_data, series_path, None, config) # Passing None for kodi_network_base_path as we are matching filenames
        output_watched_file = os.path.join('data', series_slug, f'{series_slug}_kodi_watched.json')
        os.makedirs(os.path.dirname(output_watched_file), exist_ok=True)
        save_kodi_watched_data(output_watched_file, episode_watched_status)
    else:
        logging.warning(f"No processed data found for {series_name}.")

    # Clean up pulled databases (we are leaving them for inspection as per your request)
    # for filename in os.listdir(local_db_dir):
    #    if filename.startswith("MyVideos") and filename.endswith(".db"):
    #        os.remove(os.path.join(local_db_dir, filename))
    #        logging.info(f"Deleted pulled database file: {os.path.join(local_db_dir, filename)}")

if __name__ == "__main__":
    main()
    
    # Clean up pulled databases (we are leaving them for inspection as per your request)
    # for filename in os.listdir(local_db_dir):
    #     if filename.startswith("MyVideos") and filename.endswith(".db"):
    #         os.remove(os.path.join(local_db_dir, filename))
    #         logging.info(f"Deleted pulled database file: {os.path.join(local_db_dir, filename)}")