# providers/tmdb.py v1.0.2
# Fetches metadata from TMDb using a function-based interface
# Based on tmdbf_provider.py v1.0.0
# Writes standardized metadata to tmp/tmdb.json
# Version 1.0.1: Updated to use list-based seasons structure
# Version 1.0.2: Changed titles, overviews, and ids from dictionaries to strings to match Trakt output

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

    # Construct the URL to search for the TV series by name.
    search_url = f"https://api.themoviedb.org/3/search/tv?api_key={api_key}&query={requests.utils.quote(series_name)}"

    try:
        # Send a GET request to the TMDb search API.
        show_resp = requests.get(search_url)
        # Check if the API request was successful (status code 200) and if there are any results.
        if show_resp.status_code != 200 or not show_resp.json()['results']:
            print(f"[TMDB] Show {series_name} not found.")
            return

        # Extract the first matching show from the search results.
        show_data = show_resp.json()['results'][0]
        # Get the TMDb ID of the show.
        show_id = show_data.get("id")
        # Construct the URL to fetch detailed information about the show, including seasons.
        details_url = f"https://api.themoviedb.org/3/tv/{show_id}?api_key={api_key}&append_to_response=seasons"
        # Send a GET request to the TMDb details API.
        details_resp = requests.get(details_url)
        # Parse the JSON response containing the show details.
        details = details_resp.json()

        # Initialize the output dictionary with series-level information.
        output = {
            "title": show_data.get("name"),
            "id": str(show_id),  # Convert ID to string for consistency
            "type": "tv",
            "overview": details.get("overview", ""),
            "first_air_date": show_data.get("first_air_date"),
            "seasons": []
        }

        # Dictionary to group episodes by season number.
        season_dict = {}
        # Iterate through each season listed in the show details.
        for season in details.get("seasons", []):
            # Get the season number. Default to 0 if not present.
            s = season.get("season_number", 0)
            # Construct the URL to fetch episodes for the specific season.
            season_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{s}?api_key={api_key}"
            # Send a GET request to the TMDb season API.
            season_resp = requests.get(season_url)
            # Parse the JSON response containing the episodes for the season.
            episodes = season_resp.json().get("episodes", [])

            # Iterate through each episode in the current season.
            for ep in episodes:
                # Get the episode number within the season.
                e = ep.get("episode_number")
                # Skip episodes with no episode number.
                if not e:
                    continue
                # Create the episode data dictionary.
                ep_data = {
                    "episode_number": e,
                    "air_date": ep.get("air_date"),
                    "title": clean_title(ep.get("name")),  # Use the cleaned title directly as a string
                    "overview": ep.get("overview") or "",  # Use the overview directly as a string
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
            print(f"[TMDB] Deleted existing temp file: {output_path}")

        # Write the processed metadata to the temporary JSON file.
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[TMDB] Metadata written to {output_path}")

    except Exception as e:
        print(f"[TMDB ERROR] {e}")