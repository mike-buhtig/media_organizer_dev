Script Relationships for Media Organizer
This document details the purpose, functionality, and relationships between scripts in the media_organizer project, ensuring accurate interactions to prevent errors like those before Season_Episode_builder.py v1.0.10. Each script is mapped to actions in plans/requirements.md, with plain English explanations of how scripts call each other, including input/output files and JSON keys.
Overview

Purpose: Define how scripts work together to pull Kodi data, process NextPVR recordings, fetch metadata, match files, organize files, update the NextPVR database, and generate comskip files.
Scripts: Core scripts in scripts/ and provider scripts in scripts/providers/.
Reference: Mandatory for development to ensure correct imports, file paths, and JSON keys.

Scripts and Relationships
1. Season_Episode_builder.py

Purpose: Fetches TV series metadata from multiple providers and builds episode metadata (Action 3 in requirements.md).
Functionality:
Reads config/paths.txt for provider settings (e.g., providerc_tvmaze=enabled, TVMAZE_API_KEY).
Currently Loads 8 providers: providerc_tvmaze, providerf_tvmaze, providerc_tmdb, providerf_tmdb, providerc_trakt, providerf_trakt, providerc_rotten_tomatoes, providerf_rotten_tomatoes.
Calls provider scripts to fetch metadata (e.g., episode titles, descriptions).
Merges data into data/the_a_team/The_A-Team.json with keys: series_name, seasons (array of season_number, episodes with episode_number, titles, overviews, ids).
Writes temporary files to tmp/provider_<name>.json (e.g., tmp/provider_tvmaze.json).


Calls:
json_utils.py: Uses format_builder_json to write The_A-Team.json.
Provider Scripts (in scripts/providers/):
tvmazec_provider.py: Class-based, called via TvMazeProvider.process(series_name).
tvmazef_provider.py: Function-based, called via process_tvmaze_metadata(series_name, temp_folder, config).
tmdbc_provider.py, tmdbf_provider.py, traktc_provider.py, traktf_provider.py, rotten_tomatoesc_provider.py, rotten_tomatoesf_provider.py: Similar class/function calls.


Inputs:
config/paths.txt: Provider enablement, API keys, JSON_FOLDER=data, TEMP_FOLDER=tmp.
Command-line: --series "The A-Team".


Outputs:
data/the_a_team/The_A-Team.json: Merged metadata.
tmp/provider_<name>.json: Provider-specific data.
logs/the_a_team/builder.log: Logs provider loads, errors.




Keys:
series_name: e.g., "The A-Team".
seasons: Array with season_number, episodes.
episodes: Array with episode_number, air_date, titles (e.g., {"providerc_tvmaze": "Mexican Slayride: Part 1"}), overviews, ids.


Issues (v1.0.10):
providerc_tmdb, providerc_trakt, providerc_rotten_tomatoes fail due to missing format_provider_json in json_utils.py.
Only providerc_tvmaze data appears in The_A-Team.json.



2. file_organizer.py

Purpose: Organizes NextPVR recording files into series/season folders, creates .nfo files, and optionally moves files (Action 5 in requirements.md).
Functionality:
Reads data/the_a_team/The_A-Team_Processed.json for matched episodes and file details.
Creates .nfo files (e.g., Series/The A-Team/Season 01/The A-Team - S01E10 - One More Time.nfo) with metadata from highest-priority provider.
Optionally moves .ts, .xml, .edl files to Series/The A-Team/Season XX/ with --move flag, using largest unbroken .ts.
Writes new .xml files with provider metadata.


Calls:
json_utils.py: Reads The_A-Team_Processed.json (likely via a JSON parsing function).
Inputs:
data/the_a_team/The_A-Team_Processed.json: Episode matches, file paths, watched status.
config/paths.txt: series_path_1 for source folder.


Outputs:
.nfo files in Series/The A-Team/Season XX/.
Moved files (if --move).
logs/the_a_team/file_organizer.log.




Keys:
series_name, seasons, episodes, providers (with name, priority, title, description), files (with path, size, broken), xml_metadata, watched_status, standard_name.


Issues: Fails due to path/format mismatch in The_A-Team_Processed.json (needs JSON snippet to debug).

3. series_folder_crawler.py

Purpose: Scans NextPVR recording folders to collect .ts and .xml file details (Action 2 in requirements.md).
Functionality:
Scans folders from config/paths.txt (e.g., series_path_1=D:/NEXT PVR/RecordingDirectory/The A-Team).
Extracts .xml metadata (<subtitle>, <Title>).
Groups .ts and .xml by subtitle, marks broken files (e.g., -0).
Records file sizes.
Writes data/the_a_team/The_A-Team_Processed.json with file details.


