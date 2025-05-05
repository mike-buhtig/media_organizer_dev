
# Media Organizer Requirements
## Overview of Actions
1. **Pull Kodi Database Data**
   - Extract: Watched status, source (addon: season/episode name, e.g., `The.A-Team.S01E10.One.More.Time` or `The_A-Team_S01E10_One_More_Time`; file: full path, e.g., `D:/NEXT PVR/.../The A-Team_20250303_18411933.ts`).
   - Scope: All episodes/movies in current and previous Kodi databases (due to upgrades/repurposing).
   - Output: JSON (`data/kodi_data.json`) with series, season, episode, path, watched status, source.
   - Details: Support Android (ADB for database access or commands) and non-Android (direct SQLite); merge data from multiple databases to capture all watched episodes/movies.

2. **Process NextPVR Recording Paths**
   - Scan: TV series/movie folders from `paths.txt` (e.g., `series_path_1=D:/NEXT PVR/RecordingDirectory/The A-Team`).
   - Input: Series name (e.g., `The A-Team`) from command-line argument to target specific series.
   - Collect: Basenames, `.xml` files; extract `<subtitle>` (episode title), `<Title>` (series name) for TV series.
   - Group: `.xml` and `.ts` files by subtitle.
   - Handle Broken Files: Mark files with `-0`, `-0-0` (e.g., `The A-Team_20250303_18411933-0.ts`) as `broken`; note interruption count (e.g., `basename-0-0` indicates two interruptions).
   - File Size: Record file size from filesystem to identify the largest unbroken `.ts` file for moving.
   - Output: JSON (`data/the_a_team/The_A-Team_Processed.json`) with grouped files, broken status, sizes.

3. **Fetch Metadata from Providers**
   - Fetch: TV series/movie metadata from providers (TVMaze, TMDb, Trakt, Rotten Tomatoes, IMDb).
   - Prioritize: Configurable order in `paths.txt` (e.g., `provider_priority_tvmaze=1`, `provider_priority_tmdb=2`).
   - Store: Original titles (e.g., `One More Time`), normalized titles (e.g., `one more time`), descriptions per provider.
   - Output: JSON (`data/the_a_team/The_A-Team.json` for final metadata, `data/the_a_team/metadata_provider.json` for temporary provider data).
   - Details: Skip titles that are empty (`""`) or contain “episode”; use highest-priority provider’s title for naming.

4. **Match Files to Metadata**
   - Match: `.xml` subtitles (e.g., `one more time...`) to provider metadata (e.g., S1E10 `One More Time`).
   - Preserve: Original and normalized titles, provider priorities, descriptions.
   - Integrate: Kodi watched status from `kodi_data.json`, matching by path (e.g., `The A-Team_20250303_18411933.ts`) or addon name (e.g., `The.A-Team.S01E10.One.More.Time`).
   - Output: Updated `data/the_a_team/The_A-Team_Processed.json` with matches, provider data, watched status, file details (path, size, broken status, `.xml` metadata).
   - Details: Include all `.xml` metadata (e.g., `<subtitle>`, `<description>`) for `.nfo` substitution.

5. **Organize Files**
   - Create: `.nfo` files (default) in industry-standard structure (e.g., `Series/The A-Team/Season 01/The A-Team - S01E10 - One More Time.nfo`).
     - Content: Watched status, metadata from highest-priority provider (non-normalized title, description), `.xml` metadata (substituted).
     - Future: Integrate Trakt watched data from `trakt_watched.json`.
   - Move (Optional): Move `.ts`, `.xml`, comskip (`.edl`) files to `Series/The A-Team/Season XX/` with `--move` flag.
     - Naming: `series_name - SxxEyy - episode_name.ts` or `series.name.sxxeyy.episode.name.ts`, using highest-priority provider’s title.
     - Select: Largest unbroken `.ts` file.
     - Delete: Broken files (e.g., `-0`, `-0-0`) after confirmation.
   - Output: New `.xml` files with provider metadata substituted (e.g., title, description from TVMaze).
   - Details: Support addon-watched names; create series/season subfolders (e.g., `Series/The A-Team/Season 01`).

6. **Update NextPVR Database**
   - Update: File paths in NextPVR database (e.g., `npvr.db`) to reflect new locations.
   - Remove: Moved/deleted files (e.g., broken files).
   - Track: Recorded episodes (compare `The_A-Team_Processed.json` with `The_A-Team.json`).
   - Manage: Disable “record series” flag; set “record specific episodes” for unrecorded episodes (stored in `data/the_a_team/The_A-Team_Not_Recorded.json`).
   - Output: `data/the_a_team/The_A-Team_Not_Recorded.json` with unrecorded episodes for EPG scheduling.

7. **Generate Comskip Files**
   - Create: Comskip files (`.edl`) for episodes, if not handled by Streamlink (e.g., for PlutoTV).
   - Output: Same basename as moved `.ts` file (e.g., `The A-Team - S01E10 - One More Time.edl`).

