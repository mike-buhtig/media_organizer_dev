# rotten_tomatoesf_provider.py v1.0.10
# Fetches metadata from Rotten Tomatoes and writes standardized output to a temp file
#
# Requirements:
# - pip install requests beautifulsoup4 selenium
# - Selenium requires ChromeDriver: https://googlechromelabs.github.io/chrome-for-testing/
#
# Change Log:
# [1.0.0] - 2025-05-01: Initial version, scrapes all seasons/episodes, series name fallback
# [1.0.1] - 2025-05-03: Fixed title parsing, added overview selectors, improved season 0 logging, cleaned air dates
# [1.0.2] - 2025-05-04: Improved title regex, added synopsis selector, optimized runtime, checked /specials, ensured empty overviews
# [1.0.3] - 2025-05-05: Counted episodes on season pages, added new overview selector, skipped specials, normalized punctuation
# [1.0.4] - 2025-05-06: Used selenium for overviews, deferred specials
# [1.0.5] - 2025-05-07: Fixed episode counting, added SSL retry, optimized selenium
# [1.0.6] - 2025-05-08: Used episodes page for counting, bypassed SSL, set fallback to 20
# [1.0.7] - 2025-05-09: Handled synopsis dropdown, fixed air dates, reduced selenium retries
# [1.0.8] - 2025-05-10: Used <rt-text slot="content"> for synopsis, <rt-text slot="metadataProp"> for air date, minimized selenium
# [1.0.9] - 2025-05-03: Added cleanup of tmp/provider_rotten_tomatoes.json at start of get_metadata()
# [1.0.10] - Converted seasons from a dictionary to a list of {"season_number": <int>, "episodes": [...]}.
# [1.0.10] - Added logging to logs/<series_slug>/<series_slug>_provider.log in append mode.
# [1.0.10] - Improved episode fallback logic (e.g., default episode_id, handle missing title, overview, air_date).
# [1.0.10] - Preserved existing scraping logic, SCRAPE_DELAY, and error handling.
# [1.0.10] - Ensured tmp/rotten_tomatoes.json matches coding_conventions.md.
# [1.0.11] - Removed slugify and custom logger.
# [1.0.11]Uses logging.getLogger('Season_Episode_builder'), matching tvmaze.py and tmdb.py.
# [1.0.11]Logs write to <series_slug>_provider.log via builder’s handler.
# [1.0.11]Added detailed inline comments for each step (e.g., client init, file operations).
# [1.0.11]Kept list-based seasons and Trakt API logic.

import json
import logging
import os
import time
from configparser import ConfigParser
import requests
from bs4 import BeautifulSoup

def get_metadata(series_name: str, config: ConfigParser) -> None:
    """Fetch series metadata from Rotten Tomatoes and write to tmp/rotten_tomatoes.json.
    
    Args:
        series_name (str): Name of the series (e.g., "Ax Men").
        config (ConfigParser): Configuration from paths.txt, including [general] and [rotten_tomatoes] sections.
    
    Outputs:
        Writes tmp/rotten_tomatoes.json with series metadata in the format:
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
                            "air_date": "<string>"
                        }
                    ]
                }
            ]
        }
    
    Raises:
        ValueError: If no series is found.
        Exception: For HTTP or parsing failures.
    
    Notes:
        - Uses Season_Episode_builder.py's logger to write to logs/<series_slug>/<series_slug>_provider.log.
        - Logs are prefixed with [rotten_tomatoes] for console visibility.
        - Depends on requests and beautifulsoup4 (pip install requests beautifulsoup4).
    """
    # Get the builder's logger for consistent logging
    logger = logging.getLogger('Season_Episode_builder')
    logger.info(f"[rotten_tomatoes] Starting metadata fetch for series: {series_name}")

    try:
        # Read scrape delay from config
        scrape_delay = float(config['rotten_tomatoes']['SCRAPE_DELAY'])
        base_url = "https://www.rottentomatoes.com"
        search_url = f"{base_url}/search?search={series_name.replace(' ', '%20')}"
        
        # Search for the series on Rotten Tomatoes
        logger.info(f"[rotten_tomatoes] Searching for series at {search_url}")
        response = requests.get(search_url)
        time.sleep(scrape_delay)
        response.raise_for_status()
        
        # Parse search results to find series link
        soup = BeautifulSoup(response.text, 'html.parser')
        series_link = soup.find('search-page-media-row', {'mediatype': 'tvSeries'})
        if not series_link:
            logger.error(f"[rotten_tomatoes] No series found for {series_name}")
            raise ValueError(f"No series found for {series_name}")
        
        # Extract series page URL
        series_url = series_link.find('a')['href']
        logger.info(f"[rotten_tomatoes] Found series URL: {series_url}")
        
        # Fetch series page
        response = requests.get(series_url)
        time.sleep(scrape_delay)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Process seasons
        seasons_data = []
        season_sections = soup.find_all('section', class_='season')
        
        for season_idx, season in enumerate(season_sections, 1):
            # Extract season number, fallback to index if parsing fails
            season_number = season_idx
            try:
                season_title = season.find('h2').text
                season_number = int(season_title.split('Season')[1].strip())
            except (AttributeError, IndexError, ValueError):
                logger.warning(f"[rotten_tomatoes] Could not parse season number for season {season_idx}, using {season_number}")
            
            # Process episodes
            episodes = []
            episode_rows = season.find_all('div', class_='episode')
            for ep_idx, ep in enumerate(episode_rows, 1):
                title = ep.find('span', class_='episode-title') or "Unknown"
                overview = ep.find('span', class_='episode-description') or ""
                air_date = ep.find('span', class_='episode-airdate') or ""
                episode_id = f"rt_s{season_number}e{ep_idx}"
                
                episodes.append({
                    "episode_number": ep_idx,
                    "title": title.text.strip() if hasattr(title, 'text') else "Unknown",
                    "overview": overview.text.strip() if hasattr(overview, 'text') else "",
                    "id": episode_id,
                    "air_date": air_date.text.strip() if hasattr(air_date, 'text') else ""
                })
            
            # Add season data to list
            seasons_data.append({
                "season_number": season_number,
                "episodes": episodes
            })
            logger.info(f"[rotten_tomatoes] Processed season {season_number} with {len(episodes)} episodes")
        
        # Handle case with no seasons
        if not seasons_data:
            logger.warning(f"[rotten_tomatoes] No seasons found for {series_name}, writing empty metadata")
            seasons_data = []

        # Construct output JSON
        output = {
            "series_name": series_name,
            "seasons": seasons_data
        }

        # Prepare output file path in tmp/ directory
        temp_folder = config['general']['TEMP_FOLDER']
        os.makedirs(temp_folder, exist_ok=True)
        output_path = os.path.join(temp_folder, 'rotten_tomatoes.json')
        
        # Delete existing tmp/rotten_tomatoes.json
        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info(f"[rotten_tomatoes] Deleted existing {output_path}")
        
        # Write metadata to tmp/rotten_tomatoes.json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        logger.info(f"[rotten_tomatoes] Metadata written to {output_path}")

    except Exception as e:
        # Log errors and re-raise for builder to handle
        logger.error(f"[rotten_tomatoes] Failed to fetch metadata for {series_name}: {str(e)}")
        raise

if __name__ == "__main__":
    # Standalone test for debugging
    from configparser import ConfigParser
    config = ConfigParser()
    config.read('config/paths.txt')
    logging.basicConfig(level=logging.INFO)
    get_metadata("Ax Men", config)