Calls:
json_utils.py: Writes The_A-Team_Processed.json.
Inputs:
config/paths.txt: Recording paths.
Command-line: Series name.


Outputs:
data/the_a_team/The_A-Team_Processed.json: File groups, sizes, broken status.




Keys:
series_name, seasons, episodes, files (with path, size, broken), xml_metadata (with subtitle, description).



4. kodi_db_exporter.py

Purpose: Extracts watched status and episode data from Kodi databases (Action 1 in requirements.md).
Functionality:
Accesses Kodi SQLite databases (Android via ADB, non-Android directly).
Merges data from multiple databases.
Extracts series, season, episode, path, watched status, source (addon or file).
Writes data/kodi_data.json.


Calls:
json_utils.py: Writes kodi_data.json.
Inputs: Database paths (possibly from paths.txt).
Outputs:
data/kodi_data.json: Series, episode, path, watched status.




Keys:
series_name, seasons, episodes (with episode_number, path, watched_status, source).



5. match_unmatched.py

Purpose: Matches NextPVR files to provider metadata and integrates Kodi watched status (Action 4 in requirements.md).
Functionality:
Reads data/the_a_team/The_A-Team.json (provider metadata) and data/the_a_team/The_A-Team_Processed.json (file details).
Matches .xml subtitles to provider titles (normalized).
Integrates watched status from data/kodi_data.json.
Updates The_A-Team_Processed.json with matches.


Calls:
json_utils.py: Reads/writes JSON files.
Inputs:
The_A-Team.json, The_A-Team_Processed.json, kodi_data.json.


Outputs:
Updated The_A-Team_Processed.json.




Keys:
Matches xml_metadata.subtitle to providers.normalized_title, adds watched_status, standard_name.



6. process_kodi_data.py

Purpose: Processes Kodi data for integration with other scripts (likely supports Action 1 or 4).
Functionality:
Likely preprocesses kodi_data.json for match_unmatched.py.
Normalizes addon names (e.g., The.A-Team.S01E10.One.More.Time).


Calls:
json_utils.py: Reads/writes JSON.
Inputs: kodi_data.json.
Outputs: Possibly intermediate JSON or direct input to match_unmatched.py.


Keys: series_name, episodes, source.

7. json_utils.py

Purpose: Provides utility functions for JSON reading, writing, and formatting (supports all scripts).
Functionality:
Functions like format_builder_json, format_provider_json (missing in v1.0.10, causing provider failures).
Handles JSON standards from requirements.md.


Called By:
Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, match_unmatched.py, process_kodi_data.py.


Inputs/Outputs: JSON files (e.g., The_A-Team.json, kodi_data.json).
Keys: Varies by script (e.g., series_name, episodes).

8. Provider Scripts (in scripts/providers/)

Scripts: tvmazec_provider.py, tvmazef_provider.py, tmdbc_provider.py, tmdbf_provider.py, traktc_provider.py, traktf_provider.py, rotten_tomatoesc_provider.py, rotten_tomatoesf_provider.py.
Purpose: Fetch metadata from APIs or web scraping (Action 3 in requirements.md).
Functionality:
Class-based (c_) use a Provider class (e.g., TvMazeProvider).
Function-based (f_) use process_<name>_metadata functions.
Write tmp/provider_<name>.json with episode data.


Called By:
Season_Episode_builder.py: Imports and calls each provider.


Inputs:
config/paths.txt: API keys, temp folder.
Series name from Season_Episode_builder.py.


Outputs:
tmp/provider_<name>.json: Episode metadata.


Keys:
seasons, episodes (with episode_number, title, overview, id).


Issues:
tmdbc_provider.py, traktc_provider.py, rotten_tomatoesc_provider.py fail due to missing format_provider_json.



Call Flow

kodi_db_exporter.py → kodi_data.json (Action 1).
series_folder_crawler.py → The_A-Team_Processed.json (Action 2).
Season_Episode_builder.py → Calls providers → tmp/provider_<name>.json → The_A-Team.json (Action 3).
match_unmatched.py → Reads The_A-Team.json, The_A-Team_Processed.json, kodi_data.json → Updates The_A-Team_Processed.json (Action 4).
file_organizer.py → Reads The_A-Team_Processed.json → Creates .nfo, moves files (Action 5).
process_kodi_data.py → Supports kodi_db_exporter.py or match_unmatched.py.

Notes

json_utils.py is critical for all scripts but needs format_provider_json to fix provider failures.
Logs: Each script writes to logs/the_a_team/<script>.log.
Next Steps: Fix json_utils.py, update provider scripts, test all 8 providers.

