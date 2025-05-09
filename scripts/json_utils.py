# json_utils.py
# Standardizes JSON output for provider and crawler scripts
#
# Change Log:
# [1.0.0] - 2025-05-03: Initial version with format_builder_json, format_crawler_json, and clean_temp_file
# [1.0.1] - 2025-05-04: Added template-based formatting for flexible JSON structures
# [1.0.2] - 2025-05-06: Added normalize_title for consistent title normalization

import json  # For reading/writing JSON files
import os  # For file operations (e.g., checking/deleting temp files)
from typing import Dict, List, Any  # For type hints in function signatures
import re  # For regular expression-based title normalization

def clean_temp_file(temp_file: str, provider_name: str) -> None:
    """
    Delete existing temp file to prevent stale data.
    
    Args:
        temp_file: Path to the temp file (e.g., 'tmp/providerf_tvmaze.json').
        provider_name: Name of the provider (e.g., 'tvmaze') for logging.
    
    Behavior:
        - Checks if temp_file exists using os.path.exists.
        - Deletes the file using os.remove if it exists.
        - Logs deletion for debugging.
    """
    if os.path.exists(temp_file):
        os.remove(temp_file)
        print(f"[{provider_name}] Deleted existing temp file: {temp_file}")

def normalize_title(title: str) -> str:
    """
    Normalize a title for matching purposes.
    
    Args:
        title: Raw title (e.g., "One More Time!").
    
    Returns:
        Normalized title (e.g., "one more time").
    
    Behavior:
        - Converts to lowercase.
        - Removes punctuation and special characters.
        - Strips leading/trailing whitespace.
        - Used for 'normalized_title' in provider JSON and Series_Name.json.
    """
    if not title:
        return ""
    # Remove punctuation and special characters, keep letters, numbers, spaces
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    # Replace multiple spaces with single space and strip
    return " ".join(normalized.split())

def format_provider_json(
    series_name: str,
    seasons: Dict[str, List[Dict[str, Any]]],
    provider_name: str,
    temp_file: str
) -> None:
    """
    Format provider JSON for temporary files (e.g., tmp/providerc_tmdb.json).
    
    Args:
        series_name: Series title (e.g., "The A-Team").
        seasons: Dictionary with season numbers as keys and episode lists as values.
        provider_name: Provider name (e.g., 'tmdb') for JSON keys.
        temp_file: Output file path (e.g., 'tmp/providerc_tmdb.json').
    
    Behavior:
        - Structures provider-specific JSON with title, normalized_title, overview, id.
        - Uses normalize_title to generate normalized_title.
        - Writes JSON to temp_file with proper encoding.
        - Logs success or errors.
        - Called by provider scripts (e.g., tmdbc_provider.py).
    
    Example Output (tmp/providerc_tmdb.json):
    {
      "series_name": "The A-Team",
      "seasons": {
        "1": [
          {
            "episode_number": 10,
            "air_date": "1983-04-12",
            "title": "One More Time",
            "normalized_title": "one more time",
            "overview": "A general is captured...",
            "id": "67890"
          }
        ]
      }
    }
    """
    data = {
        "series_name": series_name,
        "seasons": {
            str(season_num): [
                {
                    "episode_number": ep.get("number", 0),
                    "air_date": ep.get("air_date", ""),
                    "title": ep.get("title", ""),
                    "normalized_title": normalize_title(ep.get("title", "")),
                    "overview": ep.get("overview", ""),
                    "id": ep.get("id", None)
                } for ep in episodes
            ] for season_num, episodes in seasons.items()
        }
    }

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[{provider_name}] Wrote metadata to {temp_file}")
    except Exception as e:
        print(f"[{provider_name}] Error writing {temp_file}: {e}")

