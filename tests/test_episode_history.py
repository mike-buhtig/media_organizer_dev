import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import episode_history
from scripts import file_organizer


TEST_ROOT = Path(r"E:\MediaOrganizerWork\Test")


class EpisodeHistoryTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp_context = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temp_context.name)

    def tearDown(self):
        self.temp_context.cleanup()

    def processed_episode(self, paths, ids=None, season=1, episode=2, size=100):
        value = {
            "season_number": season, "episode_number": episode,
            "local_xml_subtitle": "Pilot", "local_xml_description": "Description",
            "matched_by_pass": 2, "titles": {"test": "Pilot"},
            "files": [{"path": path, "size": size, "broken": False} for path in paths],
        }
        if ids is not None:
            value["ids"] = ids
        return value

    def only_episode(self, history):
        self.assertEqual(len(history["episodes"]), 1)
        return next(iter(history["episodes"].values()))

    def test_first_import_from_processed_json(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\Recordings\Pilot.ts"])])
        imported = self.only_episode(history)
        self.assertEqual(imported["current_key"], "S01E02")
        self.assertTrue(imported["history_episode_id"])
        self.assertEqual(imported["recordings"][0]["paths"][0]["path"], r"D:\Recordings\Pilot.ts")

    def test_repeated_import_is_idempotent(self):
        history = episode_history.new_history("Test Series")
        processed = [self.processed_episode([r"D:\Recordings\Pilot.ts"])]
        episode_history.merge_processed_episodes(history, processed)
        first = copy.deepcopy(history)
        episode_history.merge_processed_episodes(history, processed)
        self.assertEqual(history, first)

    def test_several_paths_for_one_episode_are_several_recordings(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([
            r"D:\One\Pilot.ts", r"D:\Two\Pilot.ts", r"D:\Three\Pilot.ts"])])
        self.assertEqual(len(self.only_episode(history)["recordings"]), 3)

    def test_exact_normalized_path_recognizes_existing_recording(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\Recordings\Pilot.ts"])])
        episode_history.merge_processed_episodes(history, [self.processed_episode(["d:/recordings/PILOT.ts"])])
        imported = self.only_episode(history)
        self.assertEqual(len(imported["recordings"]), 1)
        self.assertEqual({entry["path"] for entry in imported["recordings"][0]["paths"]},
                         {r"D:\Recordings\Pilot.ts", "d:/recordings/PILOT.ts"})

    def test_same_basename_at_different_path_is_different_recording(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([
            r"D:\First\Pilot.ts", r"D:\Second\Pilot.ts"])])
        self.assertEqual(len(self.only_episode(history)["recordings"]), 2)

    def test_same_size_at_different_path_is_different_recording(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([
            r"D:\First\One.ts", r"D:\Second\Two.ts"], size=500)])
        self.assertEqual(len(self.only_episode(history)["recordings"]), 2)

    def test_historical_path_survives_later_snapshot_where_absent(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\Old\Pilot.ts"])])
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\New\Pilot.ts"])])
        paths = {entry["path"] for recording in self.only_episode(history)["recordings"]
                 for entry in recording["paths"]}
        self.assertEqual(paths, {r"D:\Old\Pilot.ts", r"D:\New\Pilot.ts"})

    def test_new_recording_appends_to_known_episode(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\Old\Pilot.ts"])])
        history_id = self.only_episode(history)["history_episode_id"]
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\Later\Pilot.ts"])])
        imported = self.only_episode(history)
        self.assertEqual(imported["history_episode_id"], history_id)
        self.assertEqual(len(imported["recordings"]), 2)

    def test_provider_ids_are_optional_and_conflicts_do_not_change_identity(self):
        history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(history, [self.processed_episode([r"D:\One.ts"])])
        history_id = self.only_episode(history)["history_episode_id"]
        episode_history.merge_processed_episodes(history, [
            self.processed_episode([r"D:\One.ts"], ids={"provider": "first"}),
            self.processed_episode([r"D:\One.ts"], ids={"provider": "conflict"})])
        imported = self.only_episode(history)
        self.assertEqual(imported["history_episode_id"], history_id)
        self.assertEqual(imported["current_key"], "S01E02")
        self.assertEqual(len(imported["observations"]), 3)

    def test_unmatched_observation_stays_outside_episode_namespace(self):
        history = episode_history.new_history("Test Series")
        unresolved = self.processed_episode([r"D:\Unknown.ts"], season="unmatched", episode=1)
        episode_history.merge_processed_episodes(history, [unresolved])
        self.assertEqual(history["episodes"], {})
        self.assertEqual(len(history["unresolved_observations"]), 1)

    def test_verified_selected_move_retains_source_and_adds_library_path(self):
        history = episode_history.new_history("Test Series")
        source = r"D:\Recordings\Pilot.ts"
        destination = r"E:\Library\Test Series\Season 01\Pilot.ts"
        episode_history.merge_processed_episodes(history, [self.processed_episode([source])])
        recording_id = episode_history.record_verified_transition(
            history, "S01E02", source, destination, "library", "verified_selected_move", selected=True)
        imported = self.only_episode(history)
        self.assertEqual(imported["selected_recording_id"], recording_id)
        self.assertEqual({path["path"] for path in imported["recordings"][0]["paths"]}, {source, destination})

    def test_verified_quarantine_retains_source_and_adds_quarantine_path(self):
        history = episode_history.new_history("Test Series")
        source = r"D:\Recordings\Duplicate.ts"
        destination = r"E:\Quarantine\Test Series\S01E02\Duplicate.ts"
        episode_history.merge_processed_episodes(history, [self.processed_episode([source])])
        episode_history.record_verified_transition(
            history, "S01E02", source, destination, "quarantine", "verified_quarantine")
        paths = self.only_episode(history)["recordings"][0]["paths"]
        self.assertEqual({path["path"] for path in paths}, {source, destination})

    def test_failed_transition_is_not_claimed(self):
        history = episode_history.new_history("Test Series")
        source = r"D:\Recordings\Pilot.ts"
        episode_history.merge_processed_episodes(history, [self.processed_episode([source])])
        before = copy.deepcopy(history)
        with self.assertRaises(KeyError):
            episode_history.record_verified_transition(
                history, "S01E02", r"D:\Other\Missing.ts", r"E:\Library\Missing.ts",
                "library", "verified_selected_move", selected=True)
        self.assertEqual(history, before)

    def test_organizer_failed_move_does_not_record_successful_transition(self):
        source_dir = self.root / "source"
        library = self.root / "library"
        source_dir.mkdir()
        library.mkdir()
        media = source_dir / "Pilot.ts"
        media.write_bytes(b"recording")
        processed = self.processed_episode([str(media)], size=media.stat().st_size)
        with mock.patch.object(file_organizer, "move_selected_recording_with_verification",
                               return_value=(False, "move_failed: simulated", media.stat().st_size)):
            file_organizer.organize_files(
                "Test Series", [processed], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")
        history = episode_history.load_history(
            library / "Test Series" / ".media_organizer" / "episode_history.json", "Test Series")
        imported = self.only_episode(history)
        self.assertIsNone(imported["selected_recording_id"])
        self.assertEqual([path["transition"] for path in imported["recordings"][0]["paths"]], ["observed"])

    def test_organizer_failed_quarantine_does_not_record_successful_transition(self):
        source_dir = self.root / "source"
        library = self.root / "library"
        source_dir.mkdir()
        library.mkdir()
        best = source_dir / "Best.ts"
        alternate = source_dir / "Alternate.ts"
        alternate_xml = source_dir / "Alternate.xml"
        best.write_bytes(b"best-recording")
        alternate.write_bytes(b"alt")
        alternate_xml.write_text("sidecar", encoding="utf-8")
        processed = self.processed_episode(
            [str(best), str(alternate)], size=alternate.stat().st_size)
        processed["files"][0]["size"] = best.stat().st_size
        original_quarantine = file_organizer.quarantine_file

        def fail_alternate(source, destination):
            if Path(source) == alternate:
                raise OSError("simulated quarantine failure")
            return original_quarantine(source, destination)

        with mock.patch.object(file_organizer, "quarantine_file", side_effect=fail_alternate):
            file_organizer.organize_files(
                "Test Series", [processed], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")
        history = episode_history.load_history(
            library / "Test Series" / ".media_organizer" / "episode_history.json", "Test Series")
        imported = self.only_episode(history)
        alternate_recording = next(
            recording for recording in imported["recordings"]
            if any(path["path"] == str(alternate) for path in recording["paths"]))
        self.assertEqual([path["transition"] for path in alternate_recording["paths"]], ["observed"])
        self.assertTrue(alternate.exists())
        self.assertTrue(alternate_xml.exists())
        manifest = json.loads((self.root / "quarantine" / "Test Series" /
                               "file_organizer_manifest.json").read_text(encoding="utf-8"))
        failed = manifest["actions"][0]["quarantined"][0]
        self.assertEqual(failed["status"], "physical_quarantine_failed")
        self.assertFalse(failed["physical_action_succeeded"])
        self.assertFalse(failed["history_recorded"])
        self.assertIsNone(failed["actual_destination"])
        self.assertTrue(manifest["actions"][0]["cleanup_stopped"])

    def test_preview_writes_proposal_without_production_history(self):
        source_dir = self.root / "source"
        library = self.root / "library"
        preview = self.root / "preview"
        quarantine = self.root / "quarantine"
        source_dir.mkdir()
        library.mkdir()
        media = source_dir / "Pilot.ts"
        media.write_bytes(b"recording")
        processed = self.processed_episode([str(media)], size=media.stat().st_size)
        file_organizer.organize_files(
            "Test Series", [processed], str(library), False, {}, ["test"],
            preview_root=preview, quarantine_root=quarantine)
        self.assertFalse((library / "Test Series" / ".media_organizer" / "episode_history.json").exists())
        self.assertTrue((preview / "Test Series" / ".media_organizer" / "episode_history.json").is_file())

    def test_failed_atomic_write_preserves_previous_valid_history(self):
        history_path = self.root / "episode_history.json"
        original = episode_history.new_history("Test Series")
        episode_history.atomic_write_history(history_path, original)
        original_bytes = history_path.read_bytes()
        changed = copy.deepcopy(original)
        episode_history.merge_processed_episodes(changed, [self.processed_episode([r"D:\Recordings\Pilot.ts"])])
        with mock.patch.object(episode_history.os, "replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                episode_history.atomic_write_history(history_path, changed)
        self.assertEqual(history_path.read_bytes(), original_bytes)
        episode_history.validate_history(json.loads(history_path.read_text(encoding="utf-8")))

    def test_real_selected_move_helper_reports_shutil_move_failure(self):
        source = self.root / "source.ts"
        destination = self.root / "destination.ts"
        source.write_bytes(b"recording")
        with mock.patch.object(file_organizer.shutil, "move",
                               side_effect=OSError("simulated shutil failure")):
            verified, status, expected_size = (
                file_organizer.move_selected_recording_with_verification(source, destination))
        self.assertFalse(verified)
        self.assertTrue(status.startswith("move_failed:"))
        self.assertEqual(expected_size, len(b"recording"))
        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())

    def test_real_selected_move_helper_reports_destination_size_mismatch(self):
        source = self.root / "source.ts"
        destination = self.root / "destination.ts"
        source.write_bytes(b"recording")

        def wrong_size_move(source_text, destination_text):
            Path(destination_text).write_bytes(b"x")
            Path(source_text).unlink()

        with mock.patch.object(file_organizer.shutil, "move", side_effect=wrong_size_move):
            verified, status, expected_size = (
                file_organizer.move_selected_recording_with_verification(source, destination))
        self.assertFalse(verified)
        self.assertTrue(status.startswith("verification_failed:"))
        self.assertEqual(expected_size, len(b"recording"))
        self.assertEqual(destination.read_bytes(), b"x")

    def test_verification_failure_stops_duplicate_quarantine(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        library = self.root / "library"
        best = source_dir / "Best.ts"
        alternate = source_dir / "Alternate.ts"
        best.write_bytes(b"best-recording")
        alternate.write_bytes(b"alt")
        processed = self.processed_episode([str(best), str(alternate)], size=3)
        processed["files"][0]["size"] = best.stat().st_size
        original_move = file_organizer.shutil.move

        def wrong_size_selected_move(source_text, destination_text):
            if Path(source_text) == best:
                Path(destination_text).write_bytes(b"x")
                Path(source_text).unlink()
                return str(destination_text)
            return original_move(source_text, destination_text)

        with mock.patch.object(file_organizer.shutil, "move", side_effect=wrong_size_selected_move):
            file_organizer.organize_files(
                "Test Series", [processed], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")
        self.assertTrue(alternate.exists())
        manifest = json.loads((self.root / "quarantine" / "Test Series" /
                               "file_organizer_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["actions"][0]["status"].startswith("verification_failed:"))
        self.assertFalse(manifest["actions"][0]["history_recorded"])
        self.assertEqual(manifest["actions"][0]["quarantined"], [])

    def test_selected_history_failure_stops_cleanup_and_cannot_leak(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        library = self.root / "library"
        first_best = source_dir / "FirstBest.ts"
        first_sidecar = source_dir / "FirstBest.xml"
        first_alternate = source_dir / "FirstAlternate.ts"
        second_best = source_dir / "SecondBest.ts"
        first_best.write_bytes(b"first-best-recording")
        first_sidecar.write_text("sidecar", encoding="utf-8")
        first_alternate.write_bytes(b"alt")
        second_best.write_bytes(b"second-best")
        first = self.processed_episode([str(first_best), str(first_alternate)], season=1,
                                       episode=1, size=3)
        first["files"][0]["size"] = first_best.stat().st_size
        second = self.processed_episode([str(second_best)], season=1, episode=2,
                                        size=second_best.stat().st_size)
        real_atomic_write = file_organizer.atomic_write_history
        write_count = 0

        def fail_first_transition(path, history):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("selected history unavailable")
            return real_atomic_write(path, history)

        with mock.patch.object(file_organizer, "atomic_write_history",
                               side_effect=fail_first_transition):
            file_organizer.organize_files(
                "Test Series", [first, second], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")

        self.assertTrue(first_sidecar.exists())
        self.assertTrue(first_alternate.exists())
        durable = episode_history.load_history(
            library / "Test Series" / ".media_organizer" / "episode_history.json", "Test Series")
        first_history = episode_history.find_episode_by_key(durable, "S01E01")
        self.assertIsNone(first_history["selected_recording_id"])
        first_paths = {path["path"] for recording in first_history["recordings"]
                       for path in recording["paths"]}
        self.assertNotIn(str(library / "Test Series" / "Season 01" /
                             "Test Series - S01E01 - Pilot.ts"), first_paths)
        self.assertIsNotNone(
            episode_history.find_episode_by_key(durable, "S01E02")["selected_recording_id"])
        manifest = json.loads((self.root / "quarantine" / "Test Series" /
                               "file_organizer_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["actions"][0]["status"],
                         "selected_move_succeeded_history_write_failed")
        self.assertTrue(manifest["actions"][0]["physical_action_succeeded"])
        self.assertFalse(manifest["actions"][0]["history_recorded"])
        self.assertEqual(manifest["actions"][0]["quarantined"], [])

    def test_quarantine_history_failure_stops_cleanup_and_cannot_leak(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        library = self.root / "library"
        best = source_dir / "Best.ts"
        rejected = source_dir / "Rejected.ts"
        rejected_xml = source_dir / "Rejected.xml"
        later_rejected = source_dir / "LaterRejected.ts"
        second_best = source_dir / "SecondBest.ts"
        best.write_bytes(b"best-recording")
        rejected.write_bytes(b"rejected")
        rejected_xml.write_text("sidecar", encoding="utf-8")
        later_rejected.write_bytes(b"later")
        second_best.write_bytes(b"second-best")
        first = self.processed_episode(
            [str(best), str(rejected), str(later_rejected)], season=1, episode=1, size=1)
        first["files"][0]["size"] = best.stat().st_size
        first["files"][1]["size"] = rejected.stat().st_size
        first["files"][2]["size"] = later_rejected.stat().st_size
        second = self.processed_episode([str(second_best)], season=1, episode=2,
                                        size=second_best.stat().st_size)
        real_atomic_write = file_organizer.atomic_write_history
        write_count = 0

        def fail_quarantine_transition(path, history):
            nonlocal write_count
            write_count += 1
            if write_count == 3:
                raise OSError("quarantine history unavailable")
            return real_atomic_write(path, history)

        with mock.patch.object(file_organizer, "atomic_write_history",
                               side_effect=fail_quarantine_transition):
            file_organizer.organize_files(
                "Test Series", [first, second], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")

        quarantine_dir = self.root / "quarantine" / "Test Series" / "Season 01" / "S01E01"
        self.assertTrue((quarantine_dir / rejected.name).exists())
        self.assertTrue(rejected_xml.exists())
        self.assertTrue(later_rejected.exists())
        durable = episode_history.load_history(
            library / "Test Series" / ".media_organizer" / "episode_history.json", "Test Series")
        rejected_recording = next(
            recording for recording in episode_history.find_episode_by_key(
                durable, "S01E01")["recordings"]
            if any(path["path"] == str(rejected) for path in recording["paths"]))
        self.assertNotIn(str(quarantine_dir / rejected.name),
                         {path["path"] for path in rejected_recording["paths"]})
        self.assertIsNotNone(
            episode_history.find_episode_by_key(durable, "S01E02")["selected_recording_id"])
        manifest = json.loads((self.root / "quarantine" / "Test Series" /
                               "file_organizer_manifest.json").read_text(encoding="utf-8"))
        quarantine_action = manifest["actions"][0]["quarantined"][0]
        self.assertEqual(quarantine_action["status"],
                         "physical_quarantine_succeeded_history_write_failed")
        self.assertTrue(quarantine_action["physical_action_succeeded"])
        self.assertFalse(quarantine_action["history_recorded"])
        self.assertEqual(quarantine_action["actual_destination"],
                         str(quarantine_dir / rejected.name))

    def test_selected_sidecar_failure_stops_duplicate_cleanup(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        library = self.root / "library"
        best = source_dir / "Best.ts"
        best_xml = source_dir / "Best.xml"
        best_edl = source_dir / "Best.edl"
        alternate = source_dir / "Alternate.ts"
        alternate_xml = source_dir / "Alternate.xml"
        best.write_bytes(b"best-recording")
        best_xml.write_text("xml", encoding="utf-8")
        best_edl.write_text("edl", encoding="utf-8")
        alternate.write_bytes(b"alt")
        alternate_xml.write_text("alt xml", encoding="utf-8")
        processed = self.processed_episode([str(best), str(alternate)], size=3)
        processed["files"][0]["size"] = best.stat().st_size
        original_move = file_organizer.shutil.move

        def fail_selected_xml(source_text, destination_text):
            if Path(source_text) == best_xml:
                raise OSError("selected sidecar failure")
            return original_move(source_text, destination_text)

        with mock.patch.object(file_organizer.shutil, "move", side_effect=fail_selected_xml):
            file_organizer.organize_files(
                "Test Series", [processed], str(library), True, {}, ["test"],
                preview_root=self.root / "preview", quarantine_root=self.root / "quarantine")
        self.assertTrue(best_xml.exists())
        self.assertTrue(best_edl.exists())
        self.assertTrue(alternate.exists())
        self.assertTrue(alternate_xml.exists())
        manifest = json.loads((self.root / "quarantine" / "Test Series" /
                               "file_organizer_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["actions"][0]["status"], "selected_sidecar_move_failed")
        self.assertTrue(manifest["actions"][0]["cleanup_stopped"])
        self.assertEqual(manifest["actions"][0]["selected_sidecars"][0]["status"],
                         "selected_sidecar_move_failed")
        self.assertEqual(manifest["actions"][0]["quarantined"], [])

    def test_atomic_manifest_replace_failure_preserves_prior_manifest(self):
        manifest_path = self.root / "manifest.json"
        original = {
            "schema_version": 2, "run_id": "prior", "started_at": "start",
            "updated_at": "update", "series": "Test Series", "mode": "move",
            "run_status": "in_progress",
            "actions": [{"episode": "S01E01", "status": "prior-valid"}],
        }
        file_organizer.write_action_manifest(manifest_path, original)
        original_bytes = manifest_path.read_bytes()
        with mock.patch.object(file_organizer.os, "replace",
                               side_effect=OSError("simulated manifest replace failure")):
            with self.assertRaises(OSError):
                file_organizer.write_action_manifest(
                    manifest_path, {**original, "actions": [
                        {"episode": "S01E01", "status": "replacement"}]})
        self.assertEqual(manifest_path.read_bytes(), original_bytes)
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
