#!/usr/bin/env python3
"""
tests/test_book_editor.py — Unit tests for common/book_editor.py (TASK-90).
"""

import json
import os
import tempfile
import unittest

from common.book_editor import (
    check_artifacts,
    check_structure,
    run_deterministic_checks,
)


class TestBookEditor(unittest.TestCase):

    def test_artifact_loss_detected(self):
        """Test 1 — artifact_loss detected when code span/version disappears."""
        source = "Run `pip install requests==2.28.0` to install."
        humanized = "Install the requests library to get started."
        chapter = "ch01_intro.md"
        para_index = 3

        flags = check_artifacts(source, humanized, chapter, para_index)
        self.assertEqual(len(flags), 1)
        flag = flags[0]

        self.assertTrue(flag["flag_id"].startswith("bef_"))
        self.assertEqual(len(flag["flag_id"]), 16)  # "bef_" + 12 hex chars
        self.assertEqual(flag["chapter"], chapter)
        self.assertEqual(flag["para_index"], para_index)
        self.assertEqual(flag["category"], "artifact_loss")
        self.assertGreaterEqual(flag["severity"], 1)
        self.assertLessEqual(flag["severity"], 5)
        self.assertEqual(flag["source_excerpt"], source)
        self.assertEqual(flag["humanized_excerpt"], humanized)
        self.assertEqual(flag["detector"], "deterministic")
        self.assertIsNone(flag["suggested_rewrite"])
        self.assertIsNone(flag["editor_model"])

    def test_clean_pass(self):
        """Test 2 — clean pass (no flags) when source and humanized match code/structure."""
        source = "# Overview\nRun `pip install requests` to install."
        humanized = "# Overview\nExecute `pip install requests` to get started."
        chapter = "ch01_intro.md"
        para_index = 0

        flags = run_deterministic_checks(source, humanized, chapter, para_index)
        self.assertEqual(flags, [])

    def test_structural_drift_detected(self):
        """Test 3 — structural_drift detected when heading counts differ."""
        source = "# Section 1\n## Subsection 1.1\n### Sub-subsection 1.1.1\nDetailed content."
        humanized = "# Combined Section\nDetailed content."
        chapter = "ch02_details.md"
        para_index = 1

        flags = check_structure(source, humanized, chapter, para_index)
        self.assertEqual(len(flags), 1)
        flag = flags[0]

        self.assertTrue(flag["flag_id"].startswith("bef_"))
        self.assertEqual(flag["chapter"], chapter)
        self.assertEqual(flag["para_index"], para_index)
        self.assertEqual(flag["category"], "structural_drift")
        self.assertEqual(flag["severity"], 4)  # 4 because heading count differs
        self.assertEqual(flag["detector"], "deterministic")

    def test_atomic_flag_file_writing(self):
        """Test atomic writing and appending of flags to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flags_path = os.path.join(tmpdir, "book_editor_flags.json")
            source = "Run `pip install requests==2.28.0` to install."
            humanized = "Install the requests library to get started."

            # First run - creates file
            new_flags1 = run_deterministic_checks(source, humanized, "ch01.md", 0, flags_path)
            self.assertEqual(len(new_flags1), 1)
            self.assertTrue(os.path.exists(flags_path))

            with open(flags_path, "r", encoding="utf-8") as f:
                data1 = json.load(f)
            self.assertEqual(len(data1), 1)

            # Second run - appends to file
            source2 = "# Title 1\n# Title 2\nContent"
            humanized2 = "# Single Title\nContent"
            new_flags2 = run_deterministic_checks(source2, humanized2, "ch02.md", 5, flags_path)
            self.assertEqual(len(new_flags2), 1)

            with open(flags_path, "r", encoding="utf-8") as f:
                data2 = json.load(f)
            self.assertEqual(len(data2), 2)
            self.assertEqual(data2[0]["category"], "artifact_loss")
            self.assertEqual(data2[1]["category"], "structural_drift")


if __name__ == "__main__":
    unittest.main()
