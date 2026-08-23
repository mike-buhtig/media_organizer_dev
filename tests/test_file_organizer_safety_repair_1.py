import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import file_organizer


TEST_ROOT = Path(r"E:\MediaOrganizerWork\Test")


class FileOrganizerSafetyRepairTests(unittest.TestCase):
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

    def make_episode(self):
        best = self.source / "best.ts"
        alternate = self.source / "alternate.ts"
        best.write_bytes(b"best-recording")
        alternate.write_bytes(b"alt")
        best.with_suffix(".xml").write_text("best xml", encoding="utf-8")
        alternate.with_suffix(".xml").write_text("alternate xml", encoding="utf-8")
        alternate.with_suffix(".edl").write_text("alternate edl", encoding="utf-8")
        episode = {
            "season_number": 1, "episode_number": 2,
            "titles": {"test": "Pilot"}, "overviews": {"test": "Overview"},
            "files": [
                {"path": str(best), "size": best.stat().st_size, "broken": False},
                {"path": str(alternate), "size": alternate.stat().st_size, "broken": False},
            ],
        }
        return episode, best, alternate

    def organize(self, episode, move):
        file_organizer.organize_files(
            "Test Series", [episode], str(self.library), move, {}, ["test"],
            preview_root=self.preview, quarantine_root=self.quarantine)

    def destination(self):
        return self.library / "Test Series" / "Season 01" / "Test Series - S01E02 - Pilot.ts"

    def preview_nfo(self):
        return self.preview / "Test Series" / "Season 01" / "Test Series - S01E02 - Pilot.nfo"

    def test_preview_creates_expected_nfo_and_manifest_structure(self):
        episode, _, _ = self.make_episode()
        self.organize(episode, False)
        self.assertTrue(self.preview_nfo().is_file())
        manifest = json.loads((self.preview / "Test Series" / "file_organizer_manifest.json").read_text())
        self.assertEqual(manifest["actions"][0]["status"], "preview")
        self.assertEqual(Path(manifest["actions"][0]["destination"]), self.destination())

    def test_preview_preserves_source_media_and_sidecars(self):
        episode, best, alternate = self.make_episode()
        before = {path: path.read_bytes() for path in self.source.iterdir()}
        self.organize(episode, False)
        self.assertEqual(before, {path: path.read_bytes() for path in self.source.iterdir()})
        self.assertTrue(best.exists())
        self.assertTrue(alternate.exists())

    def test_preview_does_not_write_to_real_destination(self):
        episode, _, _ = self.make_episode()
        self.organize(episode, False)
        self.assertEqual(list(self.library.rglob("*")), [])

    def test_successful_move_creates_and_verifies_destination_before_quarantine(self):
        episode, best, _ = self.make_episode()
        expected_size = best.stat().st_size
        original_quarantine = file_organizer.quarantine_file

        def asserting_quarantine(source, directory):
            self.assertTrue(self.destination().is_file())
            self.assertEqual(self.destination().stat().st_size, expected_size)
            return original_quarantine(source, directory)

        with mock.patch.object(file_organizer, "quarantine_file", side_effect=asserting_quarantine):
            self.organize(episode, True)
        self.assertTrue(self.destination().is_file())
        self.assertEqual(self.destination().stat().st_size, expected_size)

    def test_simulated_move_failure_preserves_all_sources_and_sidecars(self):
        episode, best, alternate = self.make_episode()
        with mock.patch.object(file_organizer, "move_selected_recording_with_verification",
                               return_value=(False, "move_failed: simulated", best.stat().st_size)):
            self.organize(episode, True)
        self.assertTrue(best.exists())
        self.assertTrue(alternate.exists())
        self.assertTrue(best.with_suffix(".xml").exists())
        self.assertTrue(alternate.with_suffix(".xml").exists())
        self.assertFalse(any(path.suffix in {".ts", ".xml", ".edl"} for path in self.quarantine.rglob("*")))

    def test_simulated_verification_failure_preserves_all_alternatives(self):
        episode, best, alternate = self.make_episode()
        with mock.patch.object(file_organizer, "move_selected_recording_with_verification",
                               return_value=(False, "verification_failed: simulated", best.stat().st_size)):
            self.organize(episode, True)
        self.assertTrue(best.exists())
        self.assertTrue(alternate.exists())
        self.assertTrue(alternate.with_suffix(".xml").exists())
        self.assertTrue(alternate.with_suffix(".edl").exists())
        self.assertFalse(any(path.suffix in {".ts", ".xml", ".edl"} for path in self.quarantine.rglob("*")))

    def test_destination_collision_preserves_sources_and_does_not_overwrite(self):
        episode, best, alternate = self.make_episode()
        self.destination().parent.mkdir(parents=True)
        self.destination().write_bytes(b"existing-destination")
        self.organize(episode, True)
        self.assertEqual(self.destination().read_bytes(), b"existing-destination")
        self.assertTrue(best.exists())
        self.assertTrue(alternate.exists())
        self.assertFalse(any(path.suffix in {".ts", ".xml", ".edl"} for path in self.quarantine.rglob("*")))

    def test_duplicates_and_sidecars_are_quarantined_not_deleted(self):
        episode, _, alternate = self.make_episode()
        self.organize(episode, True)
        quarantine_episode = self.quarantine / "Test Series" / "Season 01" / "S01E02"
        self.assertFalse(alternate.exists())
        self.assertTrue((quarantine_episode / "alternate.ts").is_file())
        self.assertTrue((quarantine_episode / "alternate.xml").is_file())
        self.assertTrue((quarantine_episode / "alternate.edl").is_file())


if __name__ == "__main__":
    unittest.main()
