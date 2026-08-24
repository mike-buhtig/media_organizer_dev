"""Tests for the canonical, history-backed series completeness engine."""

import json
import os
import shutil
import unittest
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import find_missing_episodes
from scripts import series_completeness


TEST_ROOT = Path(r"E:\MediaOrganizerWork\Test")


class SeriesCompletenessTests(unittest.TestCase):
    series = "Test Series"

    def setUp(self):
        self.root = TEST_ROOT / f"completeness_{uuid.uuid4().hex}"
        self.source_root = self.root / "source" / self.series
        self.tv_root = self.root / "library"
        self.quarantine_root = self.root / "quarantine"
        self.json_root = self.root / "catalog"
        for path in (self.source_root, self.tv_root, self.quarantine_root,
                     self.json_root):
            path.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "paths.txt"
        self.config_path.write_text(
            "[general]\n"
            f"JSON_FOLDER = {self.json_root.as_posix()}\n"
            "[series]\n"
            f"series_name_1 = {self.series}\n"
            f"series_path_1 = {self.source_root.as_posix()}\n"
            "[library_paths]\n"
            f"TV_LIBRARY_PATH = {self.tv_root.as_posix()}\n"
            "[workspace]\n"
            f"QUARANTINE_ROOT = {self.quarantine_root.as_posix()}\n",
            encoding="utf-8")
        self.resolved = series_completeness.load_completeness_config(
            self.series, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def episode(self, season=1, number=1, air_date="2020-01-01", title="Pilot",
                ids=None, synthetic=False):
        return {
            "episode_number": number,
            "titles": {"tmdb": title},
            "overviews": {"tmdb": f"{title} overview"},
            "ids": {} if ids is None else ids,
            "air_date": {} if air_date is None else (
                air_date if isinstance(air_date, dict) else {"tmdb": air_date}),
            "synthetic": synthetic,
        }

    def write_metadata(self, episodes, season=1, seasons=None, series_name=None):
        path = self.resolved["merged_metadata_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"series_name": self.series if series_name is None else series_name,
                   "seasons": seasons or [
            {"season_number": season, "episodes": episodes}]}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def write_history(self, entries=()):
        history = {
            "schema_version": 1,
            "series": {"name": self.series},
            "episodes": {},
            "unresolved_observations": [],
        }
        for index, entry in enumerate(entries):
            season = entry.get("season", 1)
            episode = entry.get("episode", 1)
            history_id = f"history-{index}"
            path = entry.get("path")
            recording = {
                "recording_id": f"recording-{index}",
                "size": entry.get("size"),
                "broken": entry.get("broken", False),
                "paths": [] if path is None else [{
                    "path": str(path),
                    "normalized_path": str(path).lower(),
                    "kind": entry.get("kind", "source"),
                    "transition": "observed",
                }],
            }
            history["episodes"][history_id] = {
                "history_episode_id": history_id,
                "current_key": f"S{season:02d}E{episode:02d}",
                "season_number": season,
                "episode_number": episode,
                "recordings": [recording],
                "observations": [],
                "selected_recording_id": None,
            }
        path = self.resolved["history_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history), encoding="utf-8")
        return path

    def media(self, path, content=b"media"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def evaluate(self):
        return series_completeness.evaluate_series_completeness(
            self.series, self.config_path, as_of_date=date(2026, 8, 23))

    def test_all_expected_acquired_is_complete(self):
        media = self.media(self.source_root / "Pilot.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": media.stat().st_size}])
        report = self.evaluate()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["summary"]["acquired_true"], 1)
        self.assertTrue(self.resolved["output_path"].exists())

    def test_definitely_missing_eligible_episode_is_incomplete(self):
        self.write_metadata([self.episode()])
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(report["expected_candidates"][0]["definitely_missing"])

    def test_missing_future_episode_does_not_make_incomplete(self):
        self.write_metadata([self.episode(air_date="2030-01-01")])
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "complete")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_conflicting_air_dates_are_unknown(self):
        self.write_metadata([self.episode(air_date={
            "tmdb": "2020-01-01", "trakt": "2020-01-02"})])
        self.write_history([])
        self.assertEqual(self.evaluate()["status"], "unknown")

    def test_unknown_air_date_unacquired_is_unknown(self):
        self.write_metadata([self.episode(air_date=None)])
        self.write_history([])
        self.assertEqual(self.evaluate()["status"], "unknown")

    def test_acquired_episode_with_uncertain_air_date_remains_acquired(self):
        media = self.media(self.source_root / "Pilot.ts")
        self.write_metadata([self.episode(air_date=None)])
        self.write_history([{"path": media, "size": media.stat().st_size}])
        candidate = self.evaluate()["expected_candidates"][0]
        self.assertEqual(candidate["acquired"]["state"], "true")

    def test_duplicate_regular_key_with_different_evidence_is_unknown(self):
        self.write_metadata([self.episode(title="Pilot"), self.episode(title="Different")])
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(len(report["expected_candidates"]), 2)
        self.assertTrue(all(item["identity_conflict"] for item in report["expected_candidates"]))

    def test_provider_id_difference_alone_does_not_create_identity_conflict(self):
        first = self.episode(ids={"tmdb": "one"})
        second = self.episode(ids={"tmdb": "two"})
        self.write_metadata([first, second])
        self.write_history([])
        candidates = self.evaluate()["expected_candidates"]
        self.assertTrue(all(not item["identity_conflict"] for item in candidates))
        self.assertEqual(candidates[0]["provider_evidence"]["ids"], {"tmdb": "one"})
        self.assertEqual(candidates[1]["provider_evidence"]["ids"], {"tmdb": "two"})

    def test_identical_duplicate_candidates_do_not_create_conflict(self):
        media = self.media(self.source_root / "Pilot.ts")
        episode = self.episode()
        self.write_metadata([episode, dict(episode)])
        self.write_history([{"path": media, "size": media.stat().st_size}])
        report = self.evaluate()
        self.assertEqual(report["status"], "complete")
        self.assertTrue(all(not item["identity_conflict"]
                            for item in report["expected_candidates"]))

    def test_season_zero_default_policy_is_unknown(self):
        self.write_metadata([self.episode(season=0)], season=0)
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["policy"]["specials_policy"], "unknown_unless_curated")

    def test_synthetic_special_number_is_not_authoritative(self):
        self.write_metadata([self.episode(season=0, synthetic=True)], season=0)
        self.write_history([])
        reasons = self.evaluate()["expected_candidates"][0]["unknown_reasons"]
        self.assertIn("synthetic_special_number_non_authoritative", reasons)

    def test_valid_source_retained_path(self):
        media = self.media(self.source_root / "source.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 5, "kind": "source"}])
        self.assertEqual(self.evaluate()["summary"]["acquired_true"], 1)

    def test_valid_library_retained_path(self):
        media = self.media(self.resolved["library_root"] / "Season 01" / "library.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 5, "kind": "library"}])
        self.assertEqual(self.evaluate()["summary"]["acquired_true"], 1)

    def test_valid_quarantine_retained_path(self):
        media = self.media(self.resolved["quarantine_root"] / "S01E01" / "copy.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 5, "kind": "quarantine"}])
        self.assertEqual(self.evaluate()["summary"]["acquired_true"], 1)

    def test_stale_historical_path_is_absent(self):
        stale = self.source_root / "gone.ts"
        self.write_metadata([self.episode()])
        self.write_history([{"path": stale, "size": 5}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "absent")

    def test_outside_root_path_is_rejected(self):
        outside = self.media(self.root / "outside" / "copy.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": outside, "size": 5, "kind": "source"}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "outside_allowed_root")

    def test_resolved_path_escape_is_rejected(self):
        media = self.media(self.source_root / "linked.ts")
        escaped = self.media(self.root / "outside" / "escaped.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": media.stat().st_size}])

        def resolve_for_test(path):
            path = Path(path)
            if path == media:
                return escaped.resolve()
            return path.resolve()

        with mock.patch.object(series_completeness, "_resolve_existing_path",
                               side_effect=resolve_for_test):
            report = self.evaluate()
        checked = report["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "outside_allowed_root")
        self.assertEqual(report["expected_candidates"][0]["acquired"]["state"], "false")

    def test_windows_lexical_containment_prevents_prefix_confusion(self):
        self.assertFalse(series_completeness._is_beneath(
            r"D:\Recordings\Show2\episode.ts", r"D:\Recordings\Show"))

    def test_windows_lexical_containment_normalizes_case_and_slashes(self):
        self.assertTrue(series_completeness._is_beneath(
            "d:/recordings/show/Season 01/EPISODE.ts", r"D:\Recordings\Show"))

    def test_windows_lexical_containment_rejects_different_drive(self):
        self.assertFalse(series_completeness._is_beneath(
            r"E:\Recordings\Show\episode.ts", r"D:\Recordings\Show"))

    def test_zero_size_file_is_rejected(self):
        media = self.media(self.source_root / "empty.ts", b"")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 0}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "zero_size")

    def test_directory_where_media_expected_is_wrong_type(self):
        directory = self.source_root / "directory.ts"
        directory.mkdir()
        self.write_metadata([self.episode()])
        self.write_history([{"path": directory, "size": None}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "wrong_type")

    def test_disallowed_extension_is_wrong_type(self):
        media = self.media(self.source_root / "episode.mp4")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": media.stat().st_size}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "wrong_type")

    def test_broken_recording_is_rejected(self):
        media = self.media(self.source_root / "broken.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 5, "broken": True}])
        checked = self.evaluate()["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "broken_recording")

    def test_recorded_size_mismatch_is_unknown(self):
        media = self.media(self.source_root / "mismatch.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 99}])
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["expected_candidates"][0]["acquired"]["state"], "unknown")

    def test_inaccessible_authorized_root_is_unknown(self):
        self.write_metadata([self.episode()])
        history_path = self.source_root / "recorded.ts"
        self.write_history([{"path": history_path, "size": 5}])
        shutil.rmtree(self.source_root)
        report = self.evaluate()
        checked = report["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "inaccessible")
        self.assertEqual(report["status"], "unknown")

    def test_inaccessible_child_path_with_valid_root_is_unknown(self):
        media = self.media(self.source_root / "inaccessible.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": media.stat().st_size}])

        def resolve_for_test(path):
            path = Path(path)
            if path == media:
                raise PermissionError("simulated inaccessible child")
            return path.resolve()

        with mock.patch.object(series_completeness, "_resolve_existing_path",
                               side_effect=resolve_for_test):
            report = self.evaluate()
        checked = report["expected_candidates"][0]["retained_paths_checked"]
        self.assertEqual(checked[0]["verification"], "inaccessible")
        self.assertEqual(report["expected_candidates"][0]["acquired"]["state"], "unknown")

    def test_provider_ids_are_optional(self):
        media = self.media(self.source_root / "no-id.ts")
        self.write_metadata([self.episode(ids=None)])
        self.write_history([{"path": media, "size": 5}])
        self.assertEqual(self.evaluate()["status"], "complete")

    def test_exact_correct_metadata_series_is_accepted(self):
        media = self.media(self.source_root / "correct-series.ts")
        self.write_metadata([self.episode()], series_name=self.series)
        self.write_history([{"path": media, "size": media.stat().st_size}])
        report = self.evaluate()
        self.assertEqual(report["status"], "complete")
        self.assertIsNone(report["inputs"]["merged_metadata"]["error"])

    def test_wrong_series_metadata_is_unknown_and_not_evaluated(self):
        self.write_metadata([self.episode()], series_name="Different Series")
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertIn("wrong_series_metadata", " ".join(report["status_reasons"]))
        self.assertEqual(report["expected_candidates"], [])

    def test_missing_history_is_unknown_not_fabricated_missing(self):
        self.write_metadata([self.episode()])
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_malformed_history_is_unknown(self):
        self.write_metadata([self.episode()])
        self.resolved["history_path"].parent.mkdir(parents=True, exist_ok=True)
        self.resolved["history_path"].write_text("{bad", encoding="utf-8")
        self.assertEqual(self.evaluate()["status"], "unknown")

    def test_structurally_malformed_history_is_unknown(self):
        self.write_metadata([self.episode()])
        self.resolved["history_path"].parent.mkdir(parents=True, exist_ok=True)
        self.resolved["history_path"].write_text(json.dumps({
            "schema_version": 1,
            "series": {"name": self.series},
            "episodes": {"bad": {"history_episode_id": "bad"}},
            "unresolved_observations": [],
        }), encoding="utf-8")
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def _mutate_only_history_episode(self, mutation):
        history_path = self.write_history([{
            "path": self.source_root / "Pilot.ts", "size": 5}])
        history = json.loads(history_path.read_text(encoding="utf-8"))
        mutation(next(iter(history["episodes"].values())))
        history_path.write_text(json.dumps(history), encoding="utf-8")

    def test_malformed_history_current_key_is_unknown(self):
        self.write_metadata([self.episode()])
        self._mutate_only_history_episode(
            lambda episode: episode.__setitem__("current_key", "season-one"))
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_canonical_history_current_key_is_accepted(self):
        media = self.media(self.source_root / "Pilot.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": media.stat().st_size}])
        report = self.evaluate()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["expected_candidates"][0]["acquired"]["state"], "true")

    def _assert_noncanonical_history_key_is_unknown(self, current_key):
        media = self.media(self.source_root / "Pilot.ts")
        self.write_metadata([self.episode()])
        self._mutate_only_history_episode(
            lambda episode: episode.__setitem__("current_key", current_key))
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertIn("noncanonical_current_key", " ".join(report["status_reasons"]))
        candidate = report["expected_candidates"][0]
        self.assertEqual(candidate["acquired"]["state"], "unknown")
        self.assertFalse(candidate["definitely_missing"])
        self.assertTrue(media.exists())

    def test_history_current_key_s001e001_is_rejected(self):
        self._assert_noncanonical_history_key_is_unknown("S001E001")

    def test_history_current_key_s01e001_is_rejected(self):
        self._assert_noncanonical_history_key_is_unknown("S01E001")

    def test_history_current_key_s001e01_is_rejected(self):
        self._assert_noncanonical_history_key_is_unknown("S001E01")

    def test_malformed_history_broken_type_is_unknown(self):
        self.write_metadata([self.episode()])
        self._mutate_only_history_episode(
            lambda episode: episode["recordings"][0].__setitem__("broken", "false"))
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_malformed_history_size_type_is_unknown(self):
        self.write_metadata([self.episode()])
        self._mutate_only_history_episode(
            lambda episode: episode["recordings"][0].__setitem__("size", "5"))
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_history_season_episode_inconsistency_is_unknown(self):
        self.write_metadata([self.episode()])
        self._mutate_only_history_episode(
            lambda episode: episode.__setitem__("episode_number", 2))
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_wrong_series_history_is_unknown(self):
        self.write_metadata([self.episode()])
        history_path = self.write_history([])
        history = json.loads(history_path.read_text(encoding="utf-8"))
        history["series"]["name"] = "Different Series"
        history_path.write_text(json.dumps(history), encoding="utf-8")
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertIn("series_mismatch", " ".join(report["status_reasons"]))

    def test_malformed_history_path_entry_is_unknown(self):
        self.write_metadata([self.episode()])
        history_path = self.write_history([{"path": self.source_root / "Pilot.ts", "size": 5}])
        history = json.loads(history_path.read_text(encoding="utf-8"))
        next(iter(history["episodes"].values()))["recordings"][0]["paths"] = ["bad"]
        history_path.write_text(json.dumps(history), encoding="utf-8")
        report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["expected_candidates"][0]["definitely_missing"])

    def test_malformed_nonempty_air_date_is_unknown(self):
        self.write_metadata([self.episode(air_date={"tmdb": "not-a-date"})])
        self.write_history([])
        candidate = self.evaluate()["expected_candidates"][0]
        self.assertEqual(candidate["eligibility"]["state"], "unknown")
        self.assertEqual(candidate["eligibility"]["reason"],
                         "malformed_nonempty_air_date")

    def test_missing_and_malformed_metadata_are_unknown(self):
        self.write_history([])
        self.assertEqual(self.evaluate()["status"], "unknown")
        self.resolved["merged_metadata_path"].parent.mkdir(parents=True, exist_ok=True)
        self.resolved["merged_metadata_path"].write_text("{bad", encoding="utf-8")
        self.assertEqual(self.evaluate()["status"], "unknown")

    def test_input_mtime_change_forces_unknown(self):
        media = self.media(self.source_root / "Pilot.ts")
        self.write_metadata([self.episode()])
        self.write_history([{"path": media, "size": 5}])
        with mock.patch.object(series_completeness, "_stat_mtime",
                               side_effect=[1, 2, 3, 2]):
            report = self.evaluate()
        self.assertEqual(report["status"], "unknown")
        self.assertIn("input_changed_during_evaluation", report["status_reasons"])

    def test_find_missing_compatibility_projection(self):
        self.write_metadata([self.episode(), self.episode(number=2, air_date=None)])
        self.write_history([])
        report = self.evaluate()
        projection = series_completeness.compatibility_projection(report)
        self.assertEqual(projection["status"], "incomplete")
        self.assertEqual([item["current_key"] for item in projection["missing_episodes"]],
                         ["S01E01"])
        self.assertIn("completeness.json", projection["notice"])
        self.assertFalse(projection["missing_list_exhaustive"])

    def test_definite_missing_plus_unknown_stays_incomplete_and_not_exhaustive(self):
        self.write_metadata([self.episode(), self.episode(number=2, air_date=None)])
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(any("eligibility_unknown" in reason
                            for reason in report["status_reasons"]))
        projection = series_completeness.compatibility_projection(report)
        self.assertFalse(projection["missing_list_exhaustive"])

    def test_only_definite_missing_projection_is_exhaustive(self):
        self.write_metadata([self.episode()])
        self.write_history([])
        report = self.evaluate()
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(series_completeness.compatibility_projection(
            report)["missing_list_exhaustive"])

    def test_find_missing_command_uses_canonical_engine(self):
        compatibility_path = self.root / "compatibility_missing.json"
        report = {
            "series": self.series,
            "status": "unknown",
            "output_path": str(self.resolved["output_path"]),
            "compatibility_output_path": str(compatibility_path),
            "expected_candidates": [],
        }
        with mock.patch.object(find_missing_episodes, "parse_args",
                               return_value=SimpleNamespace(series_name=self.series)), \
             mock.patch.object(find_missing_episodes, "evaluate_series_completeness",
                               return_value=report) as evaluate:
            find_missing_episodes.main()
        evaluate.assert_called_once_with(self.series)
        projection = json.loads(compatibility_path.read_text(encoding="utf-8"))
        self.assertEqual(projection["status"], "unknown")
        self.assertFalse(projection["missing_list_exhaustive"])

    def test_configured_roots_control_all_production_paths(self):
        self.assertEqual(self.resolved["source_root"], self.source_root)
        self.assertEqual(self.resolved["library_root"], self.tv_root / self.series)
        self.assertEqual(self.resolved["quarantine_root"], self.quarantine_root / self.series)
        self.assertEqual(self.resolved["output_path"], self.tv_root / self.series /
                         ".media_organizer" / "completeness.json")

    def test_atomic_output_preserves_prior_file_when_replace_fails(self):
        output = self.root / "atomic.json"
        output.write_text('{"prior": true}\n', encoding="utf-8")
        before = output.read_bytes()
        with mock.patch.object(series_completeness.os, "replace",
                               side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                series_completeness.atomic_write_json(output, {"new": True})
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
