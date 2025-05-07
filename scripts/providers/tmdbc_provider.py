# tmdbc_provider.py v1.0.0
# Fetches series metadata from TMDB API
#
# Change Log:
# [1.0.0] - 2025-05-04: Initial class-based version based on tmdbf_provider.py

import os  # For file path operations (e.g., creating temp folder, joining paths)
import requests  # For making HTTP requests to TMDb API
import json  # For parsing JSON responses from API
import re  # For regular expression-based title normalization
from configparser import ConfigParser  # For reading config from paths.txt
from json_utils import clean_temp_file, format_provider_json  # Utility functions for JSON handling

class tmdbcprovider:
    def __init__(self, config: ConfigParser):
        # Initialize the provider with configuration from paths.txt
        # - config: ConfigParser object with settings (e.g., API key, temp folder)
        self.config = config
        # Extract TMDb API key from config's [tmdb] section
        self.api_key = config["tmdb"]["API_KEY"]
        # Get temporary folder path from config's [general] section (e.g., 'tmp')
        self.base_temp = config["general"]["TEMP_FOLDER"]
        # Create temp folder if it doesn't exist
        os.makedirs(self.base_temp, exist_ok=True)
        # Define output path for temporary JSON file (e.g., 'tmp/provider_tmdb.json')
        self.output_path = os.path.join(self.base_temp, "provider_tmdb.json")

    def normalize_title(self, title: str) -> str:
        # Normalize a series title for API search
        # - Input: Raw title (e.g., "The A-Team")
        # - Process: Convert to lowercase, replace special quotes with single quote
        # - Output: Normalized title (e.g., "the a-team")
        # - Note: Used to make API queries more robust
        return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

    def get_metadata(self, title: str) -> None:
        # Fetch metadata for the given series title and write to temp JSON
        # - Input: Series title (e.g., "The A-Team")
        # - Process: Search TMDb API, fetch show details, collect season/episode data
        # - Output: Writes JSON to self.output_path (e.g., 'tmp/provider_tmdb.json')
        # - Note: Returns None; relies on file output for Season_Episode_builder.py

        # Step 1: Clean any existing temp file to avoid stale data
        # - Calls json_utils.clean_temp_file to remove or reset provider_tmdb.json
        clean_temp_file(self.output_path, "tmdb")

        # Step 2: Search TMDb API for the series
        # - Construct search URL with normalized title and API key
        # - Example: https://api.themoviedb.org/3/search/tv?api_key=KEY&query=the+a-team
        search_url = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={requests.utils.quote(self.normalize_title(title))}"
        try:
            # Make HTTP GET request to search for the series
            show_resp = requests.get(search_url, timeout=10)
            # Check if request failed (e.g., 404, 500)
            if show_resp.status_code != 200:
                print(f"[tmdb] No show found for '{title}' (status: {show_resp.status_code})")
                return

            # Parse JSON response and get list of results
            show_data = show_resp.json().get("results", [])
            # If no results, log and exit
            if not show_data:
                print(f"[tmdb] No show found for '{title}'")
                return

            # Step 3: Get show ID from first result (assumes best match)
            show_id = show_data[0].get("id")
            # Fetch detailed show data, including seasons
            # - URL: https://api.themoviedb.org/3/tv/{show_id}?api_key=KEY&append_to_response=seasons
            details_url = f"https://api.themoviedb.org/3/tv/{show_id}?api_key={self.api_key}&append_to_response=seasons"
            show_resp = requests.get(details_url, timeout=10)
            # Parse show details if request succeeded
            show_data = show_resp.json() if show_resp.status_code == 200 else {}

            # Step 4: Process seasons and episodes
            seasons_data = {}
            # Iterate through seasons in show data
            for season in show_data.get("seasons", []):
                # Get season number (0 for specials)
                season_num = season.get("season_number", 0)
                # Fetch episode details for this season
                # - URL: https://api.themoviedb.org/3/tv/{show_id}/season/{season_num}?api_key=KEY
                episodes_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season_num}?api_key={self.api_key}"
                ep_resp = requests.get(episodes_url, timeout=10)
                # Parse episodes if request succeeded
                episodes = ep_resp.json().get("episodes", []) if ep_resp.status_code == 200 else []

                # Step 5: Build episode data list
                ep_data = [
                    {
                        # Episode number (e.g., 10)
                        "number": ep.get("episode_number", 0),
                        # Episode title (e.g., "One More Time")
                        "title": ep.get("name", ""),
                        # Episode overview/description
                        "overview": ep.get("overview", ""),
                        # Air date (e.g., "1983-04-12")
                        "air_date": ep.get("air_date", ""),
                        # TMDb episode ID (converted to string)
                        "id": str(ep.get("id", ""))
                    } for ep in episodes if ep.get("episode_number")
                ]
                # Add episode data to seasons_data if not empty
                if ep_data:
                    seasons_data[season_num] = ep_data

            # Step 6: Write JSON output if seasons were found
            if seasons_data:
                # Call json_utils.format_provider_json to structure and write JSON
                # - Inputs: series title, seasons data, provider name ("tmdb"), output path
                # - Output: Writes to tmp/provider_tmdb.json with format defined in json_utils
                format_provider_json(title, seasons_data, "tmdb", self.output_path)
            else:
                print(f"[tmdb] No season data found for '{title}'")

        except requests.RequestException as e:
            # Handle network errors (e.g., timeout, connection failure)
            print(f"[tmdb] Network error for '{title}': {e}")
        except Exception as e:
            # Handle other errors (e.g., JSON parsing, unexpected issues)
            print(f"[tmdb] Error processing '{title}': {e}")