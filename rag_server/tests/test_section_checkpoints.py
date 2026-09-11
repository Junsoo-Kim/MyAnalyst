import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import section_checkpoints


class SectionCheckpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "checkpoints.sqlite3")
        self._patched = os.environ.get("SECTION_CHECKPOINT_DB_PATH")
        os.environ["SECTION_CHECKPOINT_DB_PATH"] = self._db_path

    def tearDown(self):
        if self._patched is None:
            os.environ.pop("SECTION_CHECKPOINT_DB_PATH", None)
        else:
            os.environ["SECTION_CHECKPOINT_DB_PATH"] = self._patched
        self._tmp.cleanup()

    def test_missing_job_returns_empty(self):
        self.assertEqual(section_checkpoints.load_sections("job-1"), {})

    def test_save_and_load_round_trips(self):
        section_checkpoints.save_section("job-1", "1", "본문 1")
        section_checkpoints.save_section("job-1", "2", "본문 2")
        self.assertEqual(
            section_checkpoints.load_sections("job-1"), {"1": "본문 1", "2": "본문 2"}
        )

    def test_saving_the_same_section_again_overwrites_it(self):
        section_checkpoints.save_section("job-1", "1", "초안")
        section_checkpoints.save_section("job-1", "1", "수정본")
        self.assertEqual(section_checkpoints.get_section("job-1", "1"), "수정본")

    def test_different_jobs_do_not_share_sections(self):
        section_checkpoints.save_section("job-a", "1", "A의 섹션")
        section_checkpoints.save_section("job-b", "1", "B의 섹션")
        self.assertEqual(section_checkpoints.get_section("job-a", "1"), "A의 섹션")
        self.assertEqual(section_checkpoints.get_section("job-b", "1"), "B의 섹션")

    def test_clear_job_removes_only_that_job(self):
        section_checkpoints.save_section("job-a", "1", "A의 섹션")
        section_checkpoints.save_section("job-b", "1", "B의 섹션")
        section_checkpoints.clear_job("job-a")
        self.assertEqual(section_checkpoints.load_sections("job-a"), {})
        self.assertEqual(section_checkpoints.load_sections("job-b"), {"1": "B의 섹션"})


if __name__ == "__main__":
    unittest.main()
