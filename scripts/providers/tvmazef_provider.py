# providers/trakt_provider.py V 1.0.2
# Fetches metadata from Trakt and writes standardized output to a temp file
# Change 1: Added clean_title function to strip quotes and backslashes from episode titles
# Change 2: Applied title cleaning to ep.get("title") to fix malformed titles (e.g., "\"By Air, Land and Sea\"")
# Change 3: Updated seasons endpoint to use ?extended=full,episodes to include episode overviews
# Change 4: Added logging for missing episode overviews

import os
import json
import requests
import re
from configparser import ConfigParser

TRAKT_API = "https://api.trakt.tv"

def clean_title(title):
    if not title:
        return ""
    cleaned = re.sub(r'^"|"$|\\', '', title.strip())
    if cleaned != title:
        print(f"[TRAKT] Cleaned title: '{title}' -> '{cleaned}'")
    return cleaned

def get_metadata(title, config: ConfigParser):
    base_temp = config["general"]["TEMP_FOLDER"]
    client_id = config["trakt"]["TRAKT_CLIENT_ID"]
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id
    }

    os.makedirs(base_temp, exist_ok=True)

    try:
        search_url = f"{TRAKT_API}/search/show?query={requests.utils.quote(title)}"
        resp = requests.get(search_url, headers=headers)
        if resp.status_code != 200 or not resp.json():
            print("[TRAKT] No matching show found.")
            return

        show = resp.json()[0]["show"]
        slug = show["ids"]["slug"]

        summary_url = f"{TRAKT_API}/shows/{slug}?extended=full"
        summary_resp = requests.get(summary_url, headers=headers)
        summary = summary_resp.json() if summary_resp.status_code == 200 else {}

        seasons_url = f"{TRAKT_API}/shows/{slug}/seasons?extended=full,episodes"
        seasons_resp = requests.get(seasons_url, headers=headers)
        all_seasons = seasons_resp.json() if seasons_resp.status_code == 200 else []

        output = {
            "title": show.get("title"),
            "id": show["ids"]["trakt"],
            "type": "tv",
            "overview": summary.get("overview", ""),
            "first_air_date": summary.get("first_aired"),
            "seasons": {}
        }

        for season in all_seasons:
            snum = season.get("number")
            episodes = season.get("episodes", [])
            for ep in episodes:
                ep_title = clean_title(ep.get("title"))
                ep_overview = ep.get("overview", "")
                if not ep_overview:
                    print(f"[TRAKT] Missing overview for S{snum:02d}E{ep.get('number'):02d}")
                ep_data = {
                    "episode_number": ep.get("number"),
                    "air_date": ep.get("first_aired"),
                    "titles": {"trakt": ep_title},
                    "overviews": {"trakt": ep_overview},
                    "ids": {"trakt": ep["ids"]["trakt"]}
                }
                output["seasons"].setdefault(snum, []).append(ep_data)

        output_path = os.path.join(base_temp, "provider_tvmaze.json")
        # Delete existing temp file to prevent stale data
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"[tvmazef] Deleted existing temp file: {output_path}")        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[TRAKT] Metadata written to {output_path}")

    except Exception as e:
        print(f"[TRAKT ERROR] {e}")