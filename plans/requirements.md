Media Organizer Requirements
Overview of Actions

Pull Kodi Database Data

Extract: Watched status, source (addon: season/episode name, e.g., The.A-Team.S01E10.One.More.Time or The_A-Team_S01E10_One_More_Time; file: full path, e.g., D:/NEXT PVR/.../The A-Team_20250303_18411933.ts).
Scope: All episodes/movies in current and previous Kodi databases (due to upgrades/repurposing).
Output: JSON (data/kodi_data.json) with series, season, episode, path, watched status, source (format to be defined later).
Details: Support Android (ADB for database access or commands) and non-Android (direct SQLite); merge data from multiple databases to capture all watched episodes/movies.


Process NextPVR Recording Paths

Scan: TV series/movie folders from paths.txt (e.g., series_path_1=D:/NEXT PVR/RecordingDirectory/The A-Team).
Input: Series name (e.g., The A-Team) from command-line argument to target specific series.
Collect: Basenames, .xml files; extract <subtitle> (episode title), <Title> (series name) for TV series.
Group: .xml and .ts files by subtitle.
Handle Broken Files: Mark files with -0, -0-0 (e.g., The A-Team_20250303_18411933-0.ts) as broken; note interruption count (e.g., basename-0-0 indicates two interruptions).
File Size: Record file size from filesystem to identify the largest unbroken .ts file for moving.
Output: JSON (data/the_a_team/The_A-Team_Processed.json) with grouped files, broken status, sizes.


Fetch Metadata from Providers

Fetch: TV series metadata from providers (TVMaze, TMDb, Trakt, Rotten Tomatoes).
Prioritize: Order defined in paths.txt [meta_providers] section (e.g., providerc_tvmaze=enabled first, providerf_tmdb=enabled second).
Store: Original titles, normalized titles, normalized descriptions, IDs per provider, using keys like tvmazec, tvmazef in output JSON.
Output:
Temporary: tmp/providerf_<name>.json for function-based providers (e.g., tmp/providerf_tvmaze.json); tmp/provider_<name>.json for class-based providers (e.g., tmp/provider_tmdb.json).
Final: data/the_a_team/The_A-Team.json with merged metadata, grouping provider data under title, normalized_title, overview, id.


Details: Skip titles that are empty ("") or contain “episode”; select air_date from most common or first provider in paths.txt; normalize titles for matching, preserve original titles for .nfo and .xml.


Match Files to Metadata

Match: .xml subtitles (e.g., one more time...) to provider normalized titles (e.g., one more time).
Preserve: Original and normalized titles, provider order, descriptions.
Integrate: Kodi watched status from kodi_data.json, matching by path (e.g., The A-Team_20250303_18411933.ts) or addon name (e.g., The.A-Team.S01E10.One.More.Time).
Output: Updated data/the_a_team/The_A-Team_Processed.json with matches, provider data, watched status, file details (path, size, broken status, .xml metadata).
Details: Include all .xml metadata (e.g., <subtitle>, <description>) for .nfo substitution; use original titles for .nfo.


Organize Files

Create: .nfo files (default) in industry-standard structure (e.g., Series/The A-Team/Season 01/The A-Team - S01E10 - One More Time.nfo).
Content: Watched status, metadata from first provider in paths.txt (original title, description), .xml metadata (substituted).
Future: Integrate Trakt watched data from trakt_watched.json.


Move (Optional): Move .ts, .xml, comskip (.edl) files to Series/The A-Team/Season XX/ with --move flag.
Naming: series_name - SxxEyy - episode_name.ts or series.name.sxxeyy.episode.name.ts, using first provider’s original title.
Select: Largest unbroken .ts file.
Delete: Broken files (e.g., -0, -0-0) after confirmation.


Output: New .xml files with provider metadata substituted (e.g., original title, description from TVMaze).
Details: Support addon-watched names; create series/season subfolders (e.g., Series/The A-Team/Season 01).


Update NextPVR Database

Update: File paths in NextPVR database (e.g., npvr.db) to reflect new locations.
Remove: Moved/deleted files (e.g., broken files).
Track: Recorded episodes (compare The_A-Team_Processed.json with The_A-Team.json).
Manage: Disable “record series” flag; set “record specific episodes” for unrecorded episodes (stored in data/the_a_team/The_A-Team_Not_Recorded.json).
Output: data/the_a_team/The_A-Team_Not_Recorded.json with unrecorded episodes for EPG scheduling.


Generate Comskip Files

Create: Comskip files (.edl) for episodes, if not handled by Streamlink (e.g., for PlutoTV).
Output: Same basename as moved .ts file (e.g., The A-Team - S01E10 - One More Time.edl).



JSON Standards

Types:

