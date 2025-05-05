import os
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import sqlite3

# kodi_db_exporter.py Version 1.3
# this version successfully cleans the temp folder called Database, and then writes the new kodi database files 
# It should be noted that if a command prompt is open and has been used in the tempp/Database folder, the script will not complete, but will throw an error.

# ---------------------- CONFIG ----------------------
def load_paths(paths_file="paths.txt"):
    paths = {}
    with open(paths_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.strip().split("=", 1)
            paths[key.strip()] = value.strip()
    return paths

# ---------------------- LOGGING ----------------------
def write_log(log_path, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(log_path, exist_ok=True)
    with open(os.path.join(log_path, "kodi_db_exporter.log"), "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")

# ---------------------- ADB UTIL ----------------------
def get_adb_path(paths):
    return paths.get("ADB_PATH") or shutil.which("adb")

def connect_to_kodi(adb_path, ip):
    result = subprocess.run([adb_path, "connect", ip], capture_output=True, text=True)
    return result.stdout.strip() + result.stderr.strip()

def pull_kodi_dbs(adb_path, temp_folder, log_path):
    db_remote_path = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/Database"
    local_db_path = os.path.join(temp_folder, "Database")

    # Clean old Database folder if it exists
    if os.path.exists(local_db_path):
        write_log(log_path, f"Removing old Database folder at {local_db_path}...")
        shutil.rmtree(local_db_path)

    os.makedirs(local_db_path, exist_ok=True)
    write_log(log_path, f"Scanning remote DB folder {db_remote_path} for .db files...")
    result = subprocess.run([adb_path, "shell", "ls", db_remote_path], capture_output=True, text=True)
    db_files = [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".db")]

    for db_file in db_files:
        remote = f"{db_remote_path}/{db_file}"
        local = os.path.join(local_db_path, db_file)
        write_log(log_path, f"Pulling {db_file}...")
        subprocess.run([adb_path, "pull", remote, local])
        write_log(log_path, f"Pulled {db_file} to {local}")

# ---------------------- MAIN ----------------------
def main():
    paths = load_paths("paths.txt")
    log_path = paths.get("LOG_PATH", ".")
    write_log(log_path, "Starting kodi_db_exporter.py Version 1.3")

    adb_path = get_adb_path(paths)
    if not adb_path:
        write_log(log_path, "ERROR: adb not found. Please set ADB_PATH or add adb to system PATH.")
        return

    kodi_ip = paths.get("KODI_IP")
    if not kodi_ip:
        write_log(log_path, "ERROR: KODI_IP not found in paths.txt")
        return

    temp_folder = paths.get("TEMP_FOLDER", "./tmp")
    json_folder = paths.get("JSON_FOLDER", "./.JSON")
    os.makedirs(json_folder, exist_ok=True)

    write_log(log_path, f"Connecting to Kodi at {kodi_ip}...")
    connect_result = connect_to_kodi(adb_path, kodi_ip)
    write_log(log_path, f"ADB Connect Result: {connect_result}")

    pull_kodi_dbs(adb_path, temp_folder, log_path)

    write_log(log_path, "Change 1 complete: DBs pulled from Kodi.")

if __name__ == "__main__":
    main()