## JSON Standards
- **Types**:
  - `Series_Name.json`: Provider metadata (series, seasons, episodes, titles, descriptions).
  - `Series_Name_Processed.json`: Matched episodes, file details, watched status, `.xml` metadata.
  - `metadata_provider.json`: Temporary provider data (e.g., TVMaze raw response).
  - `kodi_data.json`: Kodi database data (series, season, episode, path, watched status, source).
  - `trakt_watched.json` (Future): Trakt watched status for `.nfo` integration.
  - `Series_Name_Not_Recorded.json`: Unrecorded episodes for NextPVR scheduling.
- **Fields** (for `Series_Name_Processed.json`):
  ```json
  {
    "series_name": "The A-Team",
    "seasons": [
      {
        "season_number": 1,
        "episodes": [
          {
            "episode_number": 10,
            "providers": [
              {
                "name": "tvmaze",
                "priority": 1,
                "title": "One More Time",
                "normalized_title": "one more time",
                "description": "Guerrilla terrorists capture an army general..."
              },
              {
                "name": "tmdb",
                "priority": 2,
                "title": "One More Time!",
                "normalized_title": "one more time",
                "description": "A general is captured..."
              }
            ],
            "files": [
              {
                "path": "D:/NEXT PVR/.../The A-Team_20250303_18411933.ts",
                "size": 1133506708,
                "broken": false
              },
              {
                "path": "D:/NEXT PVR/.../The A-Team_20250303_18411933-0.ts",
                "size": 500000000,
                "broken": true
              }
            ],
            "xml_metadata": {
              "subtitle": "one more time...",
              "description": "guerrilla terrorists capture an army general...",
              "other_tags": {...}
            },
            "watched_status": true,
            "standard_name": "The A-Team - S01E10 - One More Time"
          }
        ]
      },
      {
        "season_number": 0,
        "episodes": [...]
      }
    ]
  }
  
  


- **Additions from Your Notes**:
  - **JSON Standards**: Defined types and fields, emphasizing consistency.
  - **Modularization**: Added `json_utils.py` and `log_utils.py` for JSON/log handling.
  - **Kodi Data**: Detailed multiple databases, addon/file sources.
  - **NextPVR Processing**: Added file size, broken file details.
  - **Output**: Specified `.xml` substitution, `.nfo` with Trakt data.
  - **New JSONs**: `kodi_data.json`, `trakt_watched.json`, `Series_Name_Not_Recorded.json`.
- **Prior Requirements**: Included recorded episode tracking (action 6) and comskip generation (action 7).
- **Action**:
  - Commit `plans/requirements.md` to `https://github.com/mike-buhtig/media_organizer` after your feedback.
  - Map existing scripts (`series_folder_crawler.py`, `file_organizer.py`, etc.) to actions post-confirmation.
  - Address `file_organizer.py` issue after requirements are finalized.
- **Question**: Happy with the updated `requirements.md`? Any additions or changes before committing? Want to map scripts next?

---

### 3. Next Steps
- **Your Input**: You’ll share more notes later, and the logs were for `The A-Team`.
- **Response**: I’ve incorporated your current notes fully. Once you share additional notes, I’ll update `requirements.md` further. For now, we can:
  1. Commit the draft `requirements.md`.
  2. Debug `file_organizer.py` (needs JSON snippet).
  3. Map scripts to actions (e.g., `series_folder_crawler.py` to action 2).
  4. Review next script (`match_unmatched.py`).
- **Action**: Await your feedback on `requirements.md` and JSON snippet for debugging.
- **Question**: Commit `requirements.md` now? Debug `file_organizer.py` or proceed with script mapping/review?

---

### Pause for Your Input
I’ve addressed:
- **File Organizer Issue**: Analyzed logs, identified path/format mismatch, requested JSON/`paths.txt`.
- **Requirements**: Updated `plans/requirements.md` with your notes, JSON/log standards, and prior requirements.
- **Next Steps**: Proposed committing `requirements.md`, debugging, or mapping scripts.

Please respond to one or two:
1. **File Organizer**: Share `The_A-Team_Processed.json` snippet and `JSON_FOLDER` from `paths.txt` to debug?
2. **Requirements**: Approve `requirements.md` for commit? Add changes or more notes?
3. **Next Steps**: Map scripts, review `match_unmatched.py`, or focus on debugging?

Thank you for the detailed notes and logs—your vision is coming together beautifully! I’ll wait for your feedback before proceeding.

paths diagram:

media_organizer/
├── config/
│   ├── paths.txt
│   └── paths.example.txt
├── data/
│   └── the_a_team/
│       ├── The_A-Team_Processed.json
│       └── [The_A-Team.json after successful run]
├── logs/
│   └── the_a_team/
│       ├── season_episode_builder.log
│       ├── file_organizer.log
│       └── ...
├── scripts/
│   ├── __init__.py
│   ├── Season_Episode_builder.py
│   ├── file_organizer.py
│   ├── series_folder_crawler.py
│   ├── kodi_db_exporter.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── tvmaze_provider.py
│   │   ├── tmdb_provider.py
│   │   ├── trakt_provider.py
│   │   ├── rotten_tomatoes_provider.py
│   └── ...
├── plans/
│   └── requirements.md
└── README.md