# providers/tmdb.py v1.0.1
# Fetches metadata from TMDb using a function-based interface
# Based on tmdbf_provider.py v1.0.0
# Writes standardized metadata to tmp/tmdb.json
# Version 1.0.1: Updated to use list-based seasons structure

import os
import json
import requests
import re

def clean_title(title):
    """Clean title by removing quotes and backslashes."""
    if not title:
        return ""
    cleaned = re.sub(r'^"|"$|\\', '', title.strip())
    if cleaned != title:
        print(f"[TMDB] Cleaned title: '{title}' -> '{cleaned}'")
    return cleaned

def get_metadata(series_name, config):
    """Fetch metadata for a series from TMDb and write to tmp/tmdb.json."""
    base_temp = config["general"]["TEMP_FOLDER"]
    api_key = config["tmdb"]["TMDB_API_KEY"]
    os.makedirs(base_temp, exist_ok=True)
    output_path = os.path.join(base_temp, "tmdb.json")

    search_url = f"https://api.themoviedb.org/3/search/tv?api_key={api_key}&query={requests.utils.quote(series_name)}"

    try:
        show_resp = requests.get(search_url)
        if show_resp.status_code != 200 or not show_resp.json()['results']:
            print(f"[TMDB] Show {series_name} not found.")
            return

        show_data = show_resp.json()['results'][0]
        show_id = show_data.get("id")
        details_url = f"https://api.themoviedb.org/3/tv/{show_id}?api_key={api_key}&append_to_response=seasons"
        details_resp = requests.get(details_url)
        details = details_resp.json()

        output = {
            "title": show_data.get("name"),
            "id": show_id,
            "type": "tv",
            "overview": details.get("overview", ""),
            "first_air_date": show_data.get("first_air_date"),
            "seasons": []
        }

        # Group episodes by season
        season_dict = {}
        for season in details.get("seasons", []):
            s = season.get("season_number", 0)
            season_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{s}?api_key={api_key}"
            season_resp = requests.get(season_url)
            episodes = season_resp.json().get("episodes", [])

            for ep in episodes:
                e = ep.get("episode_number")
                if not e:
                    continue
                ep_data = {
                    "episode_number": e,
                    "air_date": ep.get("air_date"),
                    "titles": {"tmdb": clean_title(ep.get("name"))},
                    "overviews": {"tmdb": ep.get("overview") or ""},
                    "ids": {"tmdb": ep.get("id")}
                }
                season_dict.setdefault(s, []).append(ep_data)

        # Convert season dictionary to list
        output["seasons"] = [
            {
                "season_number": season_num,
                "episodes": episodes
            }
            for season_num, episodes in sorted(season_dict.items())
        ]

        # Delete existing temp file to prevent stale data
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"[TMDB] Deleted existing temp file: {output_path}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[TMDB] Metadata written to {output_path}")

    except Exception as e:
        print(f"[TMDB ERROR] {e}")