"""Offline extraction and durable merging of path-based Kodi watched evidence."""

import hashlib
import json
import ntpath
import posixpath
import re
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from scripts.episode_history import atomic_write_history, load_history, validate_history
except ImportError:  # Support direct execution from the scripts directory.
    from episode_history import atomic_write_history, load_history, validate_history


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_DATABASE_VERSION = re.compile(r"MyVideos(\d+)\.db$", re.IGNORECASE)
_OPAQUE_URI = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<authority>[^/?#]*)(?P<remainder>.*)$",
    re.DOTALL,
)


class SnapshotChangedDuringReadError(RuntimeError):
    """Raised when database/WAL identity changes while evidence is being read."""


def utc_timestamp() -> str:
    """Return a timezone-explicit UTC scan timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_kodi_path(value: str) -> str:
    """Build a scheme-aware comparison key while preserving the source value elsewhere."""
    path = str(value)
    if _WINDOWS_DRIVE.match(path):
        normalized = ntpath.normpath(path.replace("/", "\\")).casefold()
        return f"windows:{normalized}"
    if path.startswith(("\\\\", "//")) and not _URI_SCHEME.match(path):
        normalized = ntpath.normpath(path.replace("/", "\\")).casefold()
        return f"unc:{normalized}"
    if _URI_SCHEME.match(path):
        opaque_match = _OPAQUE_URI.match(path)
        if opaque_match and opaque_match.group("scheme").casefold() != "smb":
            # Kodi add-on, PVR, and unknown URI handlers may assign meaning to dot
            # segments and backslashes. Preserve everything after authority exactly.
            return (
                "uri:"
                f"{opaque_match.group('scheme').casefold()}://"
                f"{opaque_match.group('authority').casefold()}"
                f"{opaque_match.group('remainder')}"
            )
        parsed = urlsplit(path)
        scheme = parsed.scheme.casefold()
        authority = parsed.netloc.casefold()
        uri_path = parsed.path.replace("\\", "/")
        trailing_slash = uri_path.endswith("/")
        uri_path = posixpath.normpath(uri_path)
        if parsed.path.startswith("/") and not uri_path.startswith("/"):
            uri_path = "/" + uri_path
        if trailing_slash and uri_path != "/" and not uri_path.endswith("/"):
            uri_path += "/"
        # SMB paths are served by Windows-like shares and compare case-insensitively.
        if scheme == "smb":
            uri_path = uri_path.casefold()
        normalized = urlunsplit((scheme, authority, uri_path, parsed.query, parsed.fragment))
        return f"uri:{normalized}"
    # Non-URI local POSIX/relative paths stay distinct from Windows and URI identities.
    return f"local:{posixpath.normpath(path.replace('\\', '/'))}"


def _update_digest_from_file(digest, label: bytes, path: Path) -> None:
    """Hash a framed snapshot component so main/WAL boundaries are unambiguous."""
    digest.update(label)
    digest.update(path.stat().st_size.to_bytes(16, "big"))
    with open(path, "rb") as snapshot_file:
        for block in iter(lambda: snapshot_file.read(1024 * 1024), b""):
            digest.update(block)


def database_fingerprint(database_path: Path) -> str:
    """Hash main DB bytes and companion WAL bytes, excluding transient SHM metadata."""
    database_path = Path(database_path)
    wal_path = Path(f"{database_path}-wal")
    digest = hashlib.sha256()
    _update_digest_from_file(digest, b"main\0", database_path)
    if wal_path.is_file():
        _update_digest_from_file(digest, b"wal\0", wal_path)
    else:
        digest.update(b"no-wal\0")
    return f"sha256:{digest.hexdigest()}"


def _component_state(path: Path):
    """Capture mutation-sensitive metadata without treating SHM as snapshot content."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _capture_snapshot(database_path: Path) -> dict:
    """Capture a stable main/WAL identity, rejecting mutation during fingerprinting."""
    wal_path = Path(f"{database_path}-wal")
    before = (_component_state(database_path), _component_state(wal_path))
    try:
        fingerprint = database_fingerprint(database_path)
    except (FileNotFoundError, OSError) as exc:
        raise SnapshotChangedDuringReadError("snapshot_changed_during_read") from exc
    after = (_component_state(database_path), _component_state(wal_path))
    if before != after or after[0] is None:
        raise SnapshotChangedDuringReadError("snapshot_changed_during_read")
    return {
        "fingerprint": fingerprint,
        "state": after,
        "wal_present": after[1] is not None,
    }


