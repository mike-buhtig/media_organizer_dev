# providers/tmdb_provider.py V 1.0.1
# Fetches metadata from TMDB and writes standardized output to a temp file
# Change 1: Added clean_title function to strip quotes and backslashes from episode titles
# Change 2: Applied title cleaning to ep.get("name") to fix malformed titles (e.g., "\"By Air, Land and Sea\"")

import os
import json
import requests
import re
from configparser import ConfigParser

def clean_title(title):
    if not title:
        return ""
    cleaned = re.sub(r'^"|"$|\\', '', title.strip())
    if cleaned != title:
        print(f"[TMDB] Cleaned title: '{title}' -> '{cleaned}'")
    return cleaned

def get_metadata(title, config: ConfigParser):
    base_temp = config["general"]["TEMP_FOLDER"]
    api_key = config["tmdb"]["TMDB_API_KEY"]
    os.makedirs(base_temp, exist_ok=True)

    try:
        search_url = f"https://api.themoviedb.org/3/search/tv?query={requests.utils.quote(title)}&api_key={api_key}"
        search_resp = requests.get(search_url)
        if search_resp.status_code != 200 or not search_resp.json().get("results"):
            print("[TMDB] No matching show found.")
            return

        show = search_resp.json()["results"][0]
        show_id = show["id"]

        output = {
            "title": show.get("name"),
            "id": show_id,
            "type": "tv",
            "overview": show.get("overview", ""),
            "first_air_date": show.get("first_air_date"),
            "seasons": {}
        }

        season_list_url = f"https://api.themoviedb.org/3/tv/{show_id}?api_key={api_key}"
        show_detail = requests.get(season_list_url).json()
        for season in show_detail.get("seasons", []):
            snum = season.get("season_number")
            season_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{snum}?api_key={api_key}"
            season_resp = requests.get(season_url)
            episodes = season_resp.json().get("episodes", []) if season_resp.status_code == 200 else []

            for ep in episodes:
                ep_title = clean_title(ep.get("name"))
                ep_data = {
                    "episode_number": ep.get("episode_number"),
                    "air_date": ep.get("air_date"),
                    "titles": {"tmdb": ep_title},
                    "overviews": {"tmdb": ep.get("overview", "")},
                    "ids": {"tmdb": ep.get("id")}
                }
                output["seasons"].setdefault(snum, []).append(ep_data)

        output_path = os.path.join(base_temp, "provider_tmdb.json")
        # Delete existing temp file to prevent stale data
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"[tmdbf] Deleted existing temp file: {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[TMDB] Metadata written to {output_path}")

    except Exception as e:
        print(f"[TMDB ERROR] {e}")