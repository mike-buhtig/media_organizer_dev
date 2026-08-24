Media Organizer Project Requirements
This document outlines the functional and technical requirements for the Media Organizer project, which automates the organization and metadata management of TV series media files for integration with Kodi and NextPVR.

Related Documents
This document must be used in conjunction with:

plans/coding_conventions.md: Defines coding practices, including no hard-coding of providers.
plans/to_do.md: Lists future tasks.  These need to be allowed for when coding so that we will be ready when these tasks begin.
config/paths.example.txt: This is a copy of config/paths.txt with the secrets removed.  This reference is to ensure that we maintain the same configurations.  No code is to be written without consulting it.  If code is written that needs configuration, it will be edited and the new config will be added.
plans/script_relationships.md: Describes script interactions and dependencies.Failure to consult all five documents may result in non-compliant code or functionality.

Governance Rules

No Unauthorized Deletions: No sections, settings, or content in this document, other governing documents (coding_conventions.md, script_relationships.md), or configuration files (paths.txt, paths.example.txt) may be removed without explicit approval from the project engineer. All content serves a purpose, and unauthorized deletions may lead to loss of critical functionality or data.
Preserve Script Logic: Scripts (Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, providers/.py) are the primary storage of functional logic for the project. No logic within these scripts may be altered or removed, even if it appears unnecessary, without explicit approval from the project engineer. All logic must remain available to support current and future functionality.
Read All Documents Before Changes: All governing documents (coding_conventions.md, requirements.md, script_relationships.md) and configuration files (paths.txt, paths.example.txt) must be fully reviewed before making any changes to identify existing content, ensure compliance, and avoid conflicts or deletions.
Report Conflicts: If a conflict is found between documents, within a document, or in script logic, no changes may be made. The conflict must be reported to the project engineer for resolution.

Technical Requirements
Repository Structure
The Media Organizer project uses the following folder structure to organize scripts, data, logs, and configurations:

config/: Configuration files.
paths.txt: Active configuration with API keys and settings, as well as paths to series folders, infrmation pertinent to kodi, network shares with ip addresses, and paths to the library where TVseries, and Movie files are to be stored
paths.example.txt: Template for paths.txt without sensitive data.


data/: Output JSON files for series metadata.
data/<series_slug>/<series_name>.json (e.g., data/ax_men/Ax Men.json).


logs/: Log files for script and provider actions.
logs/<series_slug>/<series_slug>_builder.log (e.g., logs/ax_men/ax_men_builder.log).
logs/<series_slug>/<series_slug>_provider.log (e.g., logs/ax_men/ax_men_provider.log).


plans/: Governance and planning documents.
requirements.md: Project requirements (this file).
coding_conventions.md: Coding standards.
script_relationships.md: Script interactions and dependencies.
to_do.md: Future tasks.
layout.md: folder locations and urls to access them


scripts/: Core and provider scripts.
Season_Episode_builder.py: Metadata orchestration.
file_organizer.py: File organization.
series_folder_crawler.py: Folder crawling.
kodi_db_exporter.py: Kodi database export.
providers/:
tvmaze.py, tmdb.py, trakt.py, rotten_tomatoes.py: Provider-specific metadata fetching.




tmp/: Temporary JSON files from providers.
tmp/<provider>.json (e.g., tmp/tvmaze.json).



All scripts and processes must adhere to this structure, as defined in config/paths.txt (JSON_FOLDER, TEMP_FOLDER, LOG_PATH).




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
Read enabled providers from paths.txt's [meta_providers] in authoritative top-to-bottom priority order: TMDb first, Trakt second, TVMaze third, Rotten Tomatoes fourth, and Rotten Tomatoes 2 fifth.
Call each provider’s get_metadata function to fetch metadata.
Merge provider data into a single JSON with series_name, seasons, and episode details (titles, overviews, ids, air_date), preserving raw provider data and respecting provider priority for downstream use (e.g., episode naming in series_folder_crawler.py, file_organizer.py).
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
            "tmdb": "Title",
            "trakt": "Trakt Title",
            "tvmaze": "Episode Title",
            "rotten_tomatoes": "RT Title",
            "rotten_tomatoes2": "RT2 Title"
          },
          "overviews": {
            "tmdb": "Summary",
            "trakt": "Trakt Overview",
            "tvmaze": "Description",
            "rotten_tomatoes": "RT Overview",
            "rotten_tomatoes2": "RT2 Overview"
          },
          "ids": {
            "tmdb": 456,
            "trakt": 789,
            "tvmaze": 123,
            "rotten_tomatoes": "rt_123",
            "rotten_tomatoes2": "rt2_123"
          },
          "air_date": {
            "tmdb": "2023-01-01",
            "trakt": "2023-01-01",
            "tvmaze": "2023-01-01",
            "rotten_tomatoes": "2023-01-01",
            "rotten_tomatoes2": "2023-01-01"
          }
        }
      ]
    }
  ]
}


