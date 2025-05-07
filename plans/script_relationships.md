Script Relationships for Media Organizer
This document details the purpose, functionality, and relationships between scripts in the media_organizer project, ensuring accurate interactions to prevent errors like those before Season_Episode_builder.py v1.0.10. Each script is mapped to actions in plans/requirements.md, with plain English explanations of how scripts call each other, including input/output files and JSON keys.
Overview

Purpose: Define how scripts work together to pull Kodi data, process NextPVR recordings, fetch metadata, match files, organize files, update the NextPVR database, and generate comskip files.
Scripts: Core scripts in scripts/ and provider scripts in scripts/providers/.
Reference: Mandatory for development to ensure correct imports, file paths, and JSON keys.
Providers: Supports 8 providers from four sources (TVMaze, TMDb, Trakt, Rotten Tomatoes), covering nearly 100% of tested series metadata (season/episode, titles, overviews, air dates). Providers are class-based (provider_namec_provider.py, class provider_namecprovider, keys like tvmazec) or function-based (provider_namef_provider.py, keys like tvmazef). New providers can be added by creating scripts and enabling in config/paths.txt.

Scripts and Relationships
1. Season_Episode_builder.py

Purpose: Fetches TV series metadata from multiple providers and builds episode metadata (Action 3 in requirements.md).
Functionality:
Reads config/paths.txt for provider settings (e.g., providerc_tvmaze=enabled, TVMAZE_API_KEY) and folder paths (e.g., TEMP_FOLDER=tmp).
Loads 8 providers: providerc_tvmaze, providerf_tvmaze, providerc_tmdb, providerf_tmdb, providerc_trakt, providerf_trakt, providerc_rotten_tomatoes, providerf_rotten_tomatoes. Providers can be added or disabled in paths.txt.
Supports two provider types:
Class-based (provider_namec_provider.py, e.g., tvmazec_provider.py): Uses a class named provider_namecprovider (e.g., tvmazecprovider in v1.0.11).
Function-based (provider_namef_provider.py, e.g., tvmazef_provider.py): Uses a get_metadata function, writes to tmp/providerf_<name>.json (e.g., tmp/providerf_tvmaze.json).


Calls providers to fetch metadata (e.g., episode titles, descriptions).
Merges data into data/<series_slug>/<series_name>.json (e.g., data/ax_men/Ax Men.json) with a single episode instance, grouping provider data under title, normalized_title, overview, id with keys like tvmazec, tvmazef.
Reads temporary files from tmp/providerf_<name>.json for function-based providers.


Calls:
Provider Scripts (in scripts/providers/):
tvmazec_provider.py: Calls tvmazecprovider.get_series_metadata(series_name).
tvmazef_provider.py: Calls get_metadata(series_name, config), reads tmp/providerf_tvmaze.json.
Similarly for tmdbc_provider.py (tmdbcprovider), tmdbf_provider.py (tmp/providerf_tmdb.json), traktc_provider.py (traktcprovider), traktf_provider.py (tmp/providerf_trakt.json), rotten_tomatoesc_provider.py (rotten_tomatoescprovider), rotten_tomatoesf_provider.py (tmp/providerf_rotten_tomatoes.json).


Inputs:
config/paths.txt: Provider enablement, API keys, folder paths (JSON_FOLDER=data, TEMP_FOLDER=tmp, LOG_PATH=logs).
Command-line: --series "Ax Men".


Outputs:
data/ax_men/Ax Men.json: Merged metadata with title, normalized_title, overview, id objects (e.g., tvmazec, tmdbf keys in v1.0.11).
tmp/providerf_<name>.json: Function-based provider data (read by builder).
logs/ax_men/builder.log: Logs provider loads, errors, temp file checks.




Keys (for Ax Men.json):
series_name: e.g., "Ax Men".
seasons: Array with season_number, episodes.
episodes: Array with episode_number, air_date, title (e.g., {"tvmazec": "Man vs. Mountain"}), normalized_title, overview, id.


Issues (v1.0.11):
providerc_tmdb, providerc_trakt, providerc_rotten_tomatoes fail due to missing format_provider_json in json_utils.py.
tvmazec_provider may bypass json_utils.py, needs verification.



2. file_organizer.py

Purpose: Organizes NextPVR recording files into series/season folders, creates .nfo files, and optionally moves files (Action 5 in requirements.md).
Functionality:
Reads data/<series_slug>/<series_name>_Processed.json for matched episodes and file details.
Creates .nfo files (e.g., Series/Ax Men/Season 01/Ax Men - S01E01 - Man vs. Mountain.nfo) with metadata from first provider in paths.txt.
Optionally moves .ts, .xml, .edl files to Series/Ax Men/Season XX/ with --move flag, using largest unbroken .ts.
Writes new .xml files with provider metadata.


Calls:
json_utils.py: Reads <series_name>_Processed.json.
Inputs:
data/ax_men/Ax Men_Processed.json: Episode matches, file paths, watched status.
config/paths.txt: series_path_1 for source folder.


Outputs:
.nfo files in Series/Ax Men/Season XX/.
Moved files (if --move).
logs/ax_men/file_organizer.log.




Keys:
series_name, seasons, episodes, providers (with name, title, normalized_title, description), files (with path, size, broken), xml_metadata, watched_status, standard_name.


Issues: Fails due to path/format mismatch in <series_name>_Processed.json (needs JSON snippet to debug).

3. series_folder_crawler.py

