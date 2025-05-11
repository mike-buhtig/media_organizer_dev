# trakt.py v1.0.3
# Fetches metadata from Trakt.tv and writes standardized output to a temp file
#
# Requirements:
# - pip install requests
#
# Change Log:
# [1.0.0] - 2025-04-01: Initial version, fetches seasons/episodes
# [1.0.1] - 2025-04-15: Added clean_title function, fixed malformed titles
# [1.0.2] - 2025-05-01: Updated seasons endpoint to extended=full,episodes, added logging for missing overviews
# [1.0.3] - 2025-05-16: Changed output to tmp/trakt.json, used logging module, aligned JSON with Season_Episode_builder.py, added detailed comments

import os
import json
import requests
import re
import logging
from configparser import ConfigParser

# Initialize logger to match Season_Episode_builder.py
logger = logging.getLogger('Season_Episode_builder')

# Base URL for Trakt.tv API
TRAKT_API = "https://api.trakt.tv"

def clean_title(title: str) -> str:
    """Clean episode titles by removing quotes and backslashes.
    
    Args:
        title (str): Raw episode title from Trakt API.
    
    Returns:
        str: Cleaned title with quotes and backslashes removed.
    
    Notes:
        - Logs cleaning action if title changes.
        - Returns empty string if title is None.
    """
    if not title:
        logger.info("[trakt] Cleaned title: None -> ''")
        return ""
    cleaned = re.sub(r'^"|"$|\\', '', title.strip())
    if cleaned != title:
        logger.info(f"[trakt] Cleaned title: '{title}' -> '{cleaned}'")
    return cleaned

def get_metadata(title: str, config: ConfigParser) -> None:
    """Fetch series metadata from Trakt.tv and write to tmp/trakt.json.
    
    Args:
        title (str): Series name (e.g., "Ax Men").
        config (ConfigParser): Configuration from paths.txt with [general] and [trakt] sections.
    
    Outputs:
        Writes tmp/trakt.json with series metadata in the format:
        {
            "series_name": "<title>",
            "seasons": [
                {
                    "season_number": <int>,
                    "episodes": [
                        {
                            "episode_number": <int>,
                            "title": "<string>",
                            "overview": "<string>",
                            "id": "<string>",
                            "air_date": "<string>"
                        }
                    ]
                }
            ]
        }
    
    Raises:
        Exception: If API requests or file operations fail.
    
    Notes:
        - Uses Trakt API with client ID from config['trakt']['TRAKT_CLIENT_ID'].
        - Logs to logs/<series_slug>/<series_slug>_provider.log via Season_Episode_builder.py's logger.
        - Matches tvmaze.py and tmdb.py logging style with [trakt] prefix.
        - Depends on requests library (pip install requests).
    """
    logger.info(f"[trakt] Starting metadata fetch for series: {title}")

    # Get temp folder from config
    base_temp = config["general"]["TEMP_FOLDER"]
    
    # Get Trakt client ID from config
    client_id = config["trakt"]["TRAKT_CLIENT_ID"]
    
    # Set up API headers
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id
    }
    logger.debug(f"[trakt] API headers: {headers}")

    # Create temp folder if it doesn't exist
    os.makedirs(base_temp, exist_ok=True)

    try:
        # Search for series by title
        search_url = f"{TRAKT_API}/search/show?query={requests.utils.quote(title)}"
        logger.debug(f"[trakt] Search URL: {search_url}")
        resp = requests.get(search_url, headers=headers)
        if resp.status_code != 200 or not resp.json():
            logger.error("[trakt] No matching show found")
            return

        # Extract show data from first search result
        show = resp.json()[0]["show"]
        slug = show["ids"]["slug"]
        logger.info(f"[trakt] Found series: {show['title']} (slug: {slug})")

        # Fetch series summary
        summary_url = f"{TRAKT_API}/shows/{slug}?extended=full"
        logger.debug(f"[trakt] Summary URL: {summary_url}")
        summary_resp = requests.get(summary_url, headers=headers)
        summary = summary_resp.json() if summary_resp.status_code == 200 else {}
        logger.debug(f"[trakt] Summary data fetched")

        # Fetch seasons and episodes
        seasons_url = f"{TRAKT_API}/shows/{slug}/seasons?extended=full,episodes"
        logger.debug(f"[trakt] Seasons URL: {seasons_url}")
        seasons_resp = requests.get(seasons_url, headers=headers)
        all_seasons = seasons_resp.json() if seasons_resp.status_code == 200 else []
        logger.debug(f"[trakt] Seasons data fetched: {len(all_seasons)} seasons")

        # Initialize output structure
        output = {
            "series_name": show.get("title"),
            "seasons": []
        }

        # Process each season
        for season in all_seasons:
            snum = season.get("number")
            episodes = season.get("episodes", [])
            season_data = {
                "season_number": snum,
                "episodes": []
            }
            
            # Process each episode
            for ep in episodes:
                ep_title = clean_title(ep.get("title"))
                ep_overview = ep.get("overview", "")
                if not ep_overview:
                    logger.info(f"[trakt] Missing overview for S{snum:02d}E{ep.get('number'):02d}")
                air_date = ep.get("first_aired")
                if air_date:
                    air_date = air_date[:10]  # Truncate to YYYY-MM-DD
                ep_data = {
                    "episode_number": ep.get("number"),
                    "title": ep_title,
                    "overview": ep_overview,
                    "id": str(ep["ids"]["trakt"]),
                    "air_date": air_date or ""
                }
                season_data["episodes"].append(ep_data)
            
            # Add season to output if it has episodes
            if season_data["episodes"]:
                output["seasons"].append(season_data)
                logger.info(f"[trakt] Processed season {snum} with {len(season_data['episodes'])} episodes")

        # Define output path
        output_path = os.path.join(base_temp, "trakt.json")
        
        # Delete existing file if present
        if os.path.exists(output_path):
            logger.info(f"[trakt] Deleted existing {output_path}")
            os.remove(output_path)

        # Write JSON output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        logger.info(f"[trakt] Metadata written to {output_path}")

    except Exception as e:
        logger.error(f"[trakt] Failed to fetch metadata for {title}: {str(e)}")
        raise