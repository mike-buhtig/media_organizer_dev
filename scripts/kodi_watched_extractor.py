import sqlite3
import subprocess
import json
import os
from configparser import ConfigParser
import argparse
import logging

# Configure logging
logging.basicConfig(filename='kodi_watched_extractor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

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

def pull_kodi_database(kodi_ip, remote_path, local_path):
    """Pulls the Kodi database file from the Android device."""
    logging.info(f"Pulling Kodi database from {kodi_ip}:{remote_path} to {local_path}")
    try:
        result = subprocess.run(['adb', 'pull', f'{kodi_ip}:{remote_path}', local_path], capture_output=True, text=True, check=True)
        logging.info(f"Database pulled successfully: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error pulling database: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        logging.error("Error: ADB command not found.")
        return False

def query_kodi_watched_status(db_path, kodi_network_path):
    """Queries the Kodi database for watched status of files in the given network path."""
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
        logging.error(f"Database error: {e}")
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
    except json.JSONDecodeError:
        logging.error(f"Error: Could not decode JSON from {processed_file_path}.")
        return {}

def map_watched_status_to_local_paths(kodi_watched_data, processed_data, local_series_path, kodi_network_base_path):
    """Maps watched status from Kodi paths to local file paths."""
    local_watched_status = {}
    for local_file_path in processed_data:
        relative_path = os.path.relpath(local_file_path, local_series_path).replace('\\', '/')
        potential_kodi_path = os.path.join(kodi_network_base_path, relative_path).replace('\\', '/')

        for kodi_path, watched_info in kodi_watched_data.items():
            if potential_kodi_path.lower() == kodi_path.lower():
                local_watched_status[local_file_path] = watched_info
                break
    return local_watched_status

def save_kodi_watched_data(output_file_path, watched_data):
    """Saves the Kodi watched data to a JSON file."""
    with open(output_file_path, 'w') as f:
        json.dump(watched_data, f, indent=4)
    logging.info(f"Kodi watched data saved to: {output_file_path}")

def main():
    parser = argparse.ArgumentParser(description='Extract watched status from Kodi for a specific TV series.')
    parser.add_argument('series_name', help='The name of the TV series to process (as defined in paths.txt).')
    args = parser.parse_args()
    series_name = args.series_name

    config = read_config()
    kodi_ip = config.get('kodi', 'kodi_ip')
    network_config = config['network_config']
    kodi_share_name = network_config.get('kodi_shares', '').split(',')[0].strip() # Still using the first Kodi share for now
    kodi_db_remote_path = '/storage/emulated/0/Android/data/org.xbmc.kodi/files/.kodi/userdata/Database/MyVideos131.db' # Hardcoded for now
    local_db_path = 'data/kodi_db.db' # Temporary local storage

    # Find the series path based on the provided series_name
    series_path = None
    series_slug = None
    series_config = config['series']
    for i in range(1, len(series_config) // 2 + 1):
        name_key = f'series_name_{i}'
        path_key = f'series_path_{i}'
        if name_key in series_config and series_config[name_key] == series_name:
            series_path = series_config[path_key]
            series_slug = series_name.lower().replace(' ', '_').replace('.', '_').replace('-', '_')
            break

    if not series_path or not series_slug:
        logging.error(f"Series '{series_name}' not found in paths.txt.")
        return

    logging.info(f"Processing series: {series_name} (Slug: {series_slug})")

    if not establish_adb_connection(kodi_ip):
        return

    if not pull_kodi_database(kodi_ip, kodi_db_remote_path, local_db_path):
        return

    # Construct the Kodi network base path
    kodi_network_base_path = f'smb://{kodi_ip}/{kodi_share_name}/{os.path.basename(local_series_path)}/'.replace('\\', '/')
    logging.info(f"Kodi network base path: {kodi_network_base_path}")

    kodi_watched_data = query_kodi_watched_status(local_db_path, kodi_network_base_path)
    processed_data = load_processed_data(f'data/{series_slug}_processed.json')
    if processed_data:
        local_watched_status = map_watched_status_to_local_paths(kodi_watched_data, processed_data, local_series_path, kodi_network_base_path)
        save_kodi_watched_data(f'data/{series_slug}_kodi_watched.json', local_watched_status)
    else:
        logging.warning(f"No processed data found for {series_name}.")

    # Clean up the pulled database
    if os.path.exists(local_db_path):
        os.remove(local_db_path)
        logging.info("Temporary Kodi database removed.")

if __name__ == "__main__":
    main()