def parse_database_version(database_name: str):
    """Parse MyVideosNNN.db versions while retaining unknown filenames safely."""
    match = _DATABASE_VERSION.search(database_name)
    return int(match.group(1)) if match else None


def _observation_id(observation: dict) -> str:
    """Hash stable evidence fields; observed_at is deliberately excluded for idempotency."""
    identity = {
        key: observation.get(key)
        for key in (
            "source_id", "database_fingerprint", "normalized_kodi_path",
            "playCount", "lastPlayed",
        )
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_watched_observations(database_path, device_id: str, observed_at=None,
                                 include_zero: bool = False) -> list:
    """Read path-level evidence from a local MyVideos DB without episode-table identity."""
    database_path = Path(database_path)
    if not database_path.is_file():
        return []
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("device_id must be an explicit non-empty operator identifier")

    scan_time = observed_at or utc_timestamp()
    snapshot = _capture_snapshot(database_path)
    database_name = database_path.name
    source_id = f"kodi:{device_id.strip()}"
    sql = """
        SELECT p.strPath || f.strFilename, f.playCount, f.lastPlayed
        FROM files AS f
        JOIN path AS p ON p.idPath = f.idPath
        WHERE f.strFilename IS NOT NULL
          AND f.playCount IS NOT NULL
    """
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()
    final_snapshot = _capture_snapshot(database_path)
    if (snapshot["state"] != final_snapshot["state"]
            or snapshot["fingerprint"] != final_snapshot["fingerprint"]):
        raise SnapshotChangedDuringReadError("snapshot_changed_during_read")

    observations = []
    for full_path, play_count, last_played in rows:
        if not isinstance(full_path, str) or not full_path:
            warnings.warn(
                "Skipping Kodi watched row with null/non-string/empty full path",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if isinstance(play_count, bool) or not isinstance(play_count, (int, float)):
            continue
        if play_count <= 0 and not include_zero:
            continue
        observation = {
            "source_id": source_id,
            "device_id": device_id.strip(),
            "database_name": database_name,
            "database_version": parse_database_version(database_name),
            "database_fingerprint": snapshot["fingerprint"],
            "database_wal_present": snapshot["wal_present"],
            "database_wal_included": snapshot["wal_present"],
            "observed_kodi_path": full_path,
            "normalized_kodi_path": normalize_kodi_path(full_path),
            "playCount": play_count,
            "lastPlayed": last_played,
            "observed_at": scan_time,
            "match_method": "unmatched",
        }
        observation["observation_id"] = _observation_id(observation)
        observations.append(observation)
    return observations


def _history_path_index(history: dict) -> dict:
    """Index all historical aliases without checking whether any file still exists."""
    index = {}
    for history_episode_id, episode in history["episodes"].items():
        for recording in episode.get("recordings", []):
            for path_entry in recording.get("paths", []):
                original_path = path_entry.get("path")
                if not original_path:
                    continue
                key = normalize_kodi_path(original_path)
                index.setdefault(key, []).append({
                    "history_episode_id": history_episode_id,
                    "recording_id": recording["recording_id"],
                    "historical_path": original_path,
                })
    return index


def _join_normalized_prefix(target_prefix: str, suffix: str) -> str:
    separator = "\\" if target_prefix.startswith(("windows:", "unc:")) else "/"
    return target_prefix.rstrip("/\\") + separator + suffix.lstrip("/\\")


def _alias_candidates(normalized_path: str, aliases: list, path_index: dict) -> list:
    """Apply only the longest explicit source prefix and return unique full-path targets."""
    applicable = []
    for alias in aliases or []:
        source = alias.get("source")
        target = alias.get("target")
        if not source or not target:
            continue
        source_key = normalize_kodi_path(source).rstrip("/\\")
        if normalized_path == source_key or normalized_path.startswith(source_key + "/") \
                or normalized_path.startswith(source_key + "\\"):
            applicable.append((len(source_key), source_key, normalize_kodi_path(target)))
    if not applicable:
        return []
    longest = max(item[0] for item in applicable)
    results = []
    seen = set()
    for _, source_key, target_key in (item for item in applicable if item[0] == longest):
        translated = _join_normalized_prefix(target_key, normalized_path[len(source_key):])
        for candidate in path_index.get(translated, []):
            identity = (candidate["history_episode_id"], candidate["recording_id"],
                        candidate["historical_path"])
            if identity not in seen:
                seen.add(identity)
                results.append(candidate)
    return results


def match_observation(observation: dict, history: dict, aliases=None) -> dict:
    """Match by exact full identity first, then a unique explicit-prefix translation."""
    index = _history_path_index(history)
    exact = index.get(observation["normalized_kodi_path"], [])
    method = "exact_full_path"
    candidates = exact
    if not exact:
        candidates = _alias_candidates(observation["normalized_kodi_path"], aliases or [], index)
        method = "configured_prefix_alias"
    if len(candidates) != 1:
        unresolved = dict(observation)
        unresolved["match_method"] = "ambiguous" if candidates else "unmatched"
        return unresolved
    candidate = candidates[0]
    matched = dict(observation)
    matched.update({
        "match_method": method,
        "matched_history_episode_id": candidate["history_episode_id"],
        "matched_recording_id": candidate["recording_id"],
        "matched_historical_path": candidate["historical_path"],
    })
    return matched


def _parsed_last_played(value):
    """Return a comparable UTC-aware datetime, or None for missing/invalid evidence."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aggregate(observations: list) -> dict:
    valid_counts = [item["playCount"] for item in observations
                    if isinstance(item.get("playCount"), (int, float))
                    and not isinstance(item.get("playCount"), bool)]
    latest_raw = None
    latest_value = None
    for item in observations:
        parsed = _parsed_last_played(item.get("lastPlayed"))
        if parsed is not None and (latest_value is None or parsed > latest_value):
            latest_value = parsed
            latest_raw = item["lastPlayed"]
    return {
        "watched": any(value > 0 for value in valid_counts),
        "playCount": max(valid_counts, default=0),
        "lastPlayed": latest_raw,
    }


def _append_by_observation_id(items: list, observation: dict) -> None:
    if all(item.get("observation_id") != observation["observation_id"] for item in items
           if isinstance(item, dict)):
        items.append(observation)


def merge_observations_into_history(history: dict, observations: list, aliases=None) -> dict:
    """Idempotently accumulate matched and unresolved Kodi observations in schema 1."""
    validate_history(history)
    for observation in observations:
        matched = match_observation(observation, history, aliases=aliases)
        history_episode_id = matched.get("matched_history_episode_id")
        if not history_episode_id:
            unresolved = {"observation_type": "kodi_watched", **matched}
            _append_by_observation_id(history["unresolved_observations"], unresolved)
            continue
        episode = history["episodes"][history_episode_id]
        evidence = episode.setdefault("watched_evidence", {
            "observations": [],
            "aggregate": {"watched": False, "playCount": 0, "lastPlayed": None},
        })
        _append_by_observation_id(evidence["observations"], matched)
        evidence["aggregate"] = _aggregate(evidence["observations"])
    validate_history(history)
    return history


def merge_database_into_history(database_path, device_id: str, history_path,
                                series_name: str, aliases=None, observed_at=None,
                                include_zero: bool = False) -> dict:
    """Extract a local snapshot, merge it, and reuse the established atomic history write."""
    observations = extract_watched_observations(
        database_path, device_id, observed_at=observed_at, include_zero=include_zero)
    history = load_history(Path(history_path), series_name)
    if not observations:
        return history
    merge_observations_into_history(history, observations, aliases=aliases)
    atomic_write_history(Path(history_path), history)
    return history
