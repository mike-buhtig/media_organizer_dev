# To-Do List for Media Organizer Project

This document tracks planned improvements and tasks for the media_organizer_dev project to ensure alignment with governing documents (`requirements.md`, `coding_conventions.md`, `script_relationships.md`).

## Tasks

1. **Graceful Recovery for Provider Failures in Season_Episode_builder.py**
   - **Description**: Update `Season_Episode_builder.py` to continue processing and write `data/<series_slug>/<series_name>.json` even if a single provider fails (e.g., import error, API failure).
   - **Priority**: Medium
   - **Status**: Not started
   - **Notes**:
     - Currently, provider failures are logged and skipped, but the script completes. Ensure robustness by validating output JSON integrity.
     - Requires testing with simulated provider failures.

2. **Review and Fix rotten_tomatoes.py**
   - **Description**: Analyze the current `rotten_tomatoes.py` logic, compare with an older working version, and either restore or update to resolve issues (e.g., "No series found for Ax Men").
   - **Priority**: Low (paused until `trakt.py` and `Season_Episode_builder.py` are verified)
   - **Status**: Not started
   - **Notes**:
     - Current version fails due to site structure or scraping issues.
     - Older version may have compatible logic to restore.
     - Requires Chromedriver compatibility check (e.g., version 136.0.7103.92).

3. **Fix Trakt JSON Format in Season_Episode_builder.py Merge**
   - **Description**: Adjust `trakt.py` JSON output or `Season_Episode_builder.py` merge logic to include Trakt data in `data/<series_slug>/<series_name>.json` (currently `"trakt": null` for most fields).
   - **Priority**: High
   - **Status**: Not started
   - **Notes**:
     - Mismatch between `trakt.py`’s JSON (`"series_name"`, list-based `"seasons"`) and builder’s expected format (nested `titles`, `overviews`, `ids`).
     - Requires minimal changes to `trakt.py` to preserve logic.

4. **kodi_watched_extractor.py:**
    - Create the `tmp/kodi_db` folder if it doesn't exist.
    - Check for and delete existing Kodi database files in `tmp/kodi_db` before pulling.
    - Pull the Kodi database file(s) to the `tmp/kodi_db` folder.
    - Modify the database query to retrieve watched status and file paths.
    - Load the `_processed.json` file to map file paths to episode identifiers and metadata.
    - Implement logic to mark an episode as watched if any of its associated file paths in `_processed.json` are marked as watched in Kodi.
    - Include the latest `lastPlayed` time for a watched episode.
    - Include relevant episode metadata (title, season, episode number) from `_processed.json` in the `_kodi_watched.json` output.
    - Save the episode-level watched status and metadata to `data/<series_slug>_kodi_watched.json`.

5. ** Fix rotten_tomatoes2.py scraper **
   - **Notes**
     - the script fails to find "The A-Team" series, probably because if mishandling of the hyphen in normalization when creating the <series_slug>
## Governance
- All tasks must comply with `requirements.md`:
  - Use `logging.getLogger('Season_Episode_builder')` for logging.
  - Include detailed inline comments.
  - Preserve changelog format: `# <script_name> vX.Y.Z`, entries `# [X.Y.Z] - YYYY-MM-DD: <description>`.
  - Log script version at start of each run.
- Changes must be verified with test runs (`python scripts\Season_Episode_builder.py --series "Ax Men"`) before committing.

## Future Enhancements: 
- Extract MPA rating (e.g., “TV-PG”) and genre (e.g., “Reality/Documentary/Adventure”) from the series page card if the project succeeds.
- Create a way to update trakt, and to gather trakt data to mark things watched that trakt has record of.
- Implement ADB connection and command execution in kodi_watched_extractor.py.
- Implement querying the Kodi database (MyVideos131.db) for watched status and file paths using the constructed SMB path.
- Implement reading the <series_slug>_Processed.json file.
- Implement the logic to match KodiFilePath with the local_path from _processed.json (handling path variations and potential network share mappings).
- Implement the creation of the <series_slug>_kodi_watched.json file.
- (Future Research): Investigate matching watched status for addon content by analyzing filenames in the files table under the addon's idPath.
- (Future Enhancement): Implement the use of the [network_shares] section in paths.txt for more flexible path mapping.