def format_builder_json(
    series_name: str,
    seasons: List[Dict[str, Any]],
    temp_file: str,
    provider_name: str = None,
    template: str = "builder"
) -> None:
    """
    Format JSON for builder (Series_Name.json) or provider temp files.
    
    Args:
        series_name: Series title (e.g., "The A-Team").
        seasons: List of seasons with episodes and metadata.
        temp_file: Output file path (e.g., 'data/the_a_team/The_A-Team.json').
        provider_name: Provider name for provider JSON (e.g., 'tvmaze').
        template: 'builder' for Series_Name.json, 'provider' for provider JSON.
    
    Behavior:
        - For template='builder': Creates compact Series_Name.json with merged provider data.
        - For template='provider': Creates provider-specific JSON (not currently used).
        - Writes JSON to temp_file with proper encoding.
        - Logs success or errors.
        - Called by Season_Episode_builder.py (for builder) or potentially providers.
    
    Example Output (Series_Name.json, template='builder'):
    {
      "series_name": "The A-Team",
      "seasons": [
        {
          "season_number": 1,
          "episodes": [
            {
              "episode_number": 10,
              "air_date": "1983-04-12",
              "titles": {
                "tvmazec": "One More Time",
                "tmdbf": "One More Time!"
              },
              "overviews": {
                "tvmazec": "guerrilla terrorists...",
                "tmdbf": "a general is captured..."
              },
              "ids": {
                "tvmazec": 12345,
                "tmdbf": 67890
              }
            }
          ]
        }
      ]
    }
    """
    if template == "builder":
        data = {
            "series_name": series_name,
            "overview": "",  # Add series-level metadata as needed
            "first_air_date": "",
            "seasons": [
                {
                    "season_number": season.get("season_number", 0),
                    "episodes": [
                        {
                            "episode_number": ep.get("episode_number", 0),
                            "air_date": ep.get("air_date", ""),
                            "titles": ep.get("titles", {}),
                            "overviews": ep.get("overviews", {}),
                            "ids": ep.get("ids", {})
                        } for ep in season.get("episodes", [])
                    ]
                } for season in seasons
            ]
        }
    elif template == "provider" and provider_name:
        data = {
            "series_name": series_name,
            "seasons": {
                str(season.get("season_number", 0)): [
                    {
                        "episode_number": ep.get("episode_number", 0),
                        "air_date": ep.get("air_date", ""),
                        "titles": {provider_name: ep.get("title", "")},
                        "overviews": {provider_name: ep.get("overview", "")},
                        "ids": {provider_name: ep.get("id", None)}
                    } for ep in season.get("episodes", [])
                ] for season in seasons
            }
        }
    else:
        raise ValueError("Invalid template or missing provider_name")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[{provider_name or 'builder'}] Wrote metadata to {temp_file}")
    except Exception as e:
        print(f"[{provider_name or 'builder'}] Error writing {temp_file}: {e}")

def format_crawler_json(
    series_name: str,
    seasons: List[Dict[str, Any]],
    temp_file: str
) -> None:
    """
    Format JSON for crawler output (Series_Name_Processed.json).
    
    Args:
        series_name: Series title (e.g., "The A-Team").
        seasons: List of seasons with episodes and file metadata.
        temp_file: Output file path (e.g., 'data/the_a_team/The_A-Team_Processed.json').
    
    Behavior:
        - Structures JSON with file metadata (paths, sizes, broken status).
        - Includes episode metadata (title, overview, air_date).
        - Writes JSON to temp_file with proper encoding.
        - Logs success or errors.
        - Called by series_folder_crawler.py.
    
    Example Output (Series_Name_Processed.json):
    {
      "series_name": "The A-Team",
      "seasons": [
        {
          "season_number": 1,
          "episodes": [
            {
              "episode_number": 10,
              "title": "",
              "overview": "",
              "air_date": "",
              "paths": [
                {
                  "path": "D:/NEXT PVR/.../The_A-Team_20250303_18411933.ts",
                  "basename": "The_A-Team_20250303_18411933",
                  "broken": false,
                  "file_size": 1133506708,
                  "watched": false
                }
              ]
            }
          ]
        }
      ]
    }
    """
    data = {
        "series_name": series_name,
        "seasons": [
            {
                "season_number": season.get("season_number", 0),
                "episodes": [
                    {
                        "episode_number": ep.get("episode_number", 0),
                        "title": ep.get("title", ""),
                        "overview": ep.get("overview", ""),
                        "air_date": ep.get("air_date", ""),
                        "paths": [
                            {
                                "path": path.get("path", ""),
                                "basename": os.path.splitext(os.path.basename(path.get("path", "")))[0],
                                "broken": path.get("broken", False),
                                "file_size": path.get("file_size", 0),
                                "watched": path.get("watched", False)
                            } for path in ep.get("paths", [])
                        ]
                    } for ep in season.get("episodes", [])
                ]
            } for season in seasons
        ]
    }

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[crawler] Wrote metadata to {temp_file}")
    except Exception as e:
        print(f"[crawler] Error writing {temp_file}: {e}")