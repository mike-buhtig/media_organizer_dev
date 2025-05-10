Media Organizer Project RequirementsThis document outlines the functional and technical requirements for the Media Organizer project, which automates the organization and metadata management of TV series media files for integration with Kodi and NextPVR.
Related Documents
This document must be used in conjunction with:

plans/coding_conventions.md: Defines coding practices, including no hard-coding of providers.
plans/script_relationships.md: Describes script interactions and dependencies.Failure to consult all three documents may result in non-compliant code or functionality.

Governance Rules

No Unauthorized Deletions: No sections, settings, or content in this document, other governing documents (coding_conventions.md, script_relationships.md), or configuration files (paths.txt, paths.example.txt) may be removed without explicit approval from the project engineer. All content serves a purpose, and unauthorized deletions may lead to loss of critical functionality or data.
Preserve Script Logic: Scripts (Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, providers/.py) are the primary storage of functional logic for the project. No logic within these scripts may be altered or removed, even if it appears unnecessary, without explicit approval from the project engineer. All logic must remain available to support current and future functionality.
Read All Documents Before Changes: All governing documents (coding_conventions.md, requirements.md, script_relationships.md) and configuration files (paths.txt, paths.example.txt) must be fully reviewed before making any changes to identify existing content, ensure compliance, and avoid conflicts or deletions.
Report Conflicts: If a conflict is found between documents, within a document, or in script logic, no changes may be made. The conflict must be reported to the project engineer for resolution.

Functional Requirements
1. Metadata Fetching

Script: Season_Episode_builder.py
Purpose: Fetch TV series metadata from multiple providers and generate a consolidated JSON file.
Inputs:
Command-line argument: --series (e.g., Ax Men).
Configuration file: config/paths.txt with [meta_providers] and [series] sections.


Outputs:
JSON file: data//.json (e.g., data/ax_men/Ax Men.json).
Temporary files: tmp/.json (e.g., tmp/tvmaze.json) per enabled provider.


Behavior:
Read enabled providers from paths.txt’s [meta_providers] (e.g., tvmaze=enabled) in order (top to bottom), where order defines priority (tvmaze highest, rotten_tomatoes lowest).
Call each provider’s get_metadata function to fetch metadata.
Merge provider data into a single JSON with series_name, seasons, and episode details (titles, overview, ids, air_date), preserving raw provider data and respecting provider priority for downstream use (e.g., episode naming in series_folder_crawler.py, file_organizer.py).
Delete tmp/.json before writing to ensure fresh data.


JSON Output Format (for Season_Episode_builder.py):
Structure:{
  "series_name": "Ax Men",
  "seasons": [
    {
      "season_number": 1,
      "episodes": [
        {
          "episode_number": 1,
          "titles": {
            "tvmaze": "Episode Title",
            "tmdb": "Title",
            "trakt": "Trakt Title",
            "rotten_tomatoes": "RT Title"
          },
          "overview": {
            "tvmaze": "Description",
            "tmdb": "Summary",
            "trakt": "Trakt Overview",
            "rotten_tomatoes": "RT Overview"
          },
          "ids": {
            "tvmaze": 123,
            "tmdb": 456,
            "trakt": 789,
            "rotten_tomatoes": "rt_123"
          },
          "air_date": {
            "tvmaze": "2023-01-01",
            "tmdb": "2023-01-01",
            "trakt": "2023-01-01",
            "rotten_tomatoes": "2023-01-01"
          }
        }
      ]
    }
  ]
}


Contains raw provider data (e.g., original titles, overviews) as provided by each provider, listed in [meta_providers] order.
Fields like titles, overview, ids, air_date are dictionaries mapping provider names to their values.
Additional fields (e.g., subtitle) may be included based on provider data.
Priority order (tvmaze first) is preserved for downstream scripts (series_folder_crawler.py, file_organizer.py) to select episode names (e.g., series_name_SxxEyy_episode-name).
Normalization of names for matching is handled by series_folder_crawler.py, not in this JSON.



2. File Organization

Script: file_organizer.py
Purpose: Organize media files into a structured directory based on metadata.
Inputs:
Series JSON: data//.json.
Configuration: paths.txt with [series] (e.g., series_path_1), OPERATION_MODE, CREATE_NFO.


Outputs:
Organized files in series_path_X//Season / - SE_.ext, using episode names from highest-priority provider (e.g., tvmaze).
Optional .nfo files if CREATE_NFO=true.


Behavior:
Read series JSON and [series] section to map episode files to paths.
Move or copy files based on OPERATION_MODE (move or copy).
Generate .nfo files with metadata if enabled, respecting [meta_providers] priority.



