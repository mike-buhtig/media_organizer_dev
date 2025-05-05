# rotten_tomatoesf_provider.py v1.0.9
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

import os
import json
import requests
import re
import time
import sys
from datetime import datetime
from configparser import ConfigParser
from bs4 import BeautifulSoup
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def log_message(message, log_dir, max_lines=500):
    """Log message to builder.log, matching season_episode_builder.py"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "builder.log")
    timestamped = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}"
    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            lines = lines[-max_lines+1:]
        else:
            lines = []
        lines.append(timestamped + "\n")
        with open(log_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"[LOGGING ERROR] {e}", file=sys.stderr)

def normalize_series_name(title):
    """Convert series name to Rotten Tomatoes URL format (e.g., 'Ax Men' -> 'ax_men')"""
    return re.sub(r'\s+', '_', title.lower().strip())

def search_series(title, log_dir):
    """Search Google for correct Rotten Tomatoes URL on 404"""
    query = f'site:rottentomatoes.com "{title}"'
    url = f"https://www.google.com/search?q={quote(query)}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "rottentomatoes.com/tv/" in href:
                match = re.search(r'/tv/([^/]+)', href)
                if match:
                    return match.group(1)
        log_message(f"No Rotten Tomatoes URL found for '{title}'", log_dir)
        return None
    except Exception as e:
        log_message(f"Search error for '{title}': {e}", log_dir)
        return None

def parse_air_date(raw_date):
    """Convert raw date (e.g., 'Aired Mar 9, 2008,') to 'YYYY-MM-DD' or ''"""
    if not raw_date or '–' in raw_date:
        return ""
    try:
        raw_date = re.sub(r'^(Aired\s+|\s*,\s*)$', '', raw_date.strip())
        for fmt in ["%b %d, %Y", "%B %d, %Y"]:
            try:
                dt = datetime.strptime(raw_date, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""
    except Exception:
        return ""

def get_metadata(title, config):
    """Fetch Rotten Tomatoes metadata for all seasons/episodes"""
    log_dir = config["general"]["LOG_PATH"]
    temp_file = os.path.join(config["general"]["TEMP_FOLDER"], "provider_rotten_tomatoes.json")
    delay = float(config["rotten_tomatoes"].get("SCRAPE_DELAY", 0.5))
    
    # Delete existing temp file to prevent stale data
    if os.path.exists(temp_file):
        os.remove(temp_file)
        log_message(f"Deleted existing temp file: {temp_file}", log_dir)
    
    series = normalize_series_name(title)
    data = {"seasons": {}}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
    selenium_failures = 0
    max_selenium_failures = 1

    # Initialize selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--ignore-certificate-errors")
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(), options=chrome_options)
        log_message("Selenium initialized successfully", log_dir)
    except Exception as e:
        log_message(f"Selenium setup failed: {e}, falling back to requests", log_dir)

    # Fetch series page
    base_url = "https://www.rottentomatoes.com"
    series_url = f"{base_url}/tv/{series}"
    try:
        response = requests.get(series_url, headers=headers, timeout=10)
        if response.status_code == 404:
            log_message(f"404 for {series_url}, searching for series", log_dir)
            series = search_series(title, log_dir)
            if not series:
                log_message(f"Series '{title}' not found on Rotten Tomatoes", log_dir)
                return
            series_url = f"{base_url}/tv/{series}"
            response = requests.get(series_url, headers=headers, timeout=10)
        response.raise_for_status()
        time.sleep(delay)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            log_message(f"429 Rate Limit for {series_url}, consider increasing SCRAPE_DELAY", log_dir)
            delay = min(delay + 0.5, 2.0)
        else:
            log_message(f"Error fetching {series_url}: {e}", log_dir)
        return
    except Exception as e:
        log_message(f"Error fetching {series_url}: {e}", log_dir)
        return

    # Parse seasons
    soup = BeautifulSoup(response.text, "html.parser")
    season_links = soup.find_all("a", href=re.compile(r'/tv/{}/s\d+'.format(series)))
    seasons = [int(re.search(r's(\d+)', link["href"]).group(1)) for link in season_links] if season_links else [i for i in range(1, 11)]

    # Skip specials
    log_message(f"Specials unavailable for '{title}', defer to thetvdb_provider.py", log_dir)

    for season in seasons:
        episodes_url = f"{base_url}/tv/{series}/s{season:02d}#episodes"
        try:
            response = requests.get(episodes_url, headers=headers, timeout=10)
            response.raise_for_status()
            time.sleep(delay)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                log_message(f"429 Rate Limit for {episodes_url}, increasing delay to {delay + 0.5}s", log_dir)
                delay = min(delay + 0.5, 2.0)
            elif e.response.status_code == 404:
                log_message(f"404 for {episodes_url}, skipping season", log_dir)
                continue
            log_message(f"Error fetching {episodes_url}: {e}", log_dir)
            continue
        except Exception as e:
            log_message(f"Error fetching {episodes_url}: {e}", log_dir)
            continue

        # Parse episodes
        soup = BeautifulSoup(response.text, "html.parser")
        episode_rows = soup.find_all("rt-episode-card")
        episodes = []
        for row in episode_rows:
            ep_num = int(row.get("episode-number", 0))
            if ep_num == 0:
                continue
            title_elem = row.find("a", {"slot": "title", "data-qa": "episode-title"})
            title = title_elem.text.strip() if title_elem else ""
            title = title.replace("`", "'")
            episodes.append({"number": ep_num, "title": title})

        if not episodes:
            log_message(f"No episodes found on {episodes_url}, falling back to 20", log_dir)
            episodes = [{"number": i, "title": ""} for i in range(1, 21)]

        data["seasons"][str(season)] = []
        for ep in episodes:
            ep_num = ep["number"]
            ep_url = f"{base_url}/tv/{series}/s{season:02d}/e{ep_num:02d}"
            description = ""
            air_date = ""
            for attempt in range(2):
                try:
                    # Try requests first
                    response = requests.get(ep_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "html.parser")
                    time.sleep(delay)

                    # Extract metadata
                    title_elem = soup.find("h1", {"data-qa": "episode-title"}) or soup.find("h1", class_="episode-title") or soup.find("h1")
                    description_elem = soup.find("rt-text", {"slot": "content"}) or soup.find("p", {"data-qa": "episode-synopsis"})
                    air_date_elem = soup.find("rt-text", {"slot": "metadataProp", "context": "label"}) or soup.find("time", {"slot": "air-date"})

                    title = title_elem.text.strip() if title_elem else ep["title"]
                    title = re.sub(r'^.*? – Season \d+, Episode \d+ ', '', title)
                    title = title.replace("`", "'")
                    description = description_elem.text.strip() if description_elem else ""
                    air_date = parse_air_date(air_date_elem.text.strip() if air_date_elem else "")

                    # If description is empty, try selenium
                    if not description and driver and selenium_failures < max_selenium_failures:
                        driver.get(ep_url)
                        try:
                            dropdown = WebDriverWait(driver, 2).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "rt-link[slot='ctaOpen']"))
                            )
                            dropdown.click()
                            time.sleep(0.3)
                        except:
                            log_message(f"Dropdown click failed for {ep_url}, extracting visible text", log_dir)
                        WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "rt-text[slot='content']"))
                        )
                        soup = BeautifulSoup(driver.page_source, "html.parser")
                        description_elem = soup.find("rt-text", {"slot": "content"})
                        description = description_elem.text.strip() if description_elem else ""

                    if not title:
                        log_message(f"No title found for {ep_url}, skipping episode", log_dir)
                        continue

                    data["seasons"][str(season)].append({
                        "episode_number": ep_num,
                        "air_date": air_date,
                        "titles": {"rotten_tomatoes": title},
                        "overviews": {"rotten_tomatoes": description},
                        "ids": {"rotten_tomatoes": None},
                        "synthetic_number": False
                    })
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        log_message(f"429 Rate Limit for {ep_url}, increasing delay to {delay + 0.5}s", log_dir)
                        delay = min(delay + 0.5, 2.0)
                    elif e.response.status_code == 404:
                        log_message(f"404 for {ep_url}, possible missing data", log_dir)
                    else:
                        log_message(f"Error fetching {ep_url}: {e}", log_dir)
                    break
                except Exception as e:
                    if driver and "SSL" in str(e):
                        log_message(f"SSL error for {ep_url}, retrying ({attempt + 1}/2)", log_dir)
                        time.sleep(1)
                        continue
                    log_message(f"Error fetching {ep_url}: {e}", log_dir)
                    if driver:
                        selenium_failures += 1
                        if selenium_failures >= max_selenium_failures:
                            log_message(f"Too many selenium failures, switching to requests", log_dir)
                            driver.quit()
                            driver = None
                    break

    if driver:
        driver.quit()

    # Write output
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log_message(f"Saved metadata to {temp_file}", log_dir)
    except Exception as e:
        log_message(f"Error writing {temp_file}: {e}", log_dir)