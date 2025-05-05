# rotten_tomatosec_provider.py v1.0.0
# Fetches series metadata from Rotten Tomatoes using Selenium
#
# Change Log:
# [1.0.0] - 2025-05-04: Initial class-based version based on rotten_tomatoesf_provider.py

import os
import json
import re
import time
from configparser import ConfigParser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from json_utils import clean_temp_file, format_provider_json

class RottenTomatoesProvider:
    def __init__(self, config: ConfigParser):
        self.config = config
        self.base_temp = config["general"]["TEMP_FOLDER"]
        os.makedirs(self.base_temp, exist_ok=True)
        self.output_path = os.path.join(self.base_temp, "provider_rotten_tomatoes.json")
        self.series_name = ""

    def normalize_title(self, title: str) -> str:
        """Normalize title for URL and search."""
        return re.sub(r"[`‘’´]", "'", title.strip().lower()) if title else ""

    def get_metadata(self, title: str) -> None:
        """Fetch metadata for the given series title."""
        self.series_name = title
        clean_temp_file(self.output_path, "rotten_tomatoes")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        driver = None

        try:
            driver = webdriver.Chrome(options=chrome_options)
            print("[rotten_tomatoes] Selenium initialized successfully")
            series_url = self.find_series_url(driver)
            if not series_url:
                print(f"[rotten_tomatoes] Series '{title}' not found on Rotten Tomatoes")
                return

            seasons_data = self.scrape_seasons(driver, series_url)
            if seasons_data:
                format_provider_json(title, seasons_data, "rotten_tomatoes", self.output_path)
            else:
                print(f"[rotten_tomatoes] No season data found for '{title}'")

        except Exception as e:
            print(f"[rotten_tomatoes] Error processing '{title}': {e}")
        finally:
            if driver:
                driver.quit()

    def find_series_url(self, driver: webdriver.Chrome) -> str:
        """Search for the series on Rotten Tomatoes and return its URL."""
        search_url = f"https://www.rottentomatoes.com/search?search={requests.utils.quote(self.normalize_title(self.series_name))}"
        driver.get(search_url)
        time.sleep(2)

        try:
            series_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'search-page-media-row[mediatype="Series"] a'))
            )
            return series_link.get_attribute("href")
        except:
            driver.get(f"https://www.rottentomatoes.com/tv/{self.normalize_title(self.series_name).replace(' ', '_')}")
            if driver.current_url == "https://www.rottentomatoes.com/404":
                print(f"[rotten_tomatoes] 404 for https://www.rottentomatoes.com/tv/{self.normalize_title(self.series_name).replace(' ', '_')}")
                return ""
            return driver.current_url

    def scrape_seasons(self, driver: webdriver.Chrome, series_url: str) -> dict:
        """Scrape season and episode data from the series page."""
        driver.get(series_url)
        seasons_data = {}

        try:
            season_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "media-scorecard"))
            )
            for season_elem in season_elements:
                season_title = season_elem.find_element(By.CSS_SELECTOR, "h3").text
                season_num = re.search(r"Season (\d+)", season_title)
                if not season_num:
                    continue
                season_num = int(season_num.group(1))

                episodes = []
                episode_elements = season_elem.find_elements(By.CSS_SELECTOR, "episode-item")
                for ep_elem in episode_elements:
                    ep_num = ep_elem.get_attribute("episodenumber")
                    if not ep_num:
                        continue
                    ep_data = {
                        "number": int(ep_num),
                        "title": ep_elem.find_element(By.CSS_SELECTOR, "h4").text,
                        "overview": ep_elem.find_element(By.CSS_SELECTOR, "p").text,
                        "air_date": ep_elem.get_attribute("airdate") or "",
                        "id": ep_elem.get_attribute("episodeid") or None
                    }
                    episodes.append(ep_data)

                if episodes:
                    seasons_data[season_num] = episodes

            return seasons_data
        except Exception as e:
            print(f"[rotten_tomatoes] Error scraping seasons for '{self.series_name}': {e}")
            return {}