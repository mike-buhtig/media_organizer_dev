"""Auditable, history-backed TV-series completeness evaluation."""

import argparse
import configparser
import copy
import json
import ntpath
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from episode_history import validate_history
except ImportError:  # Support import as scripts.series_completeness in repository tests.
    from scripts.episode_history import validate_history


SCHEMA_VERSION = 1
SPECIALS_POLICY = "unknown_unless_curated"
ALLOWED_MEDIA_EXTENSIONS = {".ts"}
UNCERTAIN_VERIFICATION_STATES = {"inaccessible", "size_mismatch"}
HISTORY_EPISODE_KEY_PATTERN = re.compile(r"^S(\d{2,})E(\d{2,})$")


def repository_root() -> Path:
    """Return the project root independently of the process working directory."""
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    """Return the canonical active configuration path."""
    return repository_root() / "config" / "paths.txt"


def series_slug(series_name: str) -> str:
    """Use Season_Episode_builder's directory-slug convention."""
    return series_name.lower().replace(" ", "_").replace("'", "").replace("-", "_")


def _resolve_configured_path(value: str, project_root: Path) -> Path:
    """Resolve relative configured paths against the project, never the caller's cwd."""
    configured = Path(value.strip().strip('"'))
    return configured if configured.is_absolute() else project_root / configured


def load_completeness_config(series_name: str, config_path=None) -> dict:
    """Resolve the exact configured series source and all completeness paths."""
    project_root = repository_root()
    config_path = Path(config_path) if config_path else default_config_path()
    parser = configparser.ConfigParser()
    loaded = parser.read(config_path, encoding="utf-8")
    if not loaded:
        raise FileNotFoundError(f"Configuration not found: {config_path}")
    required = (("general", "JSON_FOLDER"), ("library_paths", "TV_LIBRARY_PATH"),
                ("workspace", "QUARANTINE_ROOT"))
    for section, option in required:
        if not parser.has_option(section, option):
            raise ValueError(f"Missing configuration setting [{section}] {option}")

    source_value = None
    if parser.has_section("series"):
        for key, configured_name in parser.items("series"):
            if not key.startswith("series_name_") or configured_name.strip() != series_name:
                continue
            suffix = key[len("series_name_"):]
            path_key = f"series_path_{suffix}"
            if not parser.has_option("series", path_key):
                raise ValueError(f"Missing configured source path for series_name_{suffix}")
            source_value = parser.get("series", path_key)
            break
    if source_value is None:
        raise ValueError(f"Series is not configured by exact name: {series_name}")

    json_root = _resolve_configured_path(parser.get("general", "JSON_FOLDER"), project_root)
    library_root = _resolve_configured_path(
        parser.get("library_paths", "TV_LIBRARY_PATH"), project_root)
    quarantine_root = _resolve_configured_path(
        parser.get("workspace", "QUARANTINE_ROOT"), project_root)
    source_root = _resolve_configured_path(source_value, project_root)
    series_library_root = library_root / series_name
    organizer_root = series_library_root / ".media_organizer"
    return {
        "config_path": config_path.resolve(),
        "project_root": project_root,
        "json_root": json_root,
        "source_root": source_root,
        "library_root": series_library_root,
        "quarantine_root": quarantine_root / series_name,
        "merged_metadata_path": json_root / series_slug(series_name) / f"{series_name}.json",
        "history_path": organizer_root / "episode_history.json",
        "output_path": organizer_root / "completeness.json",
        "compatibility_output_path": (
            json_root / series_slug(series_name) /
            f"{series_name.replace(' ', '_')}_missing.json"),
    }


