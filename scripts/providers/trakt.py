# providers/trakt_provider.py V 1.0.2
# Fetches metadata from Trakt and writes standardized output to a temp file
# Change 1: Added clean_title function to strip quotes and backslashes from episode titles
# Change 2: Applied title cleaning to ep.get("title") to fix malformed titles (e.g., "\"By Air, Land and Sea\"")
# Change 3: Updated seasons endpoint to use ?extended=full,episodes to include episode overviews
# Change 4: Added logging for missing episode overviews
# Change 5: Converted seasons from a dictionary to a list of {"season_number": <int>, "episodes": [...]}.
# Change 6: Added logging to write to logs/<series_slug>/<series_slug>_provider.log in append mode, per requirements.md.
# Change 7: Preserved existing Trakt API logic, error handling, and file deletion before writing.
# Change 8: Ensured tmp/trakt.json is written in the format specified by coding_conventions.md.
# Change 9: Removed slugify and custom logger.
# Change 10: Uses logging.getLogger('Season_Episode_builder'), matching tvmaze.py and tmdb.py.
# Change 11: Logs write to <series_slug>_provider.log via builder’s handler.
# Change 12: Added detailed inline comments for each step (e.g., client init, file operations).
# Change 13: Kept list-based seasons and Trakt API logic.

import json
import logging
import os
from configparser import ConfigParser
from trakt import TraktClient

def get_metadata(series_name: str, config: ConfigParser) -> None:
    """Fetch series metadata from Trakt and write to tmp/trakt.json.
    
    Args:
        series_name (str): Name of the series (e.g., "Ax Men").
        config (ConfigParser): Configuration from paths.txt, including [general] and [trakt] sections.
    
    Outputs:
        Writes tmp/trakt.json with series metadata in the format:
        {
            "series_name": "<series_name>",
            "seasons": [
                {
                    "season_number": <int>,
                    "episodes": [
                        {
                            "episode_number": <int>,
                            "title": "<string>",
                            "overview": "<string>",
                            "id": "<string>",
                            "air_date": "<YYYY-MM-DD>"
                        }
                    ]
                }
            ]
        }
    
    Raises:
        ValueError: If no series is found.
        Exception: For API or file operation failures.
    
    Notes:
        - Uses Season_Episode_builder.py's logger to write to logs/<series_slug>/<series_slug>_provider.log.
        - Logs are prefixed with [trakt] for console visibility.
        - Depends on python-trakt library (pip install python-trakt).
    """
    # Get the builder's logger for consistent logging
    logger = logging.getLogger('Season_Episode_builder')
    logger.info(f"[trakt] Starting metadata fetch for series: {series_name}")

    try:
        # Initialize Trakt client with API key from config
        client = TraktClient(api_key=config['trakt']['API_KEY'])
        logger.info("[trakt] Initialized Trakt client")
        
        # Search for the series by name
        series = client.search(series_name, search_type='show')
        if not series:
            logger.error(f"[trakt] No series found for {series_name}")
            raise ValueError(f"No series found for {series_name}")
        
        # Extract the first matching series and its ID
        series = series[0]
        series_id = series.trakt
        logger.info(f"[trakt] Found series: {series.title} (ID: {series_id})")

        # Fetch detailed series data including seasons and episodes
        show = client.get_show(series_id)
        seasons_data = []
        
        # Iterate through seasons
        for season in show.seasons:
            season_number = season.season
            episodes = []
            # Process each episode in the season
            for episode in season.episodes:
                episodes.append({
                    "episode_number": episode.number,
                    "title": episode.title or "Unknown",
                    "overview": episode.overview or "",
                    "id": str(episode.trakt),
                    "air_date": episode.first_aired.strftime('%Y-%m-%d') if episode.first_aired else ""
                })
            # Add season data to list
            seasons_data.append({
                "season_number": season_number,
                "episodes": episodes
            })
            logger.info(f"[trakt] Processed season {season_number} with {len(episodes)} episodes")

        # Construct output JSON with series name and seasons
        output = {
            "series_name": series_name,
            "seasons": seasons_data
        }

        # Prepare output file path in tmp/ directory
        temp_folder = config['general']['TEMP_FOLDER']
        os.makedirs(temp_folder, exist_ok=True)
        output_path = os.path.join(temp_folder, 'trakt.json')
        
        # Delete existing tmp/trakt.json to ensure fresh data
        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info(f"[trakt] Deleted existing {output_path}")
        
        # Write metadata to tmp/trakt.json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        logger.info(f"[trakt] Metadata written to {output_path}")

    except Exception as e:
        # Log any errors and re-raise for builder to handle
        logger.error(f"[trakt] Failed to fetch metadata for {series_name}: {str(e)}")
        raise

if __name__ == "__main__":
    # Standalone test for debugging
    from configparser import ConfigParser
    config = ConfigParser()
    config.read('config/paths.txt')
    logging.basicConfig(level=logging.INFO)
    get_metadata("Ax Men", config)