Purpose: Scans NextPVR recording folders to collect .ts and .xml file details (Action 2 in requirements.md).
Functionality:
Scans folders from config/paths.txt (e.g., series_path_1=D:/NEXT PVR/RecordingDirectory/Ax Men).
Extracts .xml metadata (<subtitle>, <Title>).
Groups .ts and .xml by subtitle, marks broken files (e.g., -0).
Records file sizes.
Writes data/ax_men/Ax Men_Processed.json with file details.


Calls:
json_utils.py: Writes <series_name>_Processed.json.
Inputs:
config/paths.txt: Recording paths.
Command-line: Series name.


Outputs:
data/ax_men/Ax Men_Processed.json: File groups, sizes, broken status.




Keys:
series_name, seasons, episodes, providers (with name, title, normalized_title, description), files (with path, size, broken), xml_metadata, watched_status, standard_name.



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
data/kodi_data.json: Series, episode, path, watched status (format pending).




Keys: series_name, seasons, episodes (with episode_number, path, watched_status, source).

5. match_unmatched.py

Purpose: Matches NextPVR files to provider metadata and integrates Kodi watched status (Action 4 in requirements.md).
Functionality:
Reads data/ax_men/Ax Men.json (provider metadata) and data/ax_men/Ax Men_Processed.json (file details).
Matches .xml subtitles to provider normalized_title.
Integrates watched status from data/kodi_data.json.
Updates Ax Men_Processed.json with matches.


Calls:
json_utils.py: Reads/writes JSON files.
Inputs:
Ax Men.json, Ax Men_Processed.json, kodi_data.json.


Outputs:
Updated Ax Men_Processed.json.




Keys:
Matches xml_metadata.subtitle to providers.normalized_title, adds watched_status, standard_name.



6. process_kodi_data.py

Purpose: Processes Kodi data for integration with other scripts (likely supports Action 1 or 4).
Functionality:
Preprocesses kodi_data.json for match_unmatched.py.
Normalizes addon names (e.g., Ax.Men.S01E01.Man.vs.Mountain).


Calls:
json_utils.py: Reads/writes JSON.
Inputs: kodi_data.json.
Outputs: Intermediate JSON or input to match_unmatched.py.


Keys: series_name, episodes, source.

7. json_utils.py

Purpose: Provides utility functions for JSON reading, writing, and formatting (supports all scripts).
Functionality:
Functions like format_provider_json (missing in v1.0.11, causing provider failures).
Handles JSON standards from requirements.md.
Plan to add title normalization and JSON structuring for Series_Name.json.


Called By:
Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, match_unmatched.py, process_kodi_data.py.


Inputs/Outputs: JSON files (e.g., Ax Men.json, kodi_data.json).
Keys: Varies by script (e.g., series_name, episodes).

8. Provider Scripts (in scripts/providers/)

Scripts: tvmazec_provider.py, tvmazef_provider.py, tmdbc_provider.py, tmdbf_provider.py, traktc_provider.py, traktf_provider.py, rotten_tomatoesc_provider.py, rotten_tomatoesf_provider.py.
Purpose: Fetch metadata from APIs or web scraping (Action 3 in requirements.md).
Functionality:
Class-based (provider_namec_provider.py): Use a class named provider_namecprovider (e.g., tvmazecprovider), return metadata directly.
Function-based (provider_namef_provider.py): Use get_metadata(series_name, config), write to tmp/providerf_<name>.json.


Called By:
Season_Episode_builder.py: Imports and calls each provider.


Inputs:
config/paths.txt: API keys, temp folder (TEMP_FOLDER=tmp).
Series name from Season_Episode_builder.py.


Outputs:
tmp/providerf_<name>.json: Episode metadata (function-based).
Direct metadata return (class-based).


Keys (for providerf_<name>.json):
series_name, seasons (object with season numbers), episodes (with episode_number, air_date, title, normalized_title, overview, id).


Issues:
tmdbc_provider.py, traktc_provider.py, rotten_tomatoesc_provider.py fail due to missing format_provider_json.



Call Flow

kodi_db_exporter.py → kodi_data.json (Action 1).
series_folder_crawler.py → <series_name>_Processed.json (Action 2).
Season_Episode_builder.py → Calls providers → tmp/providerf_<name>.json (function-based) → <series_name>.json (Action 3).
match_unmatched.py → Reads <series_name>.json, <series_name>_Processed.json, kodi_data.json → Updates <series_name>_Processed.json (Action 4).
file_organizer.py → Reads <series_name>_Processed.json → Creates .nfo, moves files (Action 5).
process_kodi_data.py → Supports kodi_db_exporter.py or match_unmatched.py.

Notes

Path Conventions:
TEMP_FOLDER (e.g., tmp): Used by function-based providers to write tmp/providerf_<name>.json and by builder to read them.
JSON_FOLDER (e.g., data): Output directory for <series_name>.json.
LOG_PATH (e.g., logs): Directory for script logs.
Provider files: providerf_<name>.json for function-based, no temp files for class-based.


Provider Conventions:
providerc_<name>: Class-based providers (e.g., providerc_tvmaze), use provider_namecprovider class, JSON keys like tvmazec.
providerf_<name>: Function-based providers (e.g., providerf_tvmaze), write tmp/providerf_<name>.json, JSON keys like tvmazef.


JSON Formats:
Series_Name.json: Compact with title, normalized_title, overview, id objects using provider keys (e.g., tvmazec).
providerf_<name>.json: Provider-specific metadata with title, normalized_title.
Series_Name_Processed.json: Includes files, xml_metadata, watched_status with providers array.


Next Steps: Update Season_Episode_builder.py and provider scripts for new Series_Name.json format, plan to refactor formatting into json_utils.py later.