def _stat_mtime(path: Path):
    """Return nanosecond mtime, retaining missing inputs as auditable None."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _load_json_input(path: Path):
    """Load UTF-8 JSON and return document or a non-secret diagnostic."""
    try:
        with open(path, "r", encoding="utf-8") as input_file:
            value = json.load(input_file)
        if not isinstance(value, dict):
            return None, "root_not_object"
        return value, None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"malformed_json:{exc.msg}"
    except (OSError, UnicodeError) as exc:
        return None, f"unreadable:{type(exc).__name__}:{exc}"


def _validate_history_for_completeness(history: dict) -> None:
    """Require the path fields completeness relies on in addition to base validation."""
    validate_history(history)
    for episode in history["episodes"].values():
        current_key = episode.get("current_key")
        match = (HISTORY_EPISODE_KEY_PATTERN.fullmatch(current_key)
                 if isinstance(current_key, str) else None)
        if match is None:
            raise ValueError("history episode current_key is malformed")
        season_number = episode.get("season_number")
        episode_number = episode.get("episode_number")
        if (not isinstance(season_number, int) or isinstance(season_number, bool) or
                season_number < 0):
            raise ValueError("history episode season_number is invalid")
        if (not isinstance(episode_number, int) or isinstance(episode_number, bool) or
                episode_number <= 0):
            raise ValueError("history episode episode_number is invalid")
        if (season_number != int(match.group(1)) or
                episode_number != int(match.group(2))):
            raise ValueError("history episode numbers disagree with current_key")
        canonical_key = f"S{season_number:02d}E{episode_number:02d}"
        if current_key != canonical_key:
            raise ValueError("noncanonical_current_key")
        if not isinstance(episode.get("recordings"), list):
            raise ValueError("history episode recordings is not a list")
        for recording in episode["recordings"]:
            if not isinstance(recording, dict):
                raise ValueError("history recording is not an object")
            recording_id = recording.get("recording_id")
            if not isinstance(recording_id, str) or not recording_id.strip():
                raise ValueError("history recording_id is invalid")
            if not isinstance(recording.get("broken"), bool):
                raise ValueError("history recording broken is not boolean")
            recorded_size = recording.get("size")
            if (recorded_size is not None and
                    (not isinstance(recorded_size, int) or
                     isinstance(recorded_size, bool) or recorded_size < 0)):
                raise ValueError("history recording size is not a nonnegative integer or null")
            if not isinstance(recording.get("paths"), list):
                raise ValueError("history recording paths is not a list")
            for path_entry in recording["paths"]:
                if not isinstance(path_entry, dict):
                    raise ValueError("recording path entry is malformed")
                original_path = path_entry.get("path")
                if not isinstance(original_path, str) or not original_path.strip():
                    raise ValueError("recording path is not a non-empty string")
                if path_entry.get("kind") not in {"source", "library", "quarantine"}:
                    raise ValueError("recording path kind is not authorized")
                normalized_path = path_entry.get("normalized_path")
                if (normalized_path is not None and
                        (not isinstance(normalized_path, str) or not normalized_path.strip())):
                    raise ValueError("recording normalized_path is invalid")


def _integer(value):
    """Accept integers but reject booleans and numeric-looking strings."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _provider_mapping(value) -> dict:
    """Preserve provider-keyed evidence, treating malformed fields as empty evidence."""
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def collect_expected_candidates(metadata: dict) -> list:
    """Retain every merged-provider episode candidate without silent key collapse."""
    candidates = []
    seasons = metadata.get("seasons") if isinstance(metadata, dict) else None
    if not isinstance(seasons, list):
        return candidates
    for season_index, season in enumerate(seasons):
        if not isinstance(season, dict):
            candidates.append({
                "candidate_id": f"season-{season_index}-malformed",
                "season_number": None, "episode_number": None,
                "current_key": None, "synthetic": False,
                "titles": {}, "overviews": {}, "ids": {}, "air_date": {},
                "catalog_problem": "malformed_season",
            })
            continue
        season_number = _integer(season.get("season_number"))
        episodes = season.get("episodes")
        if not isinstance(episodes, list):
            candidates.append({
                "candidate_id": f"season-{season_index}-episodes-malformed",
                "season_number": season_number, "episode_number": None,
                "current_key": None, "synthetic": False,
                "titles": {}, "overviews": {}, "ids": {}, "air_date": {},
                "catalog_problem": "malformed_episode_list",
            })
            continue
        for episode_index, episode in enumerate(episodes):
            if not isinstance(episode, dict):
                episode = {}
                catalog_problem = "malformed_episode"
            else:
                catalog_problem = None
            episode_number = _integer(episode.get("episode_number"))
            valid_key = (season_number is not None and season_number >= 0 and
                         episode_number is not None and episode_number > 0)
            current_key = (f"S{season_number:02d}E{episode_number:02d}"
                           if valid_key else None)
            if season_number is None or season_number < 0:
                catalog_problem = catalog_problem or "invalid_season_number"
            elif episode_number is None or episode_number <= 0:
                catalog_problem = catalog_problem or "invalid_episode_number"
            candidates.append({
                "candidate_id": f"season-{season_index}-episode-{episode_index}",
                "season_number": season_number,
                "episode_number": episode_number,
                "current_key": current_key,
                "synthetic": bool(episode.get("synthetic", False)),
                "titles": _provider_mapping(episode.get("titles")),
                "overviews": _provider_mapping(episode.get("overviews")),
                "ids": _provider_mapping(episode.get("ids")),
                "air_date": _provider_mapping(episode.get("air_date")),
                "catalog_problem": catalog_problem,
            })
    return candidates


