# tmdbc_provider.py v1.0.0
# Fetches series metadata from TMDB API
#
# Change Log:
# [1.0.0] - 2025-05-04: Initial class-based version based on tmdbf_provider.py

import os
import requests
import json
import re
from configparser import ConfigParser
from json_utils import clean_temp_file, format_provider_json

class TMDBProvider:
    def __init__(self, config: ConfigParser):
        self.config = config
        self.api_key = config["tmdb"]["API_KEY"]
        self.base_temp = config["general"]["TEMP_FOLDER"]
        os.makedirs(self.base_temp, exist_ok=True)
        self.output_path = os.path.join(self.base_temp, "provider_tmdb.json")

    def normalize_title(self, title: str) -> str:
        """Normalize title for API search."""
        return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

    def get_metadata(self, title: str) -> None:
        """Fetch metadata for the given series title."""
        clean_temp_file(self.output_path, "tmdb")

        search_url = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={requests.utils.quote(self.normalize_title(title))}"
        try:
            show_resp = requests.get(search_url, timeout=10)
            if show_resp.status_code != 200:
                print(f"[tmdb] No show found for '{title}' (status: {show_resp.status_code})")
                return

            show_data = show_resp.json().get("results", [])
            if not show_data:
                print(f"[tmdb] No show found for '{title}'")
                return

            show_id = show_data[0].get("id")
            details_url = f"https://api.themoviedb.org/3/tv/{show_id}?api_key={self.api_key}&append_to_response=seasons"
            show_resp = requests.get(details_url, timeout=10)
            show_data = show_resp.json() if show_resp.status_code == 200 else {}

            seasons_data = {}
            for season in show_data.get("seasons", []):
                season_num = season.get("season_number", 0)
                episodes_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season_num}?api_key={self.api_key}"
                ep_resp = requests.get(episodes_url, timeout=10)
                episodes = ep_resp.json().get("episodes", []) if ep_resp.status_code == 200 else []

                ep_data = [
                    {
                        "number": ep.get("episode_number", 0),
                        "title": ep.get("name", ""),
                        "overview": ep.get("overview", ""),
                        "air_date": ep.get("air_date", ""),
                        "id": str(ep.get("id", ""))
                    } for ep in episodes if ep.get("episode_number")
                ]
                if ep_data:
                    seasons_data[season_num] = ep_data

            if seasons_data:
                format_provider_json(title, seasons_data, "tmdb", self.output_path)
            else:
                print(f"[tmdb] No season data found for '{title}'")

        except requests.RequestException as e:
            print(f"[tmdb] Network error for '{title}': {e}")
        except Exception as e:
            print(f"[tmdb] Error processing '{title}': {e}")