3. Kodi Database Export

Script: kodi_db_exporter.py
Purpose: Export metadata to Kodi-compatible database format.
Inputs:
Series JSON: data//.json.
Configuration: paths.txt with USE_KODI.


Outputs:
Database entries in Kodi’s MySQL or SQLite database.


Behavior:
If USE_KODI=true, export episode metadata to Kodi database.
Map JSON fields to Kodi schema (e.g., titles, air_date), prioritizing higher-priority providers.



Technical Requirements
1. Configuration File (paths.txt)

Location: config/paths.txt
Sections:
[general]:
JSON_FOLDER: Output directory for JSON files (e.g., data).
TEMP_FOLDER: Directory for temporary files (e.g., tmp).
LOG_PATH: Directory for logs (e.g., logs).
USE_KODI: Enable Kodi export (true or false).
USE_NEXTPVR: Enable NextPVR integration (true or false).
OPERATION_MODE: File operation mode (move or copy).
CREATE_NFO: Generate .nfo files (true or false).


[series]:
Format: series_name_X = , series_path_X =  (e.g., series_name_1 = The A-Team, series_path_1 = D:/NEXT PVR/RecordingDirectory/The A-Team).
Maps series names to their file paths for series_folder_crawler.py and file_organizer.py.


[meta_providers]:
Format: =enabled (e.g., tvmaze=enabled).
Providers: tvmaze, tmdb, trakt, rotten_tomatoes (in priority order).
Unique names for each provider, representing distinct metadata sources.


Provider-specific sections (e.g., [tvmaze], [rotten_tomatoes]):
Settings like API_KEY for API-based providers or SCRAPE_DELAY for scrapers.




Example:[general]
JSON_FOLDER=data
TEMP_FOLDER=tmp
LOG_PATH=logs
USE_KODI=true
USE_NEXTPVR=true
OPERATION_MODE=move
CREATE_NFO=true

[series]
series_name_1 = The A-Team
series_path_1 = D:/NEXT PVR/RecordingDirectory/The A-Team
series_name_2 = Ax Men
series_path_2 = D:/NEXT PVR/RecordingDirectory/Ax Men

[meta_providers]
tvmaze=enabled
tmdb=enabled
trakt=enabled
rotten_tomatoes=enabled

[tvmaze]
API_KEY=your_tvmaze_api_key

[rotten_tomatoes]
SCRAPE_DELAY=0.5



2. Provider Modules

Location: scripts/providers/
Naming: .py (e.g., tvmaze.py).
Function: Export get_metadata(series_name: str, config: ConfigParser) -> None.
Output: Write metadata to tmp/.json with raw provider data.

3. Logging (Season_Episode_builder.py)

Script actions: logs/<series_slug>/<series_slug>_builder.log (e.g., logs/ax_men/ax_men_builder.log).
Provider actions: logs/<series_slug>/<series_slug>_provider.log (e.g., logs/ax_men/ax_men_provider.log).
Both logs reside in logs/<series_slug>/ and are written in append mode.
Providers log through Season_Episode_builder.py’s logging mechanism.
These requirements apply only to Season_Episode_builder.py and its provider scripts (tvmaze.py, tmdb.py, trakt.py, rotten_tomatoes.py).
Note: Logging for downstream scripts (file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py) will be defined in future updates. This note will be removed when those directives are complete.


References

plans/coding_conventions.md: Coding practices and provider conventions.
plans/script_relationships.md: Script interactions and dependencies.
config/paths.example.txt: Configuration template.

Provider Precedence

Providers are listed in config/paths.txt under [meta_providers] (e.g., tvmaze, tmdb, trakt, rotten_tomatoes).
The order defines their precedence for downstream processes (e.g., crawler, file organizer), where higher-priority providers (e.g., tvmaze) are preferred for season/episode naming and overview selection.
All providers’ metadata is included in data/<series_slug>/<series_name>.json for each field (titles, overviews, ids, air_date), with no data discarded during merging.
The order of provider keys in data/<series_slug>/<series_name>.json (e.g., titles: { "tvmaze": "...", "tmdb": "..." }) matches the order in [meta_providers] to ensure downstream scripts recognize the priority of providers.

- **Detailed Inline Documentation**: 

All scripts (Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, providers/<name>.py) must include detailed inline comments documenting each significant step, including but not limited to API calls, file reads/writes, data transformations, error handling, and interactions with other scripts or configuration files. Comments must clearly describe the purpose of each code block, inputs, outputs, and dependencies to ensure traceability and clarity for debugging and maintenance. This requirement prioritizes inline comments over external documentation, though additional logging may be mandated for troubleshooting if needed.
