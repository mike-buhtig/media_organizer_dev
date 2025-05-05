# match_unmatched_v1.0.1.py
# Version 1.0.1
# Manually moves unmatched episodes in series_name_Processed.json to specified season/episode
# Includes related files (.xml, .edl, .txt, .timing) and optionally renames them
# Usage: python match_unmatched.py "Series Name" "subtitle" season episode [--rename]

import json
import sys
import os
import argparse
import re
import shutil

def load_processed(series_name):
    json_folder = "."
    with open("paths.txt", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("JSON_FOLDER="):
                json_folder = line.split("=", 1)[1].strip().strip('"')
                break
    processed_path = os.path.join(json_folder, f"{series_name.replace(' ', '_')}_Processed.json")
    with open(processed_path, "r", encoding="utf-8") as f:
        return json.load(f), processed_path

def save_processed(data, processed_path):
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_related_files(ts_path):
    base = os.path.splitext(ts_path)[0]
    extensions = [".xml", ".edl", ".txt", ".timing"]
    related = []
    for ext in extensions:
        file_path = base + ext
        if os.path.exists(file_path):
            related.append({
                "path": file_path.replace("\\", "/"),
                "size": os.path.getsize(file_path),
                "extension": ext
            })
    return related

def rename_files(series_name, season, episode, title, originals, root_folder, do_rename):
    if not do_rename:
        return originals

    new_originals = []
    for entry in originals:
        old_ts_path = entry["path"]
        base_name = f"{series_name} - S{season:02d}E{episode:02d} - {title.replace(':', ' -')}"
        new_ts_path = os.path.join(root_folder, f"{base_name}.ts").replace("\\", "/")
        
        # Rename .ts file
        if os.path.exists(old_ts_path) and do_rename:
            shutil.move(old_ts_path, new_ts_path)
            print(f"Renamed: {old_ts_path} -> {new_ts_path}")
        
        # Update entry
        new_entry = entry.copy()
        new_entry["path"] = new_ts_path
        new_originals.append(new_entry)

        # Rename related files
        for related in get_related_files(old_ts_path):
            old_related_path = related["path"]
            new_related_path = os.path.join(root_folder, f"{base_name}{related['extension']}").replace("\\", "/")
            if os.path.exists(old_related_path) and do_rename:
                shutil.move(old_related_path, new_related_path)
                print(f"Renamed: {old_related_path} -> {new_related_path}")
            new_entry = related.copy()
            new_entry["path"] = new_related_path
            new_originals.append(new_entry)
    
    return new_originals

def match_episode(series_name, subtitle, season, episode, do_rename=False):
    data, processed_path = load_processed(series_name)
    unmatched = data.get("unmatched", [])
    matched = data.get("matches", {})

    # Find root folder from paths.txt
    root_folder = ""
    with open("paths.txt", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"series_path_") and f"series_name_]={series_name}" in line:
                root_folder = line.split("=", 1)[1].strip().strip('"')
                break
    if not root_folder:
        print(f"Root folder for {series_name} not found in paths.txt")
        return

    # Find the unmatched entry
    for i, entry in enumerate(unmatched):
        if entry["episode_meta"]["subtitle"].lower() == subtitle.lower():
            # Load series metadata to get episode details
            metadata_path = os.path.join(os.path.dirname(processed_path), f"{series_name}.json")
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            # Find the episode in series metadata
            episode_meta = None
            for s in meta.get("seasons", []):
                if s["season_number"] == season:
                    for ep in s.get("episodes", []):
                        if ep["episode_number"] == episode:
                            episode_meta = {
                                "season": season,
                                "episode": episode,
                                "title": ep.get("title", ""),
                                "titles": [ep.get("title", "")] + list(ep.get("titles", {}).values()),
                                "overview": ep.get("overview", ""),
                                "overviews": [ep.get("overview", "")] + list(ep.get("overviews", {}).values()),
                                "air_date": ep.get("air_date", "")
                            }
                            break
                    if episode_meta:
                        break
            
            if not episode_meta:
                print(f"Episode S{season:02d}E{episode:02d} not found in {series_name}.json")
                return

            # Update originals with related files and optionally rename
            originals = entry["originals"]
            originals = rename_files(series_name, season, episode, episode_meta["title"], originals, root_folder, do_rename)

            # Move to matches
            group_id = f"{series_name}-S{season:02d}E{episode:02d}"
            matched[group_id] = {
                "episode_meta": episode_meta,
                "originals": originals
            }
            unmatched.pop(i)
            print(f"Moved '{subtitle}' to {group_id}")
            save_processed(data, processed_path)
            return
    
    print(f"Subtitle '{subtitle}' not found in unmatched section")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Move unmatched episodes to specified season/episode")
    parser.add_argument("series_name", help="Series name (e.g., Ax Men)")
    parser.add_argument("subtitle", help="Subtitle of the unmatched episode")
    parser.add_argument("season", type=int, help="Season number")
    parser.add_argument("episode", type=int, help="Episode number")
    parser.add_argument("--rename", action="store_true", help="Rename .ts and related files")
    args = parser.parse_args()
    
    match_episode(args.series_name, args.subtitle, args.season, args.episode, args.rename)