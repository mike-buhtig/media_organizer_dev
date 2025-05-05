# providers/tvmazec_provider.py v1.0.0
# Fetches metadata from TVmaze using a class-based interface
# Returns metadata directly instead of writing to temp file
# Based on tvmazef_provider.py v1.0.1

import requests
import re
import html

class TvMazeProvider:
    def __init__(self, config):
        self.api_key = config["tvmaze"].get("TVMAZE_API_KEY", "")
        self.config = config

    def normalize_title(self, title):
        return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

    def clean_title(self, title):
        if not title:
            return ""
        cleaned = re.sub(r'^"|"$|\\', '', title.strip())
        if cleaned != title:
            print(f"[providerc_tvmaze] Cleaned title: '{title}' -> '{cleaned}'")
        return cleaned

    def get_series_metadata(self, series_name):
        search_url = f"https://api.tvmaze.com/singlesearch/shows?q={requests.utils.quote(series_name)}"
        episodes_url_template = "https://api.tvmaze.com/shows/{id}/episodes?specials=1"

        try:
            show_resp = requests.get(search_url)
            if show_resp.status_code != 200:
                print("[providerc_tvmaze] Show The A-Team not found.")
                return {}

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
                "seasons": {}
            }

            for ep in episodes:
                s = ep.get("season", 0)
                e = ep.get("number")
                if e is None or e == 0:
                    continue

                ep_title = self.clean_title(ep.get("name"))
                ep_data = {
                    "episode_number": e,
                    "air_date": ep.get("airdate"),
                    "titles": {"providerc_tvmaze": ep_title},
                    "overviews": {"providerc_tvmaze": html.unescape(re.sub("<[^>]+>", "", ep.get("summary") or ""))},
                    "ids": {"providerc_tvmaze": ep.get("id")}
                }

                output["seasons"].setdefault(s, []).append(ep_data)

            return output

        except Exception as e:
            print(f"[providerc_tvmaze ERROR] {e}")
            return {}