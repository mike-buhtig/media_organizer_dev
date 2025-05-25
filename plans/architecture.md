			#### architecture.md 
### kodi_watched_extractor.py

## Purpose: 
To extract watched status for TV show episodes from the Kodi database.

## Inputs:
config/paths.txt (for Kodi IP and potential network share mappings).
data/<series_slug>_Processed.json (containing local file paths).

## Outputs:
data/<series_slug>_kodi_watched.json (mapping local file paths to watched status and last played time).
Integration: Explain how this script fits into the workflow between series_folder_crawler.py and file_organizer.py. It will run after the crawler and before the organizer to provide watched status information.