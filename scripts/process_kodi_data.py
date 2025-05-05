import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# process_kodi_data.py Version 1.8.4
# Changelog:
# Version 1.8.4:
# - Added fallback to IMDb ID when TMDb ID is not present
# - Added "imdb_id" field to the JSON output

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
    with open(os.path.join(log_path, "process_kodi_data.log"), "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")

# ---------------------- PROCESSING ----------------------
def extract_data_from_db(db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    entries = []
    try:
        cursor.execute("PRAGMA table_info(episode)")
        ep_columns = [col[1] for col in cursor.fetchall()]
        has_ep_playcount = "playCount" in ep_columns

        episode_query = f"""
        SELECT e.idEpisode, e.c00 AS title, e.c12 AS season, e.c13 AS episode,
               p.strPath || f.strFilename AS full_path,
               {'e.playCount' if has_ep_playcount else '0'} AS playcount
        FROM episode e
        JOIN files f ON e.idFile = f.idFile
        JOIN path p ON f.idPath = p.idPath
        WHERE f.strFilename IS NOT NULL
        """

        cursor.execute(episode_query)
        for eid, title, season, episode, full_path, playcount in cursor.fetchall():
            parts = Path(full_path).parts
            show_title = parts[-2] if len(parts) > 1 else "Unknown"

            if show_title.lower() in ("tv-series", "tv series"):
                show_title = Path(full_path).stem

            filename = Path(full_path).name
            entries.append({
                "show_title": show_title,
                "episode_title": title,
                "season": str(season) if season is not None else "",
                "episode": str(episode) if episode is not None else "",
                "filename": filename,
                "full_path": full_path,
                "watched": bool(playcount)
            })

        cursor.execute("PRAGMA table_info(movie_view)")
        movie_columns = [col[1] for col in cursor.fetchall()]
        has_plot = "plot" in movie_columns
        has_c01 = "c01" in movie_columns
        has_movie_playcount = "playCount" in movie_columns

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uniqueid'")
        has_uniqueid_table = cursor.fetchone() is not None

        select_parts = [
            "m.c00 AS title",
            "p.strPath || f.strFilename AS full_path",
            "m.idMovie",
            "m.idFile"
        ]
        if has_plot:
            select_parts.append("m.plot AS plot")
        elif has_c01:
            select_parts.append("m.c01 AS plot")
        else:
            select_parts.append("'' AS plot")

        select_parts.append("m.playCount" if has_movie_playcount else "0 AS playCount")

        movie_query = f"""
        SELECT {', '.join(select_parts)}
        FROM movie_view m
        JOIN files f ON m.idFile = f.idFile
        JOIN path p ON f.idPath = p.idPath
        WHERE f.strFilename IS NOT NULL
        """

        cursor.execute(movie_query)
        for title, full_path, idMovie, idFile, plot, playcount in cursor.fetchall():
            filename = Path(full_path).name

            tmdb_id = "N/A"
            imdb_id = "N/A"
            if has_uniqueid_table:
                try:
                    cursor.execute("SELECT value, type FROM uniqueid WHERE media_id = ? AND media_type = 'movie'", (idMovie,))
                    ids = cursor.fetchall()
                    for value, id_type in ids:
                        if id_type == "tmdb":
                            tmdb_id = value
                        elif id_type == "imdb":
                            imdb_id = value
                except Exception:
                    pass

            entries.append({
                "show_title": title,
                "episode_title": title,
                "season": "",
                "episode": "",
                "filename": filename,
                "full_path": full_path,
                "watched": bool(playcount),
                "synopsis": plot if plot else "",
                "tmdb_id": tmdb_id,
                "imdb_id": imdb_id
            })

    except Exception as e:
        print(f"Error processing {db_file}: {e}")
    finally:
        conn.close()

    return entries

# ---------------------- MAIN ----------------------
def main():
    paths = load_paths("paths.txt")
    log_path = paths.get("LOG_PATH", ".")
    write_log(log_path, "Starting process_kodi_data.py Version 1.8.4")

    db_dir = Path(paths.get("TEMP_FOLDER", "./tmp")) / "Database"
    json_output = Path(paths.get("JSON_FOLDER", "./.JSON")) / "kodi_export.json"
    os.makedirs(json_output.parent, exist_ok=True)

    db_files = sorted(db_dir.glob("MyVideos*.db"))
    if not db_files:
        write_log(log_path, f"No Kodi database found in {db_dir}")
        return

    all_entries = []
    for db_file in db_files:
        write_log(log_path, f"Processing DB: {db_file}")
        all_entries.extend(extract_data_from_db(db_file))

    previous_entries = []
    if json_output.exists():
        with open(json_output, "r", encoding="utf-8") as f:
            try:
                previous_entries = json.load(f)
            except json.JSONDecodeError:
                write_log(log_path, "Warning: Could not decode existing JSON file, assuming empty.")

    if all_entries != previous_entries:
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(all_entries, f, indent=2)
        write_log(log_path, f"Extracted {len(all_entries)} entries to {json_output}")
    else:
        write_log(log_path, f"No changes detected. Existing JSON already up to date with {len(all_entries)} entries.")

if __name__ == "__main__":
    main()
