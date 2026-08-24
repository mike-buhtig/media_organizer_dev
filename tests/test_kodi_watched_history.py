import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import episode_history, kodi_watched_history


TEST_ROOT = Path(r"E:\MediaOrganizerWork\Test")


class KodiWatchedHistoryTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp_context = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temp_context.name)
        self.history = episode_history.new_history("Test Series")
        episode_history.merge_processed_episodes(self.history, [{
            "season_number": 1,
            "episode_number": 1,
            "files": [{"path": r"D:\Recordings\Pilot.ts", "size": 10, "broken": False}],
        }])

    def tearDown(self):
        self.temp_context.cleanup()

    def make_db(self, name, rows):
        database = self.root / name
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE path (idPath INTEGER PRIMARY KEY, strPath TEXT);
            CREATE TABLE files (
                idFile INTEGER PRIMARY KEY,
                idPath INTEGER,
                strFilename TEXT,
                playCount NUMERIC,
                lastPlayed TEXT
            );
        """)
        path_ids = {}
        for directory, filename, play_count, last_played in rows:
            if directory not in path_ids:
                cursor = connection.execute("INSERT INTO path(strPath) VALUES (?)", (directory,))
                path_ids[directory] = cursor.lastrowid
            connection.execute(
                "INSERT INTO files(idPath, strFilename, playCount, lastPlayed) VALUES (?, ?, ?, ?)",
                (path_ids[directory], filename, play_count, last_played))
        connection.commit()
        connection.close()
        return database

    def extract(self, database, device="living_room", observed_at="2026-08-24T12:00:00Z",
                include_zero=False):
        return kodi_watched_history.extract_watched_observations(
            database, device, observed_at=observed_at, include_zero=include_zero)

    def only_episode(self):
        return next(iter(self.history["episodes"].values()))

    def watched_db(self, name="MyVideos131.db", path="D:\\Recordings\\",
                   filename="Pilot.ts", count=1, last_played="2025-01-01 10:00:00"):
        return self.make_db(name, [(path, filename, count, last_played)])

    def test_one_watched_full_path_maps_and_preserves_numeric_playcount(self):
        observations = self.extract(self.watched_db(count=3))
        kodi_watched_history.merge_observations_into_history(self.history, observations)
        evidence = self.only_episode()["watched_evidence"]
        self.assertEqual(evidence["observations"][0]["playCount"], 3)
        self.assertEqual(evidence["aggregate"], {
            "watched": True, "playCount": 3, "lastPlayed": "2025-01-01 10:00:00"})
        self.assertEqual(evidence["observations"][0]["match_method"], "exact_full_path")

    def test_two_databases_use_max_playcount_not_sum_and_latest_lastplayed(self):
        first = self.extract(self.watched_db("MyVideos121.db", count=2,
                                           last_played="2025-01-01 10:00:00"))
        second = self.extract(self.watched_db("MyVideos131.db", count=5,
                                            last_played="2025-02-01 10:00:00"))
        kodi_watched_history.merge_observations_into_history(self.history, first + second)
        aggregate = self.only_episode()["watched_evidence"]["aggregate"]
        self.assertEqual(aggregate["playCount"], 5)
        self.assertEqual(aggregate["lastPlayed"], "2025-02-01 10:00:00")

    def test_two_sources_and_historical_paths_accumulate_on_same_episode(self):
        episode = self.only_episode()
        recording = episode["recordings"][0]
        recording["paths"].append({
            "path": r"E:\Library\Pilot.ts",
            "normalized_path": episode_history.normalize_windows_path(r"E:\Library\Pilot.ts"),
            "kind": "library", "transition": "selected_move",
        })
        first = self.extract(self.watched_db("MyVideos121.db"), "living_room")
        second_db = self.watched_db("MyVideos131.db", "E:\\Library\\")
        second = self.extract(second_db, "bedroom")
        kodi_watched_history.merge_observations_into_history(self.history, first)
        kodi_watched_history.merge_observations_into_history(self.history, second)
        observations = episode["watched_evidence"]["observations"]
        self.assertEqual({item["source_id"] for item in observations},
                         {"kodi:living_room", "kodi:bedroom"})
        self.assertEqual(len(observations), 2)

    def test_invalid_and_null_lastplayed_are_retained_but_not_aggregated(self):
        valid = self.extract(self.watched_db("MyVideos121.db", last_played="2025-03-01 09:00:00"))
        invalid = self.extract(self.watched_db("MyVideos130.db", last_played="not-a-date"))
        null = self.extract(self.watched_db("MyVideos131.db", last_played=None))
        kodi_watched_history.merge_observations_into_history(self.history, valid + invalid + null)
        evidence = self.only_episode()["watched_evidence"]
        self.assertEqual([item["lastPlayed"] for item in evidence["observations"]],
                         ["2025-03-01 09:00:00", "not-a-date", None])
        self.assertEqual(evidence["aggregate"]["lastPlayed"], "2025-03-01 09:00:00")

    def test_explicit_zero_cannot_downgrade_prior_positive(self):
        positive = self.extract(self.watched_db("MyVideos121.db", count=4))
        zero = self.extract(self.watched_db("MyVideos131.db", count=0), include_zero=True)
        kodi_watched_history.merge_observations_into_history(self.history, positive + zero)
        aggregate = self.only_episode()["watched_evidence"]["aggregate"]
        self.assertTrue(aggregate["watched"])
        self.assertEqual(aggregate["playCount"], 4)

    def test_missing_database_creates_no_negative_evidence_or_history_file(self):
        history_path = self.root / "episode_history.json"
        result = kodi_watched_history.merge_database_into_history(
            self.root / "missing.db", "living_room", history_path, "Test Series")
        self.assertEqual(result, episode_history.new_history("Test Series"))
        self.assertFalse(history_path.exists())

    def test_stale_nonexistent_historical_path_still_matches(self):
        self.assertFalse(Path(r"D:\Recordings\Pilot.ts").exists())
        observations = self.extract(self.watched_db())
        kodi_watched_history.merge_observations_into_history(self.history, observations)
        self.assertTrue(self.only_episode()["watched_evidence"]["aggregate"]["watched"])

    def test_unmatched_path_remains_idempotently_unresolved_without_episode_identity(self):
        observations = self.extract(self.watched_db(path="D:\\Elsewhere\\"))
        kodi_watched_history.merge_observations_into_history(self.history, observations)
        kodi_watched_history.merge_observations_into_history(self.history, observations)
        unresolved = self.history["unresolved_observations"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["observation_type"], "kodi_watched")
        self.assertNotIn("matched_history_episode_id", unresolved[0])
        self.assertNotIn("current_key", unresolved[0])

    def test_duplicate_basename_does_not_false_match(self):
        observations = self.extract(self.watched_db(path="X:\\Different\\"))
        kodi_watched_history.merge_observations_into_history(self.history, observations)
        self.assertNotIn("watched_evidence", self.only_episode())
        self.assertEqual(len(self.history["unresolved_observations"]), 1)

    def test_provenance_is_complete(self):
        observation = self.extract(self.watched_db(), "operator_device")[0]
        self.assertEqual(observation["source_id"], "kodi:operator_device")
        self.assertEqual(observation["device_id"], "operator_device")
        self.assertEqual(observation["database_name"], "MyVideos131.db")
        self.assertEqual(observation["database_version"], 131)
        self.assertRegex(observation["database_fingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(observation["observed_kodi_path"], r"D:\Recordings\Pilot.ts")
        self.assertEqual(observation["observed_at"], "2026-08-24T12:00:00Z")

    def test_repeat_scan_is_idempotent_even_with_new_scan_timestamp(self):
        database = self.watched_db()
        first = self.extract(database, observed_at="2026-08-24T12:00:00Z")
        second = self.extract(database, observed_at="2026-08-25T12:00:00Z")
        self.assertEqual(first[0]["observation_id"], second[0]["observation_id"])
        kodi_watched_history.merge_observations_into_history(self.history, first + second)
        self.assertEqual(len(self.only_episode()["watched_evidence"]["observations"]), 1)

    def test_same_snapshot_under_new_filename_is_idempotent(self):
        database = self.watched_db("snapshot.db")
        renamed = self.root / "MyVideos999.db"
        renamed.write_bytes(database.read_bytes())
        first = self.extract(database)
        second = self.extract(renamed)
        self.assertEqual(first[0]["database_fingerprint"], second[0]["database_fingerprint"])
        self.assertEqual(first[0]["observation_id"], second[0]["observation_id"])
        kodi_watched_history.merge_observations_into_history(self.history, first + second)
        self.assertEqual(len(self.only_episode()["watched_evidence"]["observations"]), 1)

    def test_later_second_source_adds_without_replacing_first(self):
        database = self.watched_db()
        kodi_watched_history.merge_observations_into_history(
            self.history, self.extract(database, "first"))
        kodi_watched_history.merge_observations_into_history(
            self.history, self.extract(database, "second"))
        observations = self.only_episode()["watched_evidence"]["observations"]
        self.assertEqual([item["source_id"] for item in observations],
                         ["kodi:first", "kodi:second"])

    def test_exact_full_path_outranks_alias(self):
        other_history_id = "other-episode"
        self.history["episodes"][other_history_id] = {
            "history_episode_id": other_history_id, "current_key": "S01E02",
            "season_number": 1, "episode_number": 2, "observations": [],
            "selected_recording_id": None,
            "recordings": [{"recording_id": "other-recording", "size": 1, "broken": False,
                            "paths": [{"path": r"E:\Alias\Pilot.ts",
                                       "normalized_path": episode_history.normalize_windows_path(
                                           r"E:\Alias\Pilot.ts"),
                                       "kind": "source", "transition": "observed"}]}],
        }
        observation = self.extract(self.watched_db())[0]
        matched = kodi_watched_history.match_observation(observation, self.history, aliases=[
            {"source": "D:\\Recordings\\", "target": "E:\\Alias\\"}])
        self.assertEqual(matched["match_method"], "exact_full_path")
        self.assertEqual(matched["matched_history_episode_id"], self.only_episode()["history_episode_id"])

    def test_longest_unique_alias_maps_complete_path(self):
        database = self.watched_db(path="smb://server/share/recordings/")
        observation = self.extract(database)[0]
        aliases = [
            {"source": "smb://server/share/", "target": "Z:\\Wrong\\"},
            {"source": "smb://server/share/recordings/", "target": "D:\\Recordings\\"},
        ]
        matched = kodi_watched_history.match_observation(observation, self.history, aliases)
        self.assertEqual(matched["match_method"], "configured_prefix_alias")
        self.assertEqual(matched["matched_historical_path"], r"D:\Recordings\Pilot.ts")

    def test_ambiguous_alias_remains_unresolved(self):
        episode = self.only_episode()
        episode["recordings"][0]["paths"].append({
            "path": r"E:\Other\Pilot.ts",
            "normalized_path": episode_history.normalize_windows_path(r"E:\Other\Pilot.ts"),
            "kind": "source", "transition": "observed"})
        observation = self.extract(self.watched_db(path="smb://server/share/"))[0]
        aliases = [
            {"source": "smb://server/share/", "target": "D:\\Recordings\\"},
            {"source": "smb://server/share/", "target": "E:\\Other\\"},
        ]
        matched = kodi_watched_history.match_observation(observation, self.history, aliases)
        self.assertEqual(matched["match_method"], "ambiguous")
        self.assertNotIn("matched_history_episode_id", matched)

    def test_scheme_aware_normalization_does_not_cross_match(self):
        values = {
            "windows": r"C:\Media\Pilot.ts",
            "unc": r"\\server\share\Pilot.ts",
            "smb": "smb://server/share/Pilot.ts",
            "plugin": "plugin://example/Pilot.ts",
            "pvr": "pvr://channels/tv/Pilot.ts",
            "unknown": "custom+media://host/Pilot.ts",
        }
        normalized = {key: kodi_watched_history.normalize_kodi_path(value)
                      for key, value in values.items()}
        self.assertEqual(len(set(normalized.values())), len(values))
        self.assertTrue(normalized["windows"].startswith("windows:"))
        self.assertTrue(normalized["unc"].startswith("unc:"))
        for key in ("smb", "plugin", "pvr", "unknown"):
            self.assertTrue(normalized[key].startswith("uri:"))

    def test_non_filesystem_uri_paths_remain_opaque_and_distinct(self):
        distinct_pairs = [
            ("plugin://example/a/../b", "plugin://example/b"),
            (r"plugin://example/a\b", "plugin://example/a/b"),
            ("pvr://example/a/./b", "pvr://example/a/b"),
            ("custom+media://example/a/../b", "custom+media://example/b"),
            (r"custom+media://example/a\b", "custom+media://example/a/b"),
        ]
        for first, second in distinct_pairs:
            with self.subTest(first=first, second=second):
                self.assertNotEqual(
                    kodi_watched_history.normalize_kodi_path(first),
                    kodi_watched_history.normalize_kodi_path(second))

    def test_non_filesystem_uri_query_and_fragment_are_preserved(self):
        value = "PLUGIN://Example/a/../b?token=a%2Fb\\c#part/./two"
        self.assertEqual(
            kodi_watched_history.normalize_kodi_path(value),
            "uri:plugin://example/a/../b?token=a%2Fb\\c#part/./two")

    def test_alias_prefix_boundary_rejects_foobar_but_accepts_foo_child(self):
        alias = [{"source": "smb://server/share/foo", "target": "D:\\Recordings"}]
        rejected = self.extract(self.watched_db(
            "MyVideos130.db", path="smb://server/share/foobar/"))[0]
        accepted = self.extract(self.watched_db(
            "MyVideos131.db", path="smb://server/share/foo/"))[0]
        rejected_match = kodi_watched_history.match_observation(rejected, self.history, alias)
        accepted_match = kodi_watched_history.match_observation(accepted, self.history, alias)
        self.assertEqual(rejected_match["match_method"], "unmatched")
        self.assertNotIn("matched_history_episode_id", rejected_match)
        self.assertEqual(accepted_match["match_method"], "configured_prefix_alias")
        self.assertEqual(accepted_match["matched_historical_path"], r"D:\Recordings\Pilot.ts")

    def test_no_wal_fingerprint_and_provenance(self):
        database = self.watched_db()
        self.assertFalse(Path(f"{database}-wal").exists())
        first = kodi_watched_history.database_fingerprint(database)
        second = kodi_watched_history.database_fingerprint(database)
        self.assertEqual(first, second)
        observation = self.extract(database)[0]
        self.assertEqual(observation["database_fingerprint"], first)
        self.assertFalse(observation["database_wal_present"])
        self.assertFalse(observation["database_wal_included"])

    def test_same_main_database_with_different_wal_has_different_fingerprint(self):
        database = self.watched_db()
        wal = Path(f"{database}-wal")
        wal.write_bytes(b"first WAL snapshot")
        first = kodi_watched_history.database_fingerprint(database)
        wal.write_bytes(b"second WAL snapshot")
        second = kodi_watched_history.database_fingerprint(database)
        self.assertNotEqual(first, second)

    def test_identical_main_and_wal_copy_has_same_fingerprint(self):
        database = self.watched_db("snapshot.db")
        Path(f"{database}-wal").write_bytes(b"stable WAL snapshot")
        copied = self.root / "MyVideos999.db"
        copied.write_bytes(database.read_bytes())
        Path(f"{copied}-wal").write_bytes(Path(f"{database}-wal").read_bytes())
        self.assertEqual(
            kodi_watched_history.database_fingerprint(database),
            kodi_watched_history.database_fingerprint(copied))

    def test_snapshot_mutation_during_read_is_rejected_without_history_change(self):
        history_path = self.root / "episode_history.json"
        episode_history.atomic_write_history(history_path, self.history)
        prior_bytes = history_path.read_bytes()
        database = self.watched_db()
        stable = kodi_watched_history._capture_snapshot(database)
        changed = {**stable, "fingerprint": "sha256:" + ("0" * 64)}
        with mock.patch.object(
                kodi_watched_history, "_capture_snapshot", side_effect=[stable, changed]):
            with self.assertRaisesRegex(
                    kodi_watched_history.SnapshotChangedDuringReadError,
                    "snapshot_changed_during_read"):
                kodi_watched_history.merge_database_into_history(
                    database, "living_room", history_path, "Test Series")
        self.assertEqual(history_path.read_bytes(), prior_bytes)

    def test_null_full_path_is_skipped_and_never_authoritative(self):
        database = self.make_db("MyVideos131.db", [(None, "Pilot.ts", 2, None)])
        with self.assertWarnsRegex(RuntimeWarning, "null/non-string/empty full path"):
            observations = self.extract(database)
        self.assertEqual(observations, [])
        self.assertNotIn("watched_evidence", self.only_episode())

    def test_existing_schema_one_without_watched_evidence_remains_valid(self):
        before = copy.deepcopy(self.history)
        episode_history.validate_history(self.history)
        self.assertEqual(self.history, before)
        self.assertNotIn("watched_evidence", self.only_episode())

    def test_atomic_history_failure_preserves_prior_valid_history(self):
        history_path = self.root / "episode_history.json"
        episode_history.atomic_write_history(history_path, self.history)
        prior_bytes = history_path.read_bytes()
        database = self.watched_db()
        with mock.patch.object(kodi_watched_history, "atomic_write_history",
                               side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                kodi_watched_history.merge_database_into_history(
                    database, "living_room", history_path, "Test Series")
        self.assertEqual(history_path.read_bytes(), prior_bytes)
        episode_history.validate_history(json.loads(history_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