def _candidate_evidence_signature(candidate: dict) -> str:
    evidence = {key: candidate.get(key) for key in
                ("titles", "overviews", "air_date", "synthetic")}
    return json.dumps(evidence, sort_keys=True, ensure_ascii=False)


def mark_identity_conflicts(candidates: list) -> None:
    """Flag materially different candidates sharing an operational SxxExx key."""
    by_key = {}
    for candidate in candidates:
        if candidate.get("current_key"):
            by_key.setdefault(candidate["current_key"], []).append(candidate)
    for current_key, group in by_key.items():
        signatures = {_candidate_evidence_signature(candidate) for candidate in group}
        conflict = len(group) > 1 and len(signatures) > 1
        for candidate in group:
            candidate["duplicate_candidate_count"] = len(group)
            candidate["identity_conflict"] = conflict
            if conflict:
                candidate.setdefault("unknown_reasons", []).append(
                    f"conflicting_expected_identity:{current_key}")


def assess_air_dates(air_date_evidence: dict, as_of_date: date) -> dict:
    """Apply conservative provider-date eligibility without provider preference."""
    raw = copy.deepcopy(air_date_evidence) if isinstance(air_date_evidence, dict) else {}
    normalized = []
    malformed = []
    for provider, raw_value in raw.items():
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            continue
        value = str(raw_value).strip()
        try:
            parsed = date.fromisoformat(value)
            normalized.append({"provider": provider, "raw": raw_value,
                               "date": parsed.isoformat()})
        except (TypeError, ValueError):
            malformed.append({"provider": provider, "raw": raw_value})
    if malformed:
        return {"state": "unknown", "reason": "malformed_nonempty_air_date",
                "raw": raw, "normalized": normalized, "malformed": malformed}
    if not normalized:
        return {"state": "unknown", "reason": "no_valid_air_date",
                "raw": raw, "normalized": [], "malformed": []}
    distinct_dates = {item["date"] for item in normalized}
    if len(distinct_dates) != 1:
        return {"state": "unknown", "reason": "provider_air_dates_disagree",
                "raw": raw, "normalized": normalized, "malformed": []}
    only_date = date.fromisoformat(next(iter(distinct_dates)))
    if only_date > as_of_date:
        state, reason = "not_eligible_yet", "agreed_air_date_after_as_of"
    else:
        state, reason = "eligible_now", "agreed_air_date_on_or_before_as_of"
    return {"state": state, "reason": reason, "raw": raw,
            "normalized": normalized, "malformed": []}


