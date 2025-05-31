# providers/tvmaze.py v1.0.2
# Fetches metadata from TVmaze using a function-based interface
# Converted from tvmazec_provider.py v1.0.0
# Writes standardized metadata to tmp/tvmaze.json
# Uses list-based seasons structure to match requirements
# Version 1.0.1: Added missing json import
# Version 1.0.2: Changed titles, overviews, and ids from dictionaries to strings to match Trakt output

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
        # Search for the TV series by name.
        show_resp = requests.get(search_url)
        # Check if the API request was successful (status code 200).
        if show_resp.status_code != 200:
            print(f"[tvmaze] Show {series_name} not found.")
            return

        # Parse the JSON response containing show information.
        show_data = show_resp.json()
        # Extract the TVmaze show ID.
        show_id = show_data.get("id")
        # Construct the URL to fetch episodes for the found show, including specials.
        episodes_url = episodes_url_template.format(id=show_id)
        # Fetch the episode data from TVmaze.
        ep_resp = requests.get(episodes_url)
        # Parse the JSON response containing episode data if the request was successful.
        episodes = ep_resp.json() if ep_resp.status_code == 200 else []

        # Initialize the output dictionary with series-level information.
        output = {
            "title": show_data.get("name"),
            "id": str(show_id),  # Convert ID to string for consistency
            "type": "tv",
            "overview": html.unescape(re.sub("<[^>]+>", "", show_data.get("summary", ""))),
            "first_air_date": show_data.get("premiered"),
            "seasons": []
        }

        # Dictionary to group episodes by season number.
        season_dict = {}
        # Iterate through each episode fetched from TVmaze.
        for ep in episodes:
            # Get the season number of the episode. Default to 0 if not present.
            s = ep.get("season", 0)
            # Get the episode number within the season.
            e = ep.get("number")
            # Skip episodes with no episode number or episode number 0.
            if e is None or e == 0:
                continue

            # Clean the episode title.
            ep_title = clean_title(ep.get("name"))
            # Create the episode data dictionary.
            ep_data = {
                "episode_number": e,
                "air_date": ep.get("airdate"),
                "title": ep_title,  # Use the cleaned title directly as a string
                "overview": html.unescape(re.sub("<[^>]+>", "", ep.get("summary") or "")), # Use the overview directly as a string
                "id": str(ep.get("id"))  # Use the episode ID directly as a string and convert to string
            }
            # Append the episode data to the list of episodes for the corresponding season in the dictionary.
            season_dict.setdefault(s, []).append(ep_data)

        # Convert the season dictionary to a list of season dictionaries, sorted by season number.
        output["seasons"] = [
            {
                "season_number": season_num,
                "episodes": episodes
            }
            for season_num, episodes in sorted(season_dict.items())
        ]

        # Delete the existing temporary file to ensure no stale data is used.
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"[tvmaze] Deleted existing temp file: {output_path}")

        # Write the processed metadata to the temporary JSON file.
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[tvmaze] Metadata written to {output_path}")

    except Exception as e:
        print(f"[tvmaze ERROR] {e}")