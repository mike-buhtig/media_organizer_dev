find_missing_episodes.py

 ###Goal: To create a script (find_missing_episodes.py) that identifies missing episodes for a given series and includes their full metadata (title, overview, air_date) to aid in future searching.

1. Input (Series Identification):

 - The script will take the series name as a command-line argument, matching the series_name values in the paths.txt [series] section (e.g., "The A-Team").
2. Configuration Loading:

 - The script will load paths.txt to access JSON_FOLDER, TV_LIBRARY_PATH, and the series_path_X for the given series_name.
3. Data Loading:

 - Load Merged Metadata: Load the <series_name>_.json file from [general]JSON_FOLDER.
 - Load Kodi Watched Data: Load the kodi_watched.json file from [general]JSON_FOLDER.
4. Identifying Existing Episodes:

 - From Kodi Watched Data (Input Area): Extract season and episode numbers. Create a set of standardized identifiers.
 - From Output Folder (Moved Episodes via .nfo files): Parse .nfo files for season and episode numbers. Create a set of standardized identifiers.
5. Identifying All Expected Episodes with Full Metadata:

 - Iterate through the seasons list in the loaded <series_name>_.json metadata file.
 - For each episode, extract the season_number, episode_number, title, overview, and air_date.
 - Generate a standardized episode identifier. Store the full metadata associated with each identifier in a dictionary or similar structure.
6. Determining Missing Episodes with Full Metadata:

 - Compare the set of expected episode identifiers with the set of existing identifiers.
 - For each expected identifier that is missing:
 - Retrieve the associated full metadata (title, overview, air_date) from the structure created in step 5.
 - Store this complete episode information in the list of missing episodes.
7. Generating Output JSON for Missing Episodes:

 - Create a <series_name>_missing.json file in [general]JSON_FOLDER.
 - This file will contain a JSON structure with the series_name and a list of missing episodes. Each missing episode will be a dictionary containing:
 - season_number
 - episode_number
 - title
 - overview
 - air_date
### Workflow Integration: (No changes needed here, the order remains the same)

Season_Episode_builder.py
series_folder_crawler.py
kodi_watched_extractor.py
file_organizer.py
find_missing_episodes.py