def _normalized_windows(path) -> str:
    return ntpath.normcase(ntpath.normpath(str(path).replace("/", "\\")))


def _is_beneath(path, root) -> bool:
    """Validate Windows containment case-insensitively, including cross-drive safety."""
    normalized_path = _normalized_windows(path)
    normalized_root = _normalized_windows(root)
    try:
        return ntpath.commonpath([normalized_path, normalized_root]) == normalized_root
    except ValueError:
        return False


def _resolve_existing_path(path: Path) -> Path:
    """Resolve links/reparse points strictly so physical containment can be checked."""
    return Path(path).resolve(strict=True)


def verify_history_path(path_entry: dict, recording: dict, allowed_roots: dict) -> dict:
    """Verify one history path against its declared kind and authorized root."""
    original_path = path_entry.get("path")
    kind = path_entry.get("kind")
    result = {"path": original_path, "kind": kind,
              "transition": path_entry.get("transition"), "verification": None}
    allowed_root = allowed_roots.get(kind)
    result["authorized_root"] = str(allowed_root) if allowed_root else None
    if not original_path or allowed_root is None or not _is_beneath(original_path, allowed_root):
        result["verification"] = "outside_allowed_root"
        return result
    path = Path(original_path)
    root = Path(allowed_root)
    try:
        if not root.exists() or not root.is_dir():
            result["verification"] = "inaccessible"
            result["error"] = "authorized_root_unavailable"
            return result
        if not path.exists():
            result["verification"] = "absent"
            return result
        resolved_root = _resolve_existing_path(root)
        resolved_path = _resolve_existing_path(path)
        result["resolved_path"] = str(resolved_path)
        result["resolved_authorized_root"] = str(resolved_root)
        if not _is_beneath(resolved_path, resolved_root):
            result["verification"] = "outside_allowed_root"
            result["error"] = "resolved_path_escapes_authorized_root"
            return result
        if not resolved_path.is_file():
            result["verification"] = "wrong_type"
            return result
        if path.suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
            result["verification"] = "wrong_type"
            result["error"] = "disallowed_media_extension"
            return result
        actual_size = resolved_path.stat().st_size
        result["actual_size"] = actual_size
        if bool(recording.get("broken", False)):
            result["verification"] = "broken_recording"
            return result
        if actual_size == 0:
            result["verification"] = "zero_size"
            return result
        recorded_size = recording.get("size")
        if isinstance(recorded_size, int) and not isinstance(recorded_size, bool) and recorded_size > 0:
            result["recorded_size"] = recorded_size
            if actual_size != recorded_size:
                result["verification"] = "size_mismatch"
                return result
        result["verification"] = "verified_present"
        return result
    except OSError as exc:
        result["verification"] = "inaccessible"
        result["error"] = f"{type(exc).__name__}:{exc}"
        return result


def _history_episode_by_key(history: dict, current_key: str):
    matches = [episode for episode in history.get("episodes", {}).values()
               if isinstance(episode, dict) and episode.get("current_key") == current_key]
    return matches[0] if len(matches) == 1 else None


