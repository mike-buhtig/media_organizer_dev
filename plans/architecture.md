			#### architecture.md 

### series_folder_crawler.py

## Purpose:
To scan defined directories for TV show series folders and identify video files within them. It normalizes series names and creates a structured JSON output.

## Inputs:
* `config/paths.txt` (for `[series]` and `[library_paths]` definitions).

## Outputs:
* `data/<series_slug>_unprocessed.json` (listing identified video files with their paths).

## Integration:
This is the first script in the workflow. It identifies the raw video files and their locations, which are then processed by subsequent scripts.

### file_normalizer.py

## Purpose:
To take the output of `series_folder_crawler.py` and attempt to normalize the filenames to extract season and episode information.

## Inputs:
* `data/<series_slug>_unprocessed.json`.
* Potentially configuration for custom naming patterns (to be implemented later).

## Outputs:
* `data/<series_slug>_normalized.json` (listing files with extracted season and episode information, and those that could not be normalized).

## Integration:
This script processes the raw file list from the crawler, making the information more structured for matching and organization.

### duplicate_remover.py

## Purpose:
To identify and mark duplicate video files based on filename and potentially file size or other metadata (to be implemented later).

## Inputs:
* `data/<series_slug>_normalized.json`.

## Outputs:
* `data/<series_slug>_duplicates.json` (listing identified duplicate files).
* Updates the `data/<series_slug>_normalized.json` to flag duplicates.

## Integration:
This script runs after normalization to clean up duplicate entries before further processing.

### file_organizer.py

## Purpose:
To organize video files into a structured directory based on the normalized season and episode information. It can also rename files and create NFO metadata files.

## Inputs:
* `config/paths.txt` (for destination library paths).
* `data/<series_slug>_normalized.json` (with duplicate information).
* `data/<series_slug>_kodi_watched.json` (optional, for marking watched status in NFO).

## Outputs:
* Organized video files in the specified library directories.
* Renamed video files (optional).
* `.nfo` metadata files (optional, including watched status if available).

## Integration:
This is the final script in the primary workflow, taking the processed and de-duplicated file list and organizing the actual media files.



### kodi_watched_extractor.py

## Purpose: 
To extract watched status for TV show episodes from the Kodi database.

## Inputs:
config/paths.txt (for Kodi IP and potential network share mappings).
data/<series_slug>_Processed.json (containing local file paths).

## Outputs:
data/<series_slug>_kodi_watched.json (mapping local file paths to watched status and last played time).
Integration: Explain how this script fits into the workflow between series_folder_crawler.py and file_organizer.py. It will run after the crawler and before the organizer to provide watched status information.