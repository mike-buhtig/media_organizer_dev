"""Durable, append-only episode and recording path history for Media Organizer."""

import json
import ntpath
import os
import uuid
from pathlib import Path


SCHEMA_VERSION = 1


def normalize_windows_path(path: str) -> str:
    """Normalize separators and case for comparison while preserving original strings elsewhere."""
    return ntpath.normpath(str(path).replace("/", "\\")).casefold()


def new_history(series_name: str) -> dict:
    """Create an empty versioned history document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "series": {"name": series_name},
        "episodes": {},
        "unresolved_observations": [],
    }


def validate_history(history: dict) -> None:
    """Reject malformed history before it can replace a known-valid document."""
    if not isinstance(history, dict) or history.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported or missing episode history schema_version")
    if not isinstance(history.get("series"), dict) or not history["series"].get("name"):
        raise ValueError("Episode history requires a series name")
    if not isinstance(history.get("episodes"), dict):
        raise ValueError("Episode history episodes must be an object")
    if not isinstance(history.get("unresolved_observations"), list):
        raise ValueError("Episode history unresolved_observations must be an array")
    for observation in history["unresolved_observations"]:
        if isinstance(observation, dict) and observation.get("observation_type") == "kodi_watched":
            _validate_kodi_observation(observation, matched=False)
    for history_episode_id, episode in history["episodes"].items():
        if episode.get("history_episode_id") != history_episode_id:
            raise ValueError("Episode key and history_episode_id disagree")
        if not isinstance(episode.get("recordings"), list):
            raise ValueError("Episode recordings must be an array")
        for recording in episode["recordings"]:
            if not recording.get("recording_id") or not isinstance(recording.get("paths"), list):
                raise ValueError("Recording requires recording_id and paths")
        watched_evidence = episode.get("watched_evidence")
        if watched_evidence is not None:
            _validate_watched_evidence(watched_evidence)


def _validate_kodi_observation(observation: dict, matched: bool) -> None:
    """Validate additive Kodi evidence without changing recording identity rules."""
    required = (
        "observation_id", "source_id", "device_id", "database_name",
        "database_version", "database_fingerprint", "observed_kodi_path",
        "normalized_kodi_path", "playCount", "lastPlayed", "observed_at",
        "match_method",
    )
    if not isinstance(observation, dict) or any(key not in observation for key in required):
        raise ValueError("Kodi observation is missing required provenance")
    play_count = observation["playCount"]
    if isinstance(play_count, bool) or not isinstance(play_count, (int, float)):
        raise ValueError("Kodi observation playCount must be numeric")
    if matched:
        matched_fields = (
            "matched_history_episode_id", "matched_recording_id",
            "matched_historical_path",
        )
        if any(not observation.get(key) for key in matched_fields):
            raise ValueError("Matched Kodi observation is missing history identity")


def _validate_watched_evidence(watched_evidence: dict) -> None:
    """Validate the optional schema-1 watched-evidence extension."""
    if not isinstance(watched_evidence, dict):
        raise ValueError("watched_evidence must be an object")
    observations = watched_evidence.get("observations")
    aggregate = watched_evidence.get("aggregate")
    if not isinstance(observations, list) or not isinstance(aggregate, dict):
        raise ValueError("watched_evidence requires observations and aggregate")
    for observation in observations:
        _validate_kodi_observation(observation, matched=True)
    if not isinstance(aggregate.get("watched"), bool):
        raise ValueError("watched aggregate must be boolean")
    play_count = aggregate.get("playCount")
    if isinstance(play_count, bool) or not isinstance(play_count, (int, float)):
        raise ValueError("watched aggregate playCount must be numeric")


def load_history(path: Path, series_name: str) -> dict:
    """Load a valid history document, or return a new document when none exists."""
    path = Path(path)
    if not path.exists():
        return new_history(series_name)
    with open(path, "r", encoding="utf-8") as history_file:
        history = json.load(history_file)
    validate_history(history)
    if history["series"]["name"] != series_name:
        raise ValueError("Episode history belongs to a different series")
    return history


def atomic_write_history(path: Path, history: dict) -> None:
    """Validate and atomically replace history, preserving the prior file on failure."""
    path = Path(path)
    validate_history(history)
    payload = json.dumps(history, indent=2, ensure_ascii=False)
    reparsed = json.loads(payload)
    validate_history(reparsed)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp_path, "x", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(payload)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def episode_key(season_number: int, episode_number: int) -> str:
    """Return the existing operational season/episode key."""
    return f"S{season_number:02d}E{episode_number:02d}"


def find_episode_by_key(history: dict, current_key: str):
    """Find an established local episode using only its operational key."""
    for episode in history["episodes"].values():
        if episode.get("current_key") == current_key:
            return episode
    return None


def _observation_from_episode(episode: dict) -> dict:
    """Capture non-authoritative crawler evidence without recording transient file entries."""
    fields = (
        "local_xml_subtitle", "local_xml_description", "matched_by_pass",
        "titles", "overviews", "ids", "air_date", "synthetic",
    )
    return {field: episode[field] for field in fields if field in episode}


def _append_unique_object(items: list, value: dict) -> None:
    """Append a JSON object only when its canonical value has not already been observed."""
    signature = json.dumps(value, sort_keys=True, ensure_ascii=False)
    if all(json.dumps(item, sort_keys=True, ensure_ascii=False) != signature for item in items):
        items.append(value)


def _find_recording_by_normalized_path(episode: dict, normalized_path: str):
    for recording in episode["recordings"]:
        if any(path_entry["normalized_path"] == normalized_path for path_entry in recording["paths"]):
            return recording
    return None


def _add_path(recording: dict, original_path: str, kind: str, transition: str) -> None:
    normalized = normalize_windows_path(original_path)
    exact_entry_exists = any(
        entry["normalized_path"] == normalized and entry["path"] == original_path
        and entry["kind"] == kind and entry["transition"] == transition
        for entry in recording["paths"]
    )
    if not exact_entry_exists:
        recording["paths"].append({
            "path": original_path,
            "normalized_path": normalized,
            "kind": kind,
            "transition": transition,
        })


def _merge_recording(episode: dict, file_info: dict) -> dict:
    original_path = file_info.get("path")
    if not original_path:
        raise ValueError("Processed recording is missing path")
    normalized = normalize_windows_path(original_path)
    recording = _find_recording_by_normalized_path(episode, normalized)
    if recording is None:
        recording = {
            "recording_id": str(uuid.uuid4()),
            "size": file_info.get("size"),
            "broken": bool(file_info.get("broken", False)),
            "paths": [],
        }
        episode["recordings"].append(recording)
    else:
        if recording.get("size") is None and file_info.get("size") is not None:
            recording["size"] = file_info["size"]
        recording["broken"] = bool(recording.get("broken", False) or file_info.get("broken", False))
    _add_path(recording, original_path, "source", "observed")
    return recording


def _unresolved_value(episode: dict) -> dict:
    value = _observation_from_episode(episode)
    value["season_number"] = episode.get("season_number")
    value["episode_number"] = episode.get("episode_number")
    value["files"] = [
        {
            "path": file_info.get("path"),
            "normalized_path": normalize_windows_path(file_info.get("path", "")),
            "size": file_info.get("size"),
            "broken": bool(file_info.get("broken", False)),
        }
        for file_info in episode.get("files", [])
    ]
    return value


def merge_processed_episodes(history: dict, episodes: list) -> dict:
    """Idempotently merge a flattened processed snapshot into durable history."""
    validate_history(history)
    for processed_episode in episodes:
        season_number = processed_episode.get("season_number")
        episode_number = processed_episode.get("episode_number")
        if not isinstance(season_number, int) or not isinstance(episode_number, int):
            _append_unique_object(history["unresolved_observations"], _unresolved_value(processed_episode))
            continue

        current_key = episode_key(season_number, episode_number)
        episode = find_episode_by_key(history, current_key)
        if episode is None:
            history_episode_id = str(uuid.uuid4())
            episode = {
                "history_episode_id": history_episode_id,
                "current_key": current_key,
                "season_number": season_number,
                "episode_number": episode_number,
                "observations": [],
                "recordings": [],
                "selected_recording_id": None,
            }
            history["episodes"][history_episode_id] = episode

        _append_unique_object(episode["observations"], _observation_from_episode(processed_episode))
        for file_info in processed_episode.get("files", []):
            _merge_recording(episode, file_info)
    validate_history(history)
    return history


def record_verified_transition(history: dict, current_key: str, source_path: str,
                               destination_path: str, destination_kind: str,
                               transition: str, selected: bool = False) -> str:
    """Append a verified path transition to the exact previously observed recording."""
    episode = find_episode_by_key(history, current_key)
    if episode is None:
        raise KeyError(f"History episode not found: {current_key}")
    recording = _find_recording_by_normalized_path(
        episode, normalize_windows_path(source_path))
    if recording is None:
        raise KeyError(f"History recording not found for exact path: {source_path}")
    _add_path(recording, destination_path, destination_kind, transition)
    if selected:
        episode["selected_recording_id"] = recording["recording_id"]
    validate_history(history)
    return recording["recording_id"]