def assess_acquisition(candidate: dict, history: dict, history_usable: bool,
                       allowed_roots: dict) -> dict:
    """Evaluate physical possession using history as the sole episode/path bridge."""
    if not history_usable:
        return {"state": "unknown", "history_episode_id": None, "paths_checked": [],
                "reason": "history_missing_or_malformed"}
    current_key = candidate.get("current_key")
    if not current_key:
        return {"state": "unknown", "history_episode_id": None, "paths_checked": [],
                "reason": "candidate_has_no_valid_operational_key"}
    episode = _history_episode_by_key(history, current_key)
    if episode is None:
        duplicate_history_keys = sum(
            1 for value in history.get("episodes", {}).values()
            if isinstance(value, dict) and value.get("current_key") == current_key)
        if duplicate_history_keys > 1:
            return {"state": "unknown", "history_episode_id": None, "paths_checked": [],
                    "reason": "ambiguous_history_episode_key"}
        return {"state": "false", "history_episode_id": None, "paths_checked": [],
                "reason": "episode_not_identified_in_history"}
    checked = []
    for recording in episode.get("recordings", []):
        if not isinstance(recording, dict):
            continue
        for path_entry in recording.get("paths", []):
            if not isinstance(path_entry, dict):
                continue
            verification = verify_history_path(path_entry, recording, allowed_roots)
            verification["recording_id"] = recording.get("recording_id")
            checked.append(verification)
    states = {entry["verification"] for entry in checked}
    if "verified_present" in states:
        state, reason = "true", "verified_retained_media_present"
    elif states & UNCERTAIN_VERIFICATION_STATES:
        state, reason = "unknown", "no_verified_path_and_physical_state_uncertain"
    else:
        state, reason = "false", "no_usable_retained_media_path"
    return {"state": state, "history_episode_id": episode.get("history_episode_id"),
            "paths_checked": checked, "reason": reason}


def _input_descriptor(path: Path, initial_mtime, error=None) -> dict:
    return {"path": str(path), "mtime_ns": initial_mtime, "error": error}


def _summary(candidates: list) -> dict:
    summary = {"candidate_count": len(candidates), "eligible_now": 0,
               "not_eligible_yet": 0, "eligibility_unknown": 0,
               "acquired_true": 0, "acquired_false": 0, "acquired_unknown": 0,
               "definitely_missing": 0, "specials": 0, "identity_conflicts": 0}
    for candidate in candidates:
        eligibility = candidate["eligibility"]["state"]
        if eligibility == "eligible_now":
            summary["eligible_now"] += 1
        elif eligibility == "not_eligible_yet":
            summary["not_eligible_yet"] += 1
        else:
            summary["eligibility_unknown"] += 1
        summary[f"acquired_{candidate['acquired']['state']}"] += 1
        if candidate.get("definitely_missing"):
            summary["definitely_missing"] += 1
        if candidate.get("season_number") == 0:
            summary["specials"] += 1
        if candidate.get("identity_conflict"):
            summary["identity_conflicts"] += 1
    return summary


def aggregate_status(candidates: list, global_unknown_reasons: list) -> tuple:
    """Apply incomplete precedence, then require absence of unknowns for complete."""
    definite_missing = [candidate["current_key"] for candidate in candidates
                        if candidate.get("definitely_missing")]
    unknown_reasons = list(global_unknown_reasons)
    for candidate in candidates:
        unknown_reasons.extend(candidate.get("unknown_reasons", []))
    if definite_missing:
        reasons = [f"definitely_missing:{key}" for key in definite_missing]
        reasons.extend(dict.fromkeys(unknown_reasons))
        return "incomplete", reasons
    if unknown_reasons:
        return "unknown", list(dict.fromkeys(unknown_reasons))
    return "complete", ["all_eligible_expected_episodes_verified_present"]


