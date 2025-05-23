Repository Layout
This document centralizes links to all key documents and scripts in the mike-buhtig/media_organizer_dev repository (dev-v1.0.10 branch) and describes the folder structure for administration and development.
Plans
Governance and planning documents defining project requirements, coding standards, and script interactions.

layout.md: This document, listing all repository files and structure.
requirements.md: Project requirements, including governance, functional, and technical rules.
coding_conventions.md: Coding standards, e.g., no hard-coding, changelog format.
script_relationships.md: Script interactions and dependencies.
to_do.md: Future tasks to prepare for in coding.

Config
Configuration files for script settings and templates.

paths.txt: Active configuration with API keys and settings.
paths.example.txt: Template for paths.txt without sensitive data.

Scripts
Core and provider scripts implementing the Media Organizer functionality.
Core Scripts

Season_Episode_builder.py: Orchestrates metadata fetching and JSON merging.
file_organizer.py: Organizes media files into structured directories.
series_folder_crawler.py: Crawls series folders for file mapping.
kodi_db_exporter.py: Exports metadata to Kodi database.

Provider Scripts

tvmaze.py: Fetches metadata from TVmaze API.
tmdb.py: Fetches metadata from TMDb API.
trakt.py: Fetches metadata from Trakt API.
rotten_tomatoes.py: Scrapes metadata from Rotten Tomatoes.

Repository Structure
The folder structure organizes scripts, data, logs, and configurations, as defined in config/paths.txt (JSON_FOLDER, TEMP_FOLDER, LOG_PATH).

config/: Configuration files.
paths.txt: Active configuration with API keys and settings.
paths.example.txt: Template for paths.txt without sensitive data.


data/: Output JSON files for series metadata.
data/<series_slug>/<series_name>.json (e.g., data/ax_men/Ax Men.json).


logs/: Log files for script and provider actions.
logs/<series_slug>/<series_slug>_builder.log (e.g., logs/ax_men/ax_men_builder.log).
logs/<series_slug>/<series_slug>_provider.log (e.g., logs/ax_men/ax_men_provider.log).


plans/: Governance and planning documents.
requirements.md: Project requirements.
coding_conventions.md: Coding standards.
script_relationships.md: Script interactions and dependencies.
to_do.md: Future tasks.
layout.md: This document.


scripts/: Core and provider scripts.
Season_Episode_builder.py: Metadata orchestration.
file_organizer.py: File organization.
series_folder_crawler.py: Folder crawling.
kodi_db_exporter.py: Kodi database export.
providers/:
tvmaze.py, tmdb.py, trakt.py, rotten_tomatoes.py: Provider-specific metadata fetching.




tmp/: Temporary JSON files from providers.
tmp/<provider>.json (e.g., tmp/tvmaze.json).


## entire repository layout graphic:

.
├── config/
│   └── paths.txt             # Configuration for paths, thresholds, etc.
├── data/
│   └── <series_slug>/        # Example: ax_men
│       ├── Ax Men.json         # Output from Season_Episode_builder.py
│       └── Ax_Men_Processed.json # Output from series_folder_crawler.py
├── docs/
│   ├── architecture.md       # (If it exists) Project architecture overview
│   ├── contributing.md       # (If it exists) Contribution guidelines
│   └── ...                   # Other documentation files
├── logs/
│   └── <series_slug>/        # Example: ax_men
│       └── series_folder_crawler_ax_men.log # Log file for the crawler
├── media_organizer_dev/      # (Potentially if the root is one level higher)
│   ├── config/
│   │   └── paths.txt
│   ├── data/
│   │   └── <series_slug>/
│   │       ├── <series_name>.json
│   │       └── <series_name>_Processed.json
│   ├── docs/
│   │   ├── architecture.md
│   │   ├── contributing.md
│   │   └── ...
│   ├── logs/
│   │   └── <series_slug>/
│   │       └── series_folder_crawler_<series_slug>.log
│   ├── plans/
│   │   ├── coding_conventions.md
│   │   ├── layout.md
│   │   ├── requirements.md
│   │   ├── script_relationships.md
│   │   └── to_do.md
│   ├── scripts/
│   │   ├── file_organizer.py
│   │   ├── rename_files.py       # (If it exists)
│   │   ├── Season_Episode_builder.py
│   │   └── series_folder_crawler.py
│   └── ...                   # Other project files
├── plans/
│   ├── coding_conventions.md
│   ├── layout.md
│   ├── requirements.md
│   ├── script_relationships.md
│   └── to_do.md
├── scripts/
│   ├── file_organizer.py
│   ├── rename_files.py       # (If it exists)
│   ├── Season_Episode_builder.py
│   └── series_folder_crawler.py
└── ...                       # Other top-level files (e.g., README.md)



Notes

All scripts and processes must adhere to the repository structure and governing documents (requirements.md, coding_conventions.md, script_relationships.md).
Additional files (e.g., logs, new scripts) may be added as needed.
All URLs are for the dev-v1.0.10 branch.




base dev URL: https://github.com/mike-buhtig/media_organizer_dev

plans url: https://github.com/mike-buhtig/media_organizer_dev/tree/dev-v1.0.10/plans

requirements.md URL: https://github.com/mike-buhtig/media_organizer_dev/blob/dev-v1.0.10/plans/requirements.md

Layout.md URL:  URL: https://github.com/mike-buhtig/media_organizer_dev/blob/dev-v1.0.10/plans/layout.md