Contains raw provider data (e.g., original titles, overviews) as provided by each provider, listed in [meta_providers] order.
Fields like titles, overviews, ids, air_date are dictionaries mapping provider names to their values.
Additional fields (e.g., subtitle) may be included based on provider data.
Priority order (TMDb first, Trakt second, TVMaze third, Rotten Tomatoes fourth, Rotten Tomatoes 2 fifth) is preserved for downstream scripts (series_folder_crawler.py, file_organizer.py) to select episode names (e.g., series_name_SxxEyy_episode-name).
Normalization of names for matching is handled by series_folder_crawler.py, not in this JSON.



2. File Organization

Script: file_organizer.py
Purpose: Organize media files into a structured directory based on metadata.
Inputs:
Series JSON: data//.json.
Configuration: paths.txt with [series] (e.g., series_path_1), OPERATION_MODE, CREATE_NFO.


Outputs:
Source recordings are read from the exact series_path_X configured for the series. Organized files are written beneath TV_LIBRARY_PATH/<series_name>/Season <N>/<series_name> - S<NN>E<NN>_<episode_name>.ext, using episode names from the highest-priority enabled provider (currently TMDb). Persistent organizer metadata is stored beneath TV_LIBRARY_PATH/<series_name>/.media_organizer/.
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
Providers in authoritative priority order: tmdb, trakt, tvmaze, rotten_tomatoes, rotten_tomatoes2.
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
tmdb=enabled
trakt=enabled
tvmaze=enabled
rotten_tomatoes=enabled
rotten_tomatoes2=enabled

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

Providers are listed in config/paths.txt under [meta_providers] in authoritative top-to-bottom order: tmdb, trakt, tvmaze, rotten_tomatoes, rotten_tomatoes2.
The order defines their precedence for downstream processes (e.g., crawler, file organizer): TMDb first, Trakt second, TVMaze third, Rotten Tomatoes fourth, and Rotten Tomatoes 2 fifth.
All providers’ metadata is included in data/<series_slug>/<series_name>.json for each field (titles, overviews, ids, air_date), with no data discarded during merging.
The order of provider keys in data/<series_slug>/<series_name>.json (e.g., titles: { "tmdb": "...", "trakt": "...", "tvmaze": "..." }) matches the order in [meta_providers] to ensure downstream scripts recognize the priority of providers.

- **Detailed Inline Documentation**: 

All scripts (Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, providers/<name>.py) must include detailed inline comments documenting each significant step, including but not limited to API calls, file reads/writes, data transformations, error handling, and interactions with other scripts or configuration files. Comments must clearly describe the purpose of each code block, inputs, outputs, and dependencies to ensure traceability and clarity for debugging and maintenance. This requirement prioritizes inline comments over external documentation, though additional logging may be mandated for troubleshooting if needed.

## Core Scripts: Season_Episode_builder.py
- **Purpose**: Orchestrates metadata fetching from providers, merges data, and writes output JSON for series organization.
- **Input**:
  - Command-line argument `--series` (e.g., `"Ax Men"`).
  - Configuration from `config/paths.txt` with `[general]` (TEMP_FOLDER, LOG_PATH, JSON_FOLDER) and `[meta_providers]` (enabled providers).
- **Output**:
  - JSON file at `data/<series_slug>/<series_name>.json` with merged metadata from providers.
  - Logs to `logs/<series_slug>/<series_slug>_builder.log` (script execution) and `logs/<series_slug>/<series_slug>_provider.log` (provider execution).
- **Dependencies**:
  - Python libraries: `requests` (pip install requests).
  - Provider scripts in `scripts/providers/` (e.g., `tvmaze.py`, `tmdb.py`, `trakt.py`).
- **Behavior**:
  - Parses series name from command-line argument.
  - Loads configuration and initializes logging.
  - Dynamically imports enabled providers and calls their `get_metadata`.
  - Merges provider JSON outputs into a single file.
  - Logs script version at start, provider import attempts, file existence checks, and detailed errors (including tracebacks).
- **Integration**:
  - Calls provider scripts via `importlib.import_module("providers.<name>")`.
  - Output JSON used by other scripts (e.g., `file_organizer.py`).
- **Governance**:
  - Must use `logging.getLogger('Season_Episode_builder')` for logging.
  - Must include detailed inline comments for all significant steps.
  - Must preserve inline comments, notes, and change logs.
  - **Changelog Format**:
    - First line: `# Season_Episode_builder.py vX.Y.Z`.
    - Entries: `# [X.Y.Z] - YYYY-MM-DD: <description>`, appended.
  - **Logging**:
    - First log line must include script version (e.g., `[builder] Season_Episode_builder.py v1.0.11 starting`).
    - Logs must include provider import attempts, file existence checks, and tracebacks for errors.

## Provider Scripts: 
- Each provider script must output a JSON file to `tmp/<provider>.json` with the schema defined in `layout.md`. Providers must accept a `--series` argument to specify the series name. Logging must be to stdout using a logger named `Season_Episode_builder.provider`, captured by `Season_Episode_builder.py` into `logs/<series-slug>/<series-slug>_providers.log` with `[provider]` prefixes. Providers must not write directly to log files.

   ## Rotten Tomatoes (Scraper)