def _build_candidate_audit(candidate: dict, as_of_date: date, history: dict,
                           history_usable: bool, allowed_roots: dict) -> dict:
    audit = copy.deepcopy(candidate)
    unknown_reasons = list(audit.pop("unknown_reasons", []))
    if audit.get("catalog_problem"):
        expectation_state = "unknown"
        expectation_reason = audit["catalog_problem"]
        unknown_reasons.append(expectation_reason)
    elif audit.get("identity_conflict"):
        expectation_state = "unknown"
        expectation_reason = "duplicate_materially_different_expected_candidates"
    elif audit.get("season_number") == 0:
        expectation_state = "unknown"
        expectation_reason = "special_requires_curated_policy"
        unknown_reasons.append("season_0_requires_curated_policy")
        if audit.get("synthetic"):
            unknown_reasons.append("synthetic_special_number_non_authoritative")
    else:
        expectation_state = "expected"
        expectation_reason = "valid_regular_provider_episode"
    air = assess_air_dates(audit.get("air_date", {}), as_of_date)
    if audit.get("season_number") == 0:
        eligibility = {**air, "state": "unknown",
                       "reason": "special_eligibility_requires_curated_policy"}
    elif expectation_state != "expected":
        eligibility = {**air, "state": "unknown",
                       "reason": "expected_identity_unresolved"}
    else:
        eligibility = air
    acquisition = assess_acquisition(audit, history, history_usable, allowed_roots)
    if eligibility["state"] == "unknown":
        unknown_reasons.append(f"eligibility_unknown:{eligibility['reason']}")
    if acquisition["state"] == "unknown":
        unknown_reasons.append(f"acquisition_unknown:{acquisition['reason']}")
    audit["expectation"] = {"state": expectation_state, "reason": expectation_reason}
    audit["provider_evidence"] = {
        "titles": audit.pop("titles"), "overviews": audit.pop("overviews"),
        "ids": audit.pop("ids"), "synthetic": audit.get("synthetic", False),
    }
    audit.pop("air_date", None)
    audit["air_date_evidence"] = {"raw": eligibility["raw"],
                                  "normalized": eligibility["normalized"],
                                  "malformed": eligibility["malformed"]}
    audit["eligibility"] = {"state": eligibility["state"],
                            "reason": eligibility["reason"]}
    audit["history_episode_id"] = acquisition["history_episode_id"]
    audit["acquired"] = {"state": acquisition["state"], "reason": acquisition["reason"]}
    audit["retained_paths_checked"] = acquisition["paths_checked"]
    audit["definitely_missing"] = (
        expectation_state == "expected" and eligibility["state"] == "eligible_now" and
        acquisition["state"] == "false" and not audit.get("identity_conflict", False))
    audit["missing_reason"] = (
        acquisition["reason"] if audit["definitely_missing"] else None)
    audit["unknown_reasons"] = list(dict.fromkeys(unknown_reasons))
    return audit


def build_completeness_report(series_name: str, resolved: dict, metadata, metadata_error,
                              history, history_error, as_of_date: date,
                              initial_mtimes: dict) -> dict:
    """Construct the full audit from already-loaded immutable input snapshots."""
    global_unknown = []
    if metadata_error:
        global_unknown.append(f"merged_metadata_{metadata_error}")
    if history_error:
        global_unknown.append(f"episode_history_{history_error}")
    candidates = collect_expected_candidates(metadata or {})
    if metadata is not None and not isinstance(metadata.get("seasons"), list):
        global_unknown.append("merged_metadata_missing_or_malformed_seasons")
    if metadata is not None and not candidates:
        global_unknown.append("merged_metadata_contains_no_expected_candidates")
    mark_identity_conflicts(candidates)
    allowed_roots = {"source": resolved["source_root"],
                     "library": resolved["library_root"],
                     "quarantine": resolved["quarantine_root"]}
    history_usable = history is not None and history_error is None
    audited = [_build_candidate_audit(candidate, as_of_date, history or {},
                                      history_usable, allowed_roots)
               for candidate in candidates]
    status, status_reasons = aggregate_status(audited, global_unknown)
    return {
        "schema_version": SCHEMA_VERSION,
        "series": series_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "status": status,
        "status_reasons": status_reasons,
        "resolved_roots": {key: str(value) for key, value in allowed_roots.items()},
        "inputs": {
            "merged_metadata": _input_descriptor(
                resolved["merged_metadata_path"], initial_mtimes["merged_metadata"],
                metadata_error),
            "episode_history": _input_descriptor(
                resolved["history_path"], initial_mtimes["episode_history"], history_error),
        },
        "policy": {"specials_policy": SPECIALS_POLICY,
                   "allowed_media_extensions": sorted(ALLOWED_MEDIA_EXTENSIONS),
                   "provider_ids_authoritative": False,
                   "physical_possession_requires_history": True},
        "summary": _summary(audited),
        "expected_candidates": audited,
    }


