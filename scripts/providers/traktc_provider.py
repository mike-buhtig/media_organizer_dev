# traktc_provider.py v1.0.0
# Fetches series metadata from Trakt API
#
# Change Log:
# [1.0.0] - 2025-05-04: Initial class-based version based on traktf_provider.py

import os
import requests
import json
import re
from configparser import ConfigParser
from json_utils import clean_temp_file, format_provider_json

class TraktProvider:
    def __init__(self, config: ConfigParser):
        self.config = config
        self.client_id = config["trakt"]["CLIENT_ID"]
        self.base_temp = config["general"]["TEMP_FOLDER"]
        os.makedirs(self.base_temp, exist_ok=True)
        self.output_path = os.path.join(self.base_temp, "provider_trakt.json")

    def normalize_title(self, title: str) -> str:
        """Normalize title for API search."""
        return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

    def get_metadata(self, title: str) -> None:
        """Fetch metadata for the given series title."""
        clean_temp_file(self.output_path, "trakt")

        search_url = f"https://api.trakt.tv/search/show?query={requests.utils.quote(self.normalize_title(title))}"
        headers = {"trakt-api-version": "2", "trakt-api-key": self.client_id}
        try:
            show_resp = requests.get(search_url, headers=headers, timeout=10)
            if show_resp.status_code != 200:
                print(f"[trakt] No show found for '{title}' (status: {show_resp.status_code})")
                return

            show_data = show_resp.json()
            if not show_data:
                print(f"[trakt] No show found for '{title}'")
                return

            show_id = show_data[0]["show"]["ids"]["trakt"]
            episodes_url = f"https://api.trakt.tv/shows/{show_id}/episodes?extended=full"
            ep_resp = requests.get(episodes_url, headers=headers, timeout=10)
            episodes = ep_resp.json() if ep_resp.status_code == 200 else []

            seasons_data = {}
            for ep in episodes:
                season_num = ep.get("season", 0)
                ep_num = ep.get("number", 0)
                if not ep_num:
                    continue

                ep_data = {
                    "number": ep_num,
                    "title": ep.get("title", ""),
                    "overview": ep.get("overview", ""),
                    "air_date": ep.get("first_aired", "").split("T")[0] if ep.get("first_aired") else "",
                    "id": str(ep.get("ids", {}).get("trakt", ""))
                }
                seasons_data.setdefault(season_num, []).append(ep_data)

            if seasons_data:
                format_provider_json(title, seasons_data, "trakt", self.output_path)
            else:
                print(f"[trakt] No season data found for '{title}'")

        except requests.RequestException as e:
            print(f"[trakt] Network error for '{title}': {e}")
        except Exception as e:
            print(f"[trakt] Error processing '{title}': {e}")