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

## Governance
- All tasks must comply with `requirements.md`:
  - Use `logging.getLogger('Season_Episode_builder')` for logging.
  - Include detailed inline comments.
  - Preserve changelog format: `# <script_name> vX.Y.Z`, entries `# [X.Y.Z] - YYYY-MM-DD: <description>`.
  - Log script version at start of each run.
- Changes must be verified with test runs (`python scripts\Season_Episode_builder.py --series "Ax Men"`) before committing.

## Future Enhancements: 
- Extract MPA rating (e.g., “TV-PG”) and genre (e.g., “Reality/Documentary/Adventure”) from the series page card if the project succeeds.