def atomic_write_json(path: Path, value: dict) -> None:
    """Atomically write validated JSON while preserving any prior valid result."""
    path = Path(path)
    payload = json.dumps(value, indent=2, ensure_ascii=False)
    json.loads(payload)
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


def evaluate_series_completeness(series_name: str, config_path=None, as_of_date=None) -> dict:
    """Evaluate, freshness-check, atomically persist, and return completeness."""
    resolved = load_completeness_config(series_name, config_path)
    evaluation_date = as_of_date or date.today()
    if isinstance(evaluation_date, str):
        evaluation_date = date.fromisoformat(evaluation_date)
    input_paths = {"merged_metadata": resolved["merged_metadata_path"],
                   "episode_history": resolved["history_path"]}
    initial_mtimes = {name: _stat_mtime(path) for name, path in input_paths.items()}
    metadata, metadata_error = _load_json_input(resolved["merged_metadata_path"])
    if metadata is not None:
        metadata_series_name = metadata.get("series_name")
        if not isinstance(metadata_series_name, str) or metadata_series_name != series_name:
            metadata, metadata_error = None, "wrong_series_metadata"
    history, history_error = _load_json_input(resolved["history_path"])
    if history is not None:
        try:
            _validate_history_for_completeness(history)
            if history.get("series", {}).get("name") != series_name:
                raise ValueError("series_mismatch")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            history, history_error = None, f"malformed_schema:{exc}"
    report = build_completeness_report(
        series_name, resolved, metadata, metadata_error, history, history_error,
        evaluation_date, initial_mtimes)
    final_mtimes = {name: _stat_mtime(path) for name, path in input_paths.items()}
    changed = [name for name in input_paths if final_mtimes[name] != initial_mtimes[name]]
    if changed:
        report["status"] = "unknown"
        report["status_reasons"] = [
            reason for reason in report["status_reasons"]
            if not reason.startswith("all_eligible_expected_episodes_verified_present")]
        report["status_reasons"].append("input_changed_during_evaluation")
        report["input_changes"] = changed
    atomic_write_json(resolved["output_path"], report)
    report["output_path"] = str(resolved["output_path"])
    report["compatibility_output_path"] = str(resolved["compatibility_output_path"])
    return report


def compatibility_projection(report: dict) -> dict:
    """Project only definite misses while making uncertainty explicit."""
    missing = []
    for candidate in report.get("expected_candidates", []):
        if candidate.get("definitely_missing"):
            missing.append({
                "season_number": candidate.get("season_number"),
                "episode_number": candidate.get("episode_number"),
                "current_key": candidate.get("current_key"),
                "titles": candidate.get("provider_evidence", {}).get("titles", {}),
                "overviews": candidate.get("provider_evidence", {}).get("overviews", {}),
                "air_date": candidate.get("air_date_evidence", {}).get("raw", {}),
                "missing_reason": candidate.get("missing_reason"),
            })
    has_unresolved_candidates = any(
        candidate.get("unknown_reasons")
        for candidate in report.get("expected_candidates", []))
    return {
        "series_name": report.get("series"),
        "status": report.get("status"),
        "missing_episodes": missing,
        "missing_list_exhaustive": (
            report.get("status") != "unknown" and not has_unresolved_candidates),
        "authoritative_completeness_path": report.get("output_path"),
        "notice": "completeness.json is authoritative; this is a compatibility projection",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate TV-series completeness.")
    parser.add_argument("series_name", help="Exact series_name_N value from config/paths.txt")
    parser.add_argument("--as-of-date", help="Audit date in YYYY-MM-DD form (default: today)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = evaluate_series_completeness(
            args.series_name, as_of_date=args.as_of_date)
    except Exception as exc:
        print(f"Completeness evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Series completeness: {report['status']}")
    print(f"Authoritative report: {report['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
