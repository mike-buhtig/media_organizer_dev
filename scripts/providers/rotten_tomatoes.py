# rotten_tomatoes_provider.py v1.1.0
# Fetches metadata from Rotten Tomatoes using requests and BeautifulSoup,
# prioritizing structured JSON-LD data.
# Outputs standardized JSON to a temp file for Season_Episode_builder.py.
#
# Requirements:
# - pip install requests beautifulsoup4
#
# Change Log:
# [1.1.0] - 2025-05-21: Major overhaul to standardize output format.
#                      - Outputs JSON identical to rotten_tomatoes2.py (list of seasons, etc.).
#                      - Removed Selenium dependency; now uses only requests and BeautifulSoup.
#                      - Integrated search logic to find main series and special URLs.
#                      - Scrapes specials (season 0) with 'null_X' episode numbering and 'synthetic: True'.
#                      - Improved data extraction priority for special titles, overviews, and air dates.
#                      - Added top-level 'genres' and 'mpa_rating' fields.
#                      - Switched to using `provider_logger` passed from builder.
# [1.0.8] - 2025-05-10: Used <rt-text slot="content"> for synopsis, <rt-text slot="metadataProp"> for air date, minimized selenium
# [1.0.7] - 2025-05-09: Handled synopsis dropdown, fixed air dates, reduced selenium retries
# [1.0.6] - 2025-05-08: Used episodes page for counting, bypassed SSL, set fallback to 20
# [1.0.5] - 2025-05-07: Fixed episode counting, added SSL retry, optimized selenium
# [1.0.4] - 2025-05-06: Used selenium for overviews, deferred specials
# [1.0.3] - 2025-05-05: Counted episodes on season pages, added new overview selector, skipped specials, normalized punctuation
# [1.0.2] - 2025-05-04: Improved title regex, added synopsis selector, optimized runtime, checked /specials, ensured empty overviews
# [1.0.1] - 2025-05-03: Fixed title parsing, added overview selectors, improved season 0 logging, cleaned air dates
# [1.0.0] - 2025-05-01: Initial version, scrapes all seasons/episodes, series name fallback

import os
import json
import requests
import re
import time
from datetime import datetime
from configparser import ConfigParser
from bs4 import BeautifulSoup
from urllib.parse import quote
import logging # Import logging to use the passed logger

# The provider_logger instance will be passed from the Season_Episode_builder.py
# No need to define it globally here or set its level, as the builder handles that.

def normalize_series_name(title: str) -> str:
    """Convert series name to Rotten Tomatoes URL format (e.g., 'Ax Men' -> 'ax_men')"""
    return re.sub(r'\s+', '_', title.lower().strip())

