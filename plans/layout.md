Repository Layout
This document provides links to all key documents in the mike-buhtig/media_organizer_dev repository (dev-v1.0.10 branch) for easy access.
Plans

requirements.md: Project requirements, including governance, functional, and technical rules.
coding_conventions.md: Coding standards, e.g., no hard-coding, changelog format.
script_relationships.md: Script interactions and dependencies.

Config

paths.txt: Configuration settings for scripts.
paths.example.txt: Template for paths.txt.

Notes

Add other documents (e.g., scripts, logs) as needed.
All URLs are for the dev-v1.0.10 branch.


Repository Structure
The Media Organizer project uses the following folder structure to organize scripts, data, logs, and configurations:

config/: Configuration files.
paths.txt: Active configuration with API keys and settings.
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



base dev URL: https://github.com/mike-buhtig/media_organizer_dev

plans url: https://github.com/mike-buhtig/media_organizer_dev/tree/dev-v1.0.10/plans

requirements.md URL: https://github.com/mike-buhtig/media_organizer_dev/blob/dev-v1.0.10/plans/requirements.md

Layout.md URL:  URL: https://github.com/mike-buhtig/media_organizer_dev/blob/dev-v1.0.10/plans/layout.md
