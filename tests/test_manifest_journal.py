import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import file_organizer


TEST_ROOT = Path(r"E:\MediaOrganizerWork\Test")


class ManifestJournalTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp_context = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temp_context.name)
        self.source = self.root / "source"
        self.library = self.root / "library"
        self.preview = self.root / "preview"
        self.quarantine = self.root / "quarantine"
        self.source.mkdir()
        self.library.mkdir()

    def tearDown(self):
        self.temp_context.cleanup()

    def episode(self, files, episode_number=1):
        return {
            "season_number": 1,
            "episode_number": episode_number,
            "titles": {"test": "Pilot"},
            "overviews": {"test": "Overview"},
            "files": [
                {"path": str(path), "size": path.stat().st_size, "broken": False}
                for path in files
            ],
        }

    def latest_path(self):
        return self.quarantine / "Test Series" / "file_organizer_manifest.json"

    def latest(self):
        return json.loads(self.latest_path().read_text(encoding="utf-8"))

    def organize(self, episodes, move=True):
        file_organizer.organize_files(
            "Test Series", episodes, str(self.library), move, {}, ["test"],
            preview_root=self.preview, quarantine_root=self.quarantine)

    def test_selected_physical_move_is_checkpointed_before_history_write(self):
        selected = self.source / "Selected.ts"
        selected.write_bytes(b"selected-recording")
        real_history_write = file_organizer.atomic_write_history
        history_writes = 0

        def inspect_selected_checkpoint(path, history):
            nonlocal history_writes
            history_writes += 1
            if history_writes == 2:
                action = self.latest()["actions"][0]
                self.assertEqual(action["status"], "moved_and_verified")
                self.assertTrue(action["physical_action_succeeded"])
                self.assertFalse(action["history_recorded"])
                self.assertTrue(Path(action["actual_destination"]).is_file())
            return real_history_write(path, history)

        with mock.patch.object(file_organizer, "atomic_write_history",
                               side_effect=inspect_selected_checkpoint):
            self.organize([self.episode([selected])])
        self.assertEqual(history_writes, 2)

    def test_quarantine_physical_move_is_checkpointed_before_history_write(self):
        selected = self.source / "Selected.ts"
        rejected = self.source / "Rejected.ts"
        selected.write_bytes(b"selected-recording")
        rejected.write_bytes(b"rejected")
        real_history_write = file_organizer.atomic_write_history
        history_writes = 0

        def inspect_quarantine_checkpoint(path, history):
            nonlocal history_writes
            history_writes += 1
            if history_writes == 3:
                quarantine_action = self.latest()["actions"][0]["quarantined"][0]
                self.assertEqual(quarantine_action["status"], "physical_quarantine_succeeded")
                self.assertTrue(quarantine_action["physical_action_succeeded"])
                self.assertFalse(quarantine_action["history_recorded"])
                self.assertTrue(Path(quarantine_action["actual_destination"]).is_file())
            return real_history_write(path, history)

        with mock.patch.object(file_organizer, "atomic_write_history",
                               side_effect=inspect_quarantine_checkpoint):
            self.organize([self.episode([selected, rejected])])
        self.assertEqual(history_writes, 3)

    def test_failure_between_selected_move_and_history_leaves_durable_evidence(self):
        selected = self.source / "Selected.ts"
        alternate = self.source / "Alternate.ts"
        selected.write_bytes(b"selected-recording")
        alternate.write_bytes(b"alt")
        real_history_write = file_organizer.atomic_write_history
        history_writes = 0

        def interrupt_before_selected_history(path, history):
            nonlocal history_writes
            history_writes += 1
            if history_writes == 2:
                raise KeyboardInterrupt("simulated abrupt stop")
            return real_history_write(path, history)

        with mock.patch.object(file_organizer, "atomic_write_history",
                               side_effect=interrupt_before_selected_history):
            with self.assertRaises(KeyboardInterrupt):
                self.organize([self.episode([selected, alternate])])
        action = self.latest()["actions"][0]
        self.assertEqual(action["status"], "moved_and_verified")
        self.assertTrue(action["physical_action_succeeded"])
        self.assertFalse(action["history_recorded"])
        self.assertTrue(Path(action["actual_destination"]).is_file())
        self.assertTrue(alternate.exists())

    def test_checkpoint_failure_after_selected_move_stops_later_cleanup(self):
        selected = self.source / "Selected.ts"
        selected_xml = self.source / "Selected.xml"
        alternate = self.source / "Alternate.ts"
        alternate_xml = self.source / "Alternate.xml"
        selected.write_bytes(b"selected-recording")
        selected_xml.write_text("selected sidecar", encoding="utf-8")
        alternate.write_bytes(b"alt")
        alternate_xml.write_text("alternate sidecar", encoding="utf-8")
        real_checkpoint = file_organizer.checkpoint_action_manifest
        checkpoints = 0

        def fail_physical_checkpoint(manifest, run_path, latest_path):
            nonlocal checkpoints
            checkpoints += 1
            if checkpoints == 2:
                raise OSError("simulated checkpoint failure")
            return real_checkpoint(manifest, run_path, latest_path)

        with mock.patch.object(file_organizer, "checkpoint_action_manifest",
                               side_effect=fail_physical_checkpoint):
            with self.assertRaises(OSError):
                self.organize([self.episode([selected, alternate])])
        self.assertTrue(selected_xml.exists())
        self.assertTrue(alternate.exists())
        self.assertTrue(alternate_xml.exists())
        self.assertFalse(any(path.suffix in {".ts", ".xml"}
                             for path in self.quarantine.rglob("*")
                             if "manifests" not in path.parts))

    def test_failed_run_journal_replace_preserves_prior_checkpoint(self):
        manifest, run_path, latest_path = file_organizer.create_action_manifest(
            "Test Series", True, self.quarantine)
        file_organizer.checkpoint_action_manifest(manifest, run_path, latest_path)
        prior_bytes = run_path.read_bytes()
        manifest["actions"].append({"episode": "S01E01", "status": "new"})
        real_replace = file_organizer.os.replace

        def fail_run_replace(source, destination):
            if Path(destination) == run_path:
                raise OSError("simulated run journal replace failure")
            return real_replace(source, destination)

        with mock.patch.object(file_organizer.os, "replace", side_effect=fail_run_replace):
            with self.assertRaises(OSError):
                file_organizer.checkpoint_action_manifest(manifest, run_path, latest_path)
        self.assertEqual(run_path.read_bytes(), prior_bytes)

    def test_multiple_runs_retain_distinct_run_journals(self):
        first = self.source / "First.ts"
        first.write_bytes(b"first")
        self.organize([self.episode([first])], move=False)
        first_latest = json.loads(
            (self.preview / "Test Series" / "file_organizer_manifest.json").read_text(
                encoding="utf-8"))
        second = self.source / "Second.ts"
        second.write_bytes(b"second")
        self.organize([self.episode([second], episode_number=2)], move=False)
        second_latest = json.loads(
            (self.preview / "Test Series" / "file_organizer_manifest.json").read_text(
                encoding="utf-8"))
        journals = list((self.preview / "Test Series" / "manifests").glob("*.json"))
        self.assertEqual(len(journals), 2)
        self.assertNotEqual(first_latest["run_id"], second_latest["run_id"])
        retained_ids = {
            json.loads(path.read_text(encoding="utf-8"))["run_id"] for path in journals
        }
        self.assertEqual(retained_ids, {first_latest["run_id"], second_latest["run_id"]})


if __name__ == "__main__":
    unittest.main()