Series_Name.json: Builder output with merged provider metadata (series, seasons, episodes, provider-specific titles, normalized titles, descriptions, IDs).
Series_Name_Processed.json: Crawler output with matched episodes, file details, watched status, .xml metadata.
providerf_<name>.json or provider_<name>.json: Temporary provider data (e.g., tmp/providerf_tvmaze.json, tmp/provider_tmdb.json).
kodi_data.json: Kodi database data (format to be defined later).
trakt_watched.json (Future): Trakt watched status for .nfo integration.
Series_Name_Not_Recorded.json: Unrecorded episodes for NextPVR scheduling.


Fields for Series_Name.json (Builder Output):
{
  "series_name": "The A-Team",
  "seasons": [
    {
      "season_number": 1,
      "episodes": [
        {
          "episode_number": 10,
          "air_date": "1983-04-12",
          "title": {
            "tvmazec": "One More Time",
            "tvmazef": "One More Time",
            "tmdbf": "One More Time!",
            "traktf": "One More Time",
            "rotten_tomatoesf": "One More Time"
          },
          "normalized_title": {
            "tvmazec": "one more time",
            "tvmazef": "one more time",
            "tmdbf": "one more time",
            "traktf": "one more time",
            "rotten_tomatoesf": "one more time"
          },
          "overview": {
            "tvmazec": "guerrilla terrorists capture an army general...",
            "tvmazef": "guerrilla terrorists capture an army general...",
            "tmdbf": "a general is captured...",
            "traktf": "a general is captured...",
            "rotten_tomatoesf": null
          },
          "id": {
            "tvmazec": 12345,
            "tvmazef": 12345,
            "tmdbf": 67890,
            "traktf": 54321,
            "rotten_tomatoesf": null
          }
        }
      ]
    },
    {
      "season_number": 0,
      "episodes": [...]
    }
  ]
}


series_name: Series title (e.g., The A-Team).
seasons: Array of seasons.
season_number: Integer (0 for specials).
episodes: Array of episodes.
episode_number: Integer.
air_date: ISO 8601 or provider’s format, chosen from the most common or first provider in paths.txt.
title: Object with provider keys (e.g., tvmazec, tvmazef) and original episode titles.
normalized_title: Object with provider keys and normalized titles (lowercase, punctuation removed).
overview: Object with provider keys and normalized episode descriptions (null if missing).
id: Object with provider keys and episode IDs (null if missing).


Fields for providerf_<name>.json or provider_<name>.json (Provider Output):
{
  "series_name": "The A-Team",
  "seasons": {
    "1": [
      {
        "episode_number": 10,
        "air_date": "1983-04-12",
        "title": "One More Time",
        "normalized_title": "one more time",
        "overview": "guerrilla terrorists capture an army general...",
        "id": 12345
      }
    ],
    "0": [...]
  }
}


series_name: Series title.
seasons: Object with season numbers as keys, arrays of episodes as values.
episode_number, air_date, title, normalized_title, overview, id: Provider-specific data.
Note: Class-based providers (e.g., tmdbc_provider.py) may write to tmp/provider_<name>.json (e.g., tmp/provider_tmdb.json).


Fields for Series_Name_Processed.json (Crawler Output):
{
  "series_name": "The A-Team",
  "seasons": [
    {
      "season_number": 1,
      "episodes": [
        {
          "episode_number": 10,
          "air_date": "1983-04-12",
          "providers": [
            {
              "name": "tvmazec",
              "title": "One More Time",
              "normalized_title": "one more time",
              "description": "guerrilla terrorists capture an army general...",
              "id": 12345
            },
            {
              "name": "tmdbf",
              "title": "One More Time!",
              "normalized_title": "one more time",
              "description": "a general is captured...",
              "id": 67890
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
    }
  ]
}


Uses providers array to include files, xml_metadata, watched_status, standard_name.
Note: Format to be revisited for alignment with Series_Name.json.



Notes

JSON Standards: Defined compact format for Series_Name.json with title and normalized_title, aligned providerf_<name>.json and provider_<name>.json, and detailed Series_Name_Processed.json (pending update).
Modularization: Use json_utils.py for JSON handling, log_utils.py for logging; plan to centralize JSON formatting in json_utils.py.
Kodi Data: Support multiple databases, addon/file sources.
NextPVR Processing: Include file size, broken file details.
Output: .xml substitution, .nfo with original titles from first provider (future).
New JSONs: kodi_data.json, trakt_watched.json, Series_Name_Not_Recorded.json.
Action:
Commit plans/requirements.md to https://github.com/mike-buhtig/media_organizer after feedback.
Document json_utils.py after receiving the script.
Update tmdbc_provider.py and Season_Episode_builder.py to match new JSON format, plan to refactor formatting into json_utils.py.


Question: Approve requirements.md? Any changes before committing?

