# json_utils.py
# Standardizes JSON output for provider and crawler scripts
#
# Change Log:
# [1.0.0] - 2025-05-03: Initial version with format_builder_json, format_crawler_json, and clean_temp_file
# [1.0.1] - 2025-05-04: Added template-based formatting for flexible JSON structures

import json
import os
from typing import Dict, List, Any

def clean_temp_file(temp_file: str, provider_name: str) -> None:
    """Delete existing temp file if it exists."""
    if os.path.exists(temp_file):
        os.remove(temp_file)
        print(f"[{provider_name}f] Deleted existing temp file: {temp_file}")

def format_builder_json(
    series_name: str,
    seasons: List[Dict[str, Any]],
    temp_file: str,
    provider_name: str = None,
    template: str = "builder"
) -> None:
    """
    Format builder JSON (e.g., The_A-Team.json) or provider JSON (e.g., tmp/provider_tvmaze.json).
    
    Args:
        series_name: Series title.
        seasons: List of seasons with episodes and metadata.
        temp_file: Output file path.
        provider_name: Provider name for provider JSON (e.g., 'tvmaze').
        template: 'builder' or 'provider' to select format.
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
    Format crawler JSON with video file metadata.
    
    Args:
        series_name: Series title.
        seasons: List of seasons with episodes and file metadata.
        temp_file: Output file path.
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