- The `rotten_tomatoes.py` script is a web scraper that fetches metadata from Rotten Tomatoes. It must:
- Build URLs dynamically using the `--series` argument (e.g., `https://www.rottentomatoes.com/search?search=<series>`).
- Parse search, series, and episode pages to extract series name, season/episode counts, titles, air dates, and overviews.
- Fetch episode pages for overviews, as they are not available on series or season pages.
- Identify specials from the search page (e.g., titles containing the series name and a colon).
- Output JSON matching the schema in `layout.md`, using `null` for missing fields.

   ## trakt.py
- **Purpose**: Fetches metadata (seasons, episodes, titles, overviews, air dates) from Trakt.tv API for a given series and writes standardized JSON output.
- **Input**:
  - Series name (string, e.g., "Ax Men") passed via `get_metadata(title, config)`.
  - Configuration from `config/paths.txt` with `[general]` (TEMP_FOLDER, LOG_PATH) and `[trakt]` (TRAKT_CLIENT_ID).
- **Output**:
  - JSON file at `tmp/trakt.json` with structure:
    ```json
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
              "air_date": "<YYYY-MM-DD or empty>"
            }
          ]
        }
      ]
    }
    ```
  - Logs to `logs/<series_slug>/<series_slug>_provider.log` with `[trakt]` prefix.
- **Dependencies**:
  - Python libraries: `requests` (pip install requests).
  - Trakt API client ID (valid key in `config['trakt']['TRAKT_CLIENT_ID']`).
  - ADB needs to be installed and accessible in the system's PATH.
  -Python sqlite3 library
- **Behavior**:
  - Searches Trakt API for series by title, retrieves slug.
  - Fetches series summary and seasons with extended episode data.
  - Cleans episode titles (removes quotes, backslashes).
  - Logs missing overviews, cleaned titles, and script version at start.
  - Handles API errors gracefully, logging failures.
- **Integration**:
  - Called by `Season_Episode_builder.py` via `importlib.import_module("providers.trakt")`.
  - JSON output merged into `data/<series_slug>/<series_name>.json`.
- **Governance**:
  - Must use `logging.getLogger('Season_Episode_builder')` for logging, matching `tvmaze.py` and `tmdb.py`.
  - Must preserve inline comments, notes, and change logs.
  - Must minimize changes to working logic, only modifying output format, logging, or filename as required.
  - **Changelog Format**:
    - First line: `# <script_name> vX.Y.Z` (e.g., `# trakt.py v1.0.3`).
    - Entries: `# [X.Y.Z] - YYYY-MM-DD: <description>`, appended to preserve history.
  - **Logging**:
    - First log line of any run must include script version (e.g., `[trakt] trakt.py v1.0.3 starting`), which implies that all scripts must have the ability to include the version when they print
    - All logs must use `[trakt]` prefix for console and file output.
	
	### Logging Flow
- `Season_Episode_builder.py`:
  - `builder_logger` (`Season_Episode_builder.builder`): Writes to `logs/<series_slug>/<series_slug>_builder.log` for version, provider fetch, JSON write.
  - `provider_logger` (`Season_Episode_builder.provider`): Writes to `logs/<series_slug>/<series_slug>_provider.log` for JSON loading, errors, and provider logs.
- Providers (e.g., `rotten_tomatoes.py`):
  - Must log to `Season_Episode_builder.provider`, not custom files (e.g., `logs/builder.log`).
  - Legacy logging (e.g., `log_message`) must be updated to use `provider_logger`.
  
## kodi_watched_extractor.py

  - **Software Dependencies** 
	- ADB (Android Debug Bridge) installed and in system PATH."
  - **Python Libraries
	- Standard Python library sqlite3.
  - **Configuration (config/paths.txt)**
    - [kodi] section (KODI_IP) Include the kodi ip address, and/or path to kodi for the sake of pulling the kodi database.

### `[network_config]` Section

This section defines network-related configurations for servers that host media files accessed by Kodi.

* `<servername>_ip`: The IP address of a network server (e.g., `htpc_ip`, `win10box3_ip`). You can choose a descriptive `servername` prefix.
* `<servername>_shares`: A comma-separated list of share names on the corresponding server that Kodi might access (e.g., `htpc_shares = Recordings, Movies-HTPC, TV-Series`). The `servername` prefix should match the IP address key.

**Example:**

```ini
[network_config]
htpc_ip = 192.168.0.254
htpc_shares = Recordings, Movies-HTPC, TV-Series

win10box3_ip = 192.168.0.123
win10box3_shares = Media, KodiShare
  
	- **Verification Rule**: All assumptions about configuration files (e.g., `paths.txt`), data availability (e.g., API responses), or repository contents (e.g., `coding_conventions.md`) must be verified against source files (`paths.example.txt`, API documentation, repository) before coding. No changes may be based on unverified assumptions.