def parse_air_date(raw_date: str) -> str:
    """
    Convert raw date (e.g., 'Aired Mar 9, 2008') to 'YYYY-MM-DD' or ''
    Handles various formats and extracts the date part.
    """
    if not raw_date:
        return ""
    
    # Clean up common prefixes/suffixes
    raw_date = re.sub(r'^(Aired\s+|\s*,\s*)$', '', raw_date.strip())
    
    # Handle date ranges (e.g., "Dec 4, 2013 - Present")
    if ' - ' in raw_date:
        raw_date = raw_date.split(' - ')[0]

    # Try various date formats
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(raw_date, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

def get_metadata(title: str, config: ConfigParser) -> None:
    """
    Fetches Rotten Tomatoes metadata for a TV series, including seasons, episodes,
    and specials (season 0). Prioritizes structured JSON-LD data.
    """
    # Get the provider_logger instance that was set up by the builder
    provider_logger = logging.getLogger("Season_Episode_builder.provider")
    provider_logger.info(f"rotten_tomatoes_provider.py v1.1.0 starting for {title}")

    temp_folder = config["general"]["TEMP_FOLDER"]
    # Output filename for this provider
    temp_file = os.path.join(temp_folder, "rotten_tomatoes.json") 
    scrape_delay = float(config["rotten_tomatoes"].get("SCRAPE_DELAY", 0.5))

    # Initialize data structure to match Season_Episode_builder.py's expectation
    output_data = {
        "series_name": title,
        "seasons": [],
        "genres": [],
        "mpa_rating": ""
    }

    base_url = "https://www.rottentomatoes.com"
    series_slug = normalize_series_name(title)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    # --- Step 1: Search for Series URL and Identify Specials ---
    search_url = f"{base_url}/search?search={quote(title)}"
    main_series_url = None
    special_urls_set = set() # Use a set to store unique special URLs

    try:
        provider_logger.debug(f"Fetching search results from {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        time.sleep(scrape_delay)
        search_soup = BeautifulSoup(response.text, "html.parser")
        provider_logger.debug(f"Search page HTML snippet (first 1000 chars):\n{response.text[:1000]}") # Log HTML snippet

        # Directly find all <a> links with href containing '/tv/'
        tv_links = search_soup.find_all("a", href=re.compile(r'/tv/'))
        
        if not tv_links:
            provider_logger.warning("No <a> links with href containing '/tv/' found on the search page.")

        for link in tv_links:
            href = link.get('href')
            if href:
                # Ensure href is relative before joining with base_url
                if href.startswith(base_url): # If it's already a full URL
                    full_url = href
                    relative_href = href.replace(base_url, "")
                else: # Assume relative URL
                    full_url = f"{base_url}{href}"
                    relative_href = href

                provider_logger.debug(f"Processing link href: {relative_href}")
                
                # Check if it's the main series or a special
                # Main series URL usually ends with just the slug (e.g., /tv/ax_men)
                # Specials have additional parts (e.g., /tv/ax_men_logged_and_loaded)
                if relative_href == f"/tv/{series_slug}":
                    main_series_url = full_url
                    provider_logger.info(f"Identified main series URL: {main_series_url}")
                elif relative_href.startswith(f"/tv/{series_slug}_"):
                    special_urls_set.add(full_url) # Add to set to deduplicate
                    provider_logger.info(f"Identified special URL: {full_url}")
                else:
                    provider_logger.debug(f"Skipping non-relevant TV link (not main series or special): {full_url}")
            else:
                provider_logger.debug(f"Link has no href: {link}")
        
        if not main_series_url:
            provider_logger.error(f"No main series URL found in search results for '{title}'. Cannot proceed.")
            return # Cannot proceed without main series page

    except requests.exceptions.RequestException as e:
        provider_logger.error(f"Error fetching search results for '{title}': {e}")
        return

    special_urls = list(special_urls_set) # Convert set back to list for processing

    # --- Step 2: Get Series-Level Metadata (Genre, MPA Rating, Total Seasons) ---
    total_seasons = 0
    series_genre = []
    series_mpa_rating = ""

    try:
        provider_logger.debug(f"Fetching main series page from {main_series_url}")
        response = requests.get(main_series_url, headers=headers, timeout=10)
        response.raise_for_status()
        time.sleep(scrape_delay)
        series_soup = BeautifulSoup(response.text, "html.parser")

        # Extract total seasons from <rt-text size="1" context="label" slot="title"> (e.g., "10 Seasons")
        seasons_text_elem = series_soup.find("rt-text", {"size": "1", "context": "label", "slot": "title"}, string=re.compile(r'\d+\s+Seasons'))
        if seasons_text_elem:
            match = re.search(r'(\d+)\s+Seasons', seasons_text_elem.get_text(strip=True))
            if match:
                total_seasons = int(match.group(1))
                provider_logger.info(f"Found {total_seasons} seasons for '{title}' from <rt-text>.")
        else:
            provider_logger.warning(f"Could not find total seasons count on series page for '{title}' using <rt-text>. Will try JSON-LD.")

        # Extract genre and MPA rating from JSON-LD or window.mpscall script
        json_ld_script = series_soup.find("script", {"type": "application/ld+json"})
        if json_ld_script:
            try:
                json_ld_data = json.loads(json_ld_script.string)
                if isinstance(json_ld_data, dict):
                    # Genre can be a string or list
                    genre_data = json_ld_data.get("genre")
                    if genre_data:
                        if isinstance(genre_data, list):
                            series_genre = [g.strip() for g in genre_data if g.strip()]
                        elif isinstance(genre_data, str):
                            series_genre = [genre_data.strip()]
                    
                    # MPA rating might be in various places, check common ones
                    if json_ld_data.get("contentRating"): # Common schema.org property
                        series_mpa_rating = json_ld_data["contentRating"].strip()
                    elif json_ld_data.get("ratingValue"): # Sometimes a rating value
                        series_mpa_rating = str(json_ld_data["ratingValue"]).strip()
                    elif json_ld_data.get("mpaaRating"): # Another common property
                        series_mpa_rating = json_ld_data["mpaaRating"].strip()


                provider_logger.debug(f"Extracted from JSON-LD: Genres={series_genre}, MPA={series_mpa_rating}")
            except json.JSONDecodeError as e:
                provider_logger.warning(f"Could not parse JSON-LD on series page: {e}")
        
        # Fallback for genre/MPA from window.mpscall if JSON-LD is not sufficient
        mpscall_script = series_soup.find("script", string=re.compile(r'window\.mpscall\s*='))
        if mpscall_script:
            match = re.search(r'window\.mpscall\s*=\s*(\{.*?\});', mpscall_script.string, re.DOTALL)
            if match:
                try:
                    mps_data = json.loads(match.group(1))
                    if mps_data.get("cag[genre]") and not series_genre:
                        series_genre = [g.strip() for g in mps_data["cag[genre]"].split('|') if g.strip()]
                    if mps_data.get("cag[rating]") and not series_mpa_rating:
                        series_mpa_rating = mps_data["cag[rating]"]
                    elif mps_data.get("cag[mpaa_rating]") and not series_mpa_rating:
                        series_mpa_rating = mps_data["cag[mpaa_rating]"]
                    elif mps_data.get("cag[tv_rating]") and not series_mpa_rating:
                        series_mpa_rating = mps_data["cag[tv_rating]"]
                    provider_logger.debug(f"Extracted from mpscall: Genres={series_genre}, MPA={series_mpa_rating}")
                except json.JSONDecodeError as e:
                    provider_logger.warning(f"Could not parse window.mpscall on series page: {e}")

        output_data["genres"] = series_genre
        output_data["mpa_rating"] = series_mpa_rating.strip() if series_mpa_rating else ""

    except requests.exceptions.RequestException as e:
        provider_logger.error(f"Error fetching main series page for '{title}': {e}")
        # Continue to season scraping even if series page fails, if total_seasons is known or default

    # --- Step 3: Scrape Main Seasons (1 to N) from Season Pages ---
    # If total_seasons was not found, try to infer by checking up to a reasonable max (e.g., 20 seasons)
    if total_seasons == 0:
        provider_logger.info("Total seasons not found, attempting to infer by checking season pages up to 20.")
        for i in range(1, 21): # Max 20 seasons for inference
            season_test_url = f"{main_series_url}/s{i:02d}" # Use main_series_url base
            try:
                test_response = requests.head(season_test_url, headers=headers, timeout=5) # Use HEAD request for efficiency
                if test_response.status_code == 200:
                    total_seasons = i # Update total_seasons to the highest found
                    provider_logger.debug(f"Found season {i} at {season_test_url}")
                else:
                    provider_logger.debug(f"Season {i} not found (status {test_response.status_code}) at {season_test_url}, stopping inference.")
                    break # Stop if a season is not found
            except requests.exceptions.RequestException:
                provider_logger.debug(f"Error checking season {i} at {season_test_url}, stopping inference.")
                break
        provider_logger.info(f"Inferred total seasons: {total_seasons}")


    for season_num in range(1, total_seasons + 1):
        season_url = f"{main_series_url}/s{season_num:02d}" # Use main_series_url base
        provider_logger.debug(f"Fetching season page: {season_url}")
        season_episodes = []
        
        try:
            response = requests.get(season_url, headers=headers, timeout=10)
            response.raise_for_status()
            time.sleep(scrape_delay)
            season_soup = BeautifulSoup(response.text, "html.parser")

            # Prioritize JSON-LD for episode data
            json_ld_script = season_soup.find("script", {"type": "application/ld+json"})
            if json_ld_script:
                try:
                    json_ld_data = json.loads(json_ld_script.string)
                    if isinstance(json_ld_data, dict) and "episode" in json_ld_data:
                        for ep_data in json_ld_data["episode"]:
                            episode_number = int(ep_data.get("episodeNumber", 0)) if ep_data.get("episodeNumber") else 0
                            # Skip episode 0 if it's not a special (specials handled separately)
                            if episode_number == 0:
                                continue

                            title_text = ep_data.get("name", "").strip()
                            overview_text = ep_data.get("description", "").strip()
                            air_date_text = parse_air_date(ep_data.get("dateCreated", "").strip())
                            
                            season_episodes.append({
                                "episode_number": episode_number,
                                "title": title_text,
                                "overview": overview_text,
                                "id": None, # RT does not provide a specific episode ID
                                "air_date": air_date_text
                            })
                        provider_logger.info(f"Successfully scraped Season {season_num} from JSON-LD.")
                    else:
                        provider_logger.warning(f"JSON-LD on Season {season_num} page did not contain expected 'episode' data. Falling back to rt-episode-card.")
                except json.JSONDecodeError as e:
                    provider_logger.warning(f"Could not parse JSON-LD on Season {season_num} page: {e}. Falling back to rt-episode-card.")
            
            # Fallback to rt-episode-card if JSON-LD is missing or incomplete
            if not season_episodes:
                provider_logger.info(f"Attempting to scrape Season {season_num} from rt-episode-card elements.")
                episode_cards = season_soup.find_all("rt-episode-card")
                for card in episode_cards:
                    episode_number = int(card.get("episode-number", 0)) if card.get("episode-number") else 0
                    if episode_number == 0: # Skip if episode number is missing or 0
                        continue
                    
                    title_elem = card.find("a", {"slot": "title", "data-qa": "episode-title"})
                    title_text = title_elem.get_text(strip=True) if title_elem else ""
                    
                    overview_elem = card.find("rt-text", {"slot": "synopsis"}) # Common slot for synopsis
                    if not overview_elem: # Try another common slot
                        overview_elem = card.find("rt-text", {"slot": "content"})
                    overview_text = overview_elem.get_text(strip=True) if overview_elem else ""

                    air_date_elem = card.find("rt-text", {"slot": "metadataProp", "context": "label"})
                    if not air_date_elem:
                        air_date_elem = card.find("time", {"slot": "air-date"})
                    air_date_text = parse_air_date(air_date_elem.get_text(strip=True) if air_date_elem else "")

                    season_episodes.append({
                        "episode_number": episode_number,
                        "title": title_text,
                        "overview": overview_text,
                        "id": None,
                        "air_date": air_date_text
                    })
                if not season_episodes:
                    provider_logger.warning(f"No episodes found for Season {season_num} on {season_url} using rt-episode-card.")

        except requests.exceptions.RequestException as e:
            provider_logger.error(f"Error fetching Season {season_num} page {season_url}: {e}")
            continue # Continue to next season even if this one fails

        if season_episodes:
            # Sort episodes by episode_number before adding to season
            season_episodes.sort(key=lambda x: x.get("episode_number", 0))
            output_data["seasons"].append({
                "season_number": season_num,
                "episodes": season_episodes
            })
    
    # Sort seasons by season_number (this will put season 0 first if it exists after specials are added)
    output_data["seasons"].sort(key=lambda x: x.get("season_number", 999)) 

    # --- Step 4: Scrape Specials (Season 0) ---
    season_0_episodes = []
    processed_special_titles = set() # To prevent duplicate specials in season 0
    special_episode_counter = 1 # For null_X numbering

    for special_url in special_urls:
        provider_logger.debug(f"Fetching special page: {special_url}")
        try:
            response = requests.get(special_url, headers=headers, timeout=10)
            response.raise_for_status()
            time.sleep(scrape_delay)
            special_soup = BeautifulSoup(response.text, "html.parser")

            special_title = ""
            special_overview = ""
            special_air_date = ""
            
            # Priority for special title: photosCarousel script > <title> tag > JSON-LD
            photos_carousel_script = special_soup.find("script", {"id": "photosCarousel", "type": "application/json"})
            if photos_carousel_script:
                try:
                    photos_data = json.loads(photos_carousel_script.string)
                    special_title = photos_data.get("title", "").strip()
                    if special_title:
                        provider_logger.debug(f"Extracted special title from photosCarousel: '{special_title}'")
                except json.JSONDecodeError:
                    pass # Continue to next fallback if parsing fails

            if not special_title:
                title_elem = special_soup.find("title")
                if title_elem:
                    special_title = title_elem.get_text(strip=True).replace(" | Rotten Tomatoes", "")
                    if special_title:
                        provider_logger.debug(f"Extracted special title from <title>: '{special_title}'")

            json_ld_script = special_soup.find("script", {"type": "application/ld+json"})
            if json_ld_script:
                try:
                    json_ld_data = json.loads(json_ld_script.string)
                    if isinstance(json_ld_data, dict):
                        # Extract title from JSON-LD only if not found yet
                        if not special_title:
                            special_title = json_ld_data.get("name", "").strip()
                            if special_title:
                                provider_logger.debug(f"Extracted special title from JSON-LD: '{special_title}'")

                        # Priority for overview: <rt-text data-qa="synopsis-value"> (if not empty) > JSON-LD description
                        overview_from_rt_text = ""
                        overview_elem = special_soup.find("rt-text", {"data-qa": "synopsis-value"})
                        if overview_elem:
                            overview_from_rt_text = overview_elem.get_text(strip=True)
                            if overview_from_rt_text: # Only use if not empty
                                special_overview = overview_from_rt_text
                                provider_logger.debug(f"Extracted special overview from <rt-text>: '{special_overview}'")
                        
                        if not special_overview: # Fallback to JSON-LD description if rt-text is empty or not found
                            special_overview = json_ld_data.get("description", "").strip()
                            if special_overview:
                                provider_logger.debug(f"Extracted special overview from JSON-LD: '{special_overview}'")

                        # Priority for air_date: <rt-text data-qa="item-value"> (Release Date) > mpscall > JSON-LD dateCreated
                        # Find the "Release Date" label and then its sibling value
                        release_date_label = special_soup.find("rt-text", {"class": "key", "size": "0.875", "data-qa": "item-label"}, string="Release Date")
                        if release_date_label:
                            release_date_value_group = release_date_label.find_parent("dt").find_next_sibling("dd", {"data-qa": "item-value-group"})
                            if release_date_value_group:
                                release_date_text_elem = release_date_value_group.find("rt-text", {"data-qa": "item-value"})
                                if release_date_text_elem:
                                    special_air_date = parse_air_date(release_date_text_elem.get_text(strip=True))
                                    if special_air_date:
                                        provider_logger.debug(f"Extracted special air date from <rt-text>: '{special_air_date}'")

                        if not special_air_date: # Fallback to JSON-LD dateCreated if rt-text is empty or not found
                            special_air_date = parse_air_date(json_ld_data.get("dateCreated", "").strip())
                            if special_air_date:
                                provider_logger.debug(f"Extracted special air date from JSON-LD: '{special_air_date}'")
                        
                        # Try to get genre from special if not already found at series level
                        if json_ld_data.get("genre") and not output_data["genres"]:
                            genre_data = json_ld_data.get("genre")
                            if isinstance(genre_data, list):
                                output_data["genres"] = [g.strip() for g in genre_data if g.strip()]
                            elif isinstance(genre_data, str):
                                output_data["genres"] = [genre_data.strip()]
                        
                        # Try to get MPA rating from special if not already found at series level
                        if json_ld_data.get("contentRating") and not output_data["mpa_rating"]:
                            output_data["mpa_rating"] = json_ld_data["contentRating"].strip()
                        elif json_ld_data.get("rating") and not output_data["mpa_rating"]:
                            output_data["mpa_rating"] = json_ld_data["rating"].strip()

                    provider_logger.debug(f"Extracted from special JSON-LD (final check): Title='{special_title}', Overview='{special_overview}', AirDate='{special_air_date}'")
                except json.JSONDecodeError as e:
                    provider_logger.warning(f"Could not parse JSON-LD on special page {special_url}: {e}. Falling back to other elements.")
            
            # Fallback for air_date from window.mpscall if other methods failed
            if not special_air_date:
                mpscall_script = special_soup.find("script", string=re.compile(r'window\.mpscall\s*='))
                if mpscall_script:
                    match = re.search(r'window\.mpscall\s*=\s*(\{.*?\});', mpscall_script.string, re.DOTALL)
                    if match:
                        try:
                            mps_data = json.loads(match.group(1))
                            if mps_data.get("cag[release]"):
                                special_air_date = parse_air_date(mps_data["cag[release]"])
                                if special_air_date:
                                    provider_logger.debug(f"Extracted special air date from mpscall: '{special_air_date}'")
                            # Try to get genre/MPA from mpscall if not already found
                            if mps_data.get("cag[genre]") and not output_data["genres"]:
                                output_data["genres"] = [g.strip() for g in mps_data["cag[genre]"].split('|') if g.strip()]
                            if mps_data.get("cag[rating]") and not output_data["mpa_rating"]:
                                output_data["mpa_rating"] = mps_data["cag[rating]"]
                            elif mps_data.get("cag[mpaa_rating]") and not output_data["mpa_data"]:
                                output_data["mpa_rating"] = mps_data["cag[mpaa_rating]"]
                            elif mps_data.get("cag[tv_rating]") and not output_data["mpa_rating"]:
                                output_data["mpa_rating"] = mps_data["cag[tv_rating]"]
                        except json.JSONDecodeError as e:
                            provider_logger.warning(f"Could not parse window.mpscall on special page {special_url}: {e}")

            # Ensure all fields are strings, even if empty
            special_title = special_title or ""
            special_overview = special_overview or ""
            special_air_date = special_air_date or ""

            if special_title and special_title not in processed_special_titles: # Only add if we have a title and it's not a duplicate
                episode_number_for_special = f"null_{special_episode_counter}"
                season_0_episodes.append({
                    "episode_number": episode_number_for_special, # Unique 'null_X' numbering for specials
                    "title": special_title,
                    "overview": special_overview,
                    "id": None,
                    "air_date": special_air_date,
                    "synthetic": True # Mark as synthetic for builder
                })
                processed_special_titles.add(special_title) # Add title to set to track processed specials
                special_episode_counter += 1
            else:
                if special_title:
                    provider_logger.info(f"Skipping duplicate special: '{special_title}' at {special_url}")
                else:
                    provider_logger.warning(f"Could not find title for special at {special_url}, skipping this special.")

        except requests.exceptions.RequestException as e:
            provider_logger.error(f"Error fetching special page {special_url}: {e}")
            continue

    if season_0_episodes:
        # Sort specials by air_date if available, otherwise by title for consistent ordering
        season_0_episodes.sort(key=lambda x: (x.get("air_date") or "", x.get("title", "")))
        output_data["seasons"].insert(0, { # Insert at beginning to ensure season 0 is first
            "season_number": 0,
            "episodes": season_0_episodes
        })

    # --- Step 5: Write Output JSON ---
    os.makedirs(temp_folder, exist_ok=True)
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        provider_logger.info(f"Successfully saved metadata to {temp_file}")
    except Exception as e:
        provider_logger.error(f"Error writing metadata to {temp_file}: {e}")

