# providers/tvmaze.py v1.0.1
# Fetches metadata from TVmaze using a function-based interface
# Converted from tvmazec_provider.py v1.0.0
# Writes standardized metadata to tmp/tvmaze.json
# Uses list-based seasons structure to match requirements
# Version 1.0.1: Added missing json import

import os
import json
import requests
import re
import html

def normalize_title(title):
    """Normalize title by converting quotes and stripping case."""
    return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

def clean_title(title):
    """Clean title by removing quotes and backslashes."""
    if not title:
        return ""
    cleaned = re.sub(r'^"|"$|\\', '', title.strip())
    if cleaned != title:
        print(f"[tvmaze] Cleaned title: '{title}' -> '{cleaned}'")
    return cleaned

def get_metadata(series_name, config):
    """Fetch metadata for a series from TVmaze and write to tmp/tvmaze.json."""
    base_temp = config["general"]["TEMP_FOLDER"]
    os.makedirs(base_temp, exist_ok=True)
    output_path = os.path.join(base_temp, "tvmaze.json")

    search_url = f"https://api.tvmaze.com/singlesearch/shows?q={requests.utils.quote(series_name)}"
    episodes_url_template = "https://api.tvmaze.com/shows/{id}/episodes?specials=1"

    try:
        show_resp = requests.get(search_url)
        if show_resp.status_code != 200:
            print(f"[tvmaze] Show {series_name} not found.")
            return

        show_data = show_resp.json()
        show_id = show_data.get("id")
        episodes_url = episodes_url_template.format(id=show_id)
        ep_resp = requests.get(episodes_url)
        episodes = ep_resp.json() if ep_resp.status_code == 200 else []

        output = {
            "title": show_data.get("name"),
            "id": show_id,
            "type": "tv",
            "overview": html.unescape(re.sub("<[^>]+>", "", show_data.get("summary", ""))),
            "first_air_date": show_data.get("premiered"),
            "seasons": []
        }

        # Group episodes by season
        season_dict = {}
        for ep in episodes:
            s = ep.get("season", 0)
            e = ep.get("number")
            if e is None or e == 0:
                continue

            ep_title = clean_title(ep.get("name"))
            ep_data = {
                "episode_number": e,
                "air_date": ep.get("airdate"),
                "titles": {"tvmaze": ep_title},
                "overviews": {"tvmaze": html.unescape(re.sub("<[^>]+>", "", ep.get("summary") or ""))},
                "ids": {"tvmaze": ep.get("id")}
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
            print(f"[tvmaze] Deleted existing temp file: {output_path}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[tvmaze] Metadata written to {output_path}")

    except Exception as e:
        print(f"[tvmaze ERROR] {e}")