#!/usr/bin/env python3
"""
tests/test_book_editor.py — Unit tests for common/book_editor.py (TASK-94).
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, Mock

import requests

from common.book_editor import (
    check_artifacts,
    check_structure,
    run_deterministic_checks,
    run_deterministic_checks_for_chapter,
    run_model_checks,
    split_paragraphs,
    _call_editor_model,
    _make_flag_id,
    EditorModelError,
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


def _fake_agent_config():
    return {
        "model_path": "~/models/qwen25-3b-editor/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        "temperature": 0.1,
        "max_tokens": 300,
        "severity_threshold": 3,
        "response_format": {"type": "json_schema", "json_schema": {"name": "editor_flag", "schema": {}}},
    }


def _mock_response(status_code=200, content=None):
    resp = Mock()
    resp.status_code = status_code
    resp.text = "error body"
    if content is not None:
        resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


class TestBookEditorModel(unittest.TestCase):
    """TASK-94 Stage 9 Part 1/2 — mocked-HTTP tests for the model-calling
    half. No real network/GPU calls; requests.post is patched."""

    def test_call_editor_model_success(self):
        content = json.dumps({"issue": "Version changed from 1.2 to 1.3, quoted exact values here.", "severity": 4})
        with patch("common.book_editor.requests.post", return_value=_mock_response(200, content)):
            verdict = _call_editor_model("source text", "humanized text", "fact_drift", _fake_agent_config())
        self.assertEqual(verdict["severity"], 4)
        self.assertIn("Version changed", verdict["issue"])

    def test_call_editor_model_http_error_raises(self):
        with patch("common.book_editor.requests.post", return_value=_mock_response(500)):
            with self.assertRaises(EditorModelError):
                _call_editor_model("s", "h", "fact_drift", _fake_agent_config())

    def test_call_editor_model_connection_error_raises(self):
        with patch("common.book_editor.requests.post", side_effect=requests.ConnectionError("refused")):
            with self.assertRaises(EditorModelError):
                _call_editor_model("s", "h", "fact_drift", _fake_agent_config())

    def test_call_editor_model_malformed_json_raises(self):
        with patch("common.book_editor.requests.post", return_value=_mock_response(200, "not json")):
            with self.assertRaises(EditorModelError):
                _call_editor_model("s", "h", "fact_drift", _fake_agent_config())

    def test_call_editor_model_missing_keys_raises(self):
        content = json.dumps({"severity": 4})  # missing "issue"
        with patch("common.book_editor.requests.post", return_value=_mock_response(200, content)):
            with self.assertRaises(EditorModelError):
                _call_editor_model("s", "h", "fact_drift", _fake_agent_config())

    def test_run_model_checks_threshold_filters_and_flag_id_deterministic(self):
        # fact_drift: severity 4 (>= threshold 3, kept). translation_hostile: severity 1 (< threshold, dropped).
        responses = [
            _mock_response(200, json.dumps({"issue": "Real fact drift found here, quoted exact values.", "severity": 4})),
            _mock_response(200, json.dumps({"issue": "Minor stylistic wobble, not really hostile at all.", "severity": 1})),
        ]
        with patch("common.book_editor.requests.post", side_effect=responses):
            flags1 = run_model_checks("src", "hum", "ch01.md", 2, _fake_agent_config())

        self.assertEqual(len(flags1), 1)
        self.assertEqual(flags1[0]["category"], "fact_drift")
        self.assertEqual(flags1[0]["detector"], "model")

        # Same inputs again -- flag_id must be identical (A.7: deterministic, not secrets.token_hex).
        responses2 = [
            _mock_response(200, json.dumps({"issue": "Real fact drift found here, quoted exact values.", "severity": 4})),
            _mock_response(200, json.dumps({"issue": "Minor stylistic wobble, not really hostile at all.", "severity": 1})),
        ]
        with patch("common.book_editor.requests.post", side_effect=responses2):
            flags2 = run_model_checks("src", "hum", "ch01.md", 2, _fake_agent_config())
        self.assertEqual(flags1[0]["flag_id"], flags2[0]["flag_id"])

    def test_run_model_checks_second_detector_failure_discards_first_result(self):
        """Locks in the CURRENT all-or-nothing behavior (Q-confirmed 'Варіант
        1'): if fact_drift succeeds and computes a real flag but
        translation_hostile then raises, the whole call raises and nothing
        is written to flags_path -- the already-computed fact_drift flag is
        not silently persisted. This test documents that this is what the
        code actually does, so a future change to this behavior is a
        deliberate decision, not an accident."""
        responses = [
            _mock_response(200, json.dumps({"issue": "Real fact drift found here, quoted exact values.", "severity": 4})),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            flags_path = os.path.join(tmpdir, "flags.json")
            with patch("common.book_editor.requests.post", side_effect=responses + [requests.ConnectionError("refused")]):
                with self.assertRaises(EditorModelError):
                    run_model_checks("src", "hum", "ch01.md", 0, _fake_agent_config(), flags_path=flags_path)
            self.assertFalse(os.path.exists(flags_path))


class TestSplitParagraphsAndChapterGranularity(unittest.TestCase):
    """TASK-94 Stage 9 A.1/A.2 — paragraph-granularity deterministic pre-filter."""

    def test_split_paragraphs_basic(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        self.assertEqual(split_paragraphs(text), ["Para one.", "Para two.", "Para three."])

    def test_split_paragraphs_fence_aware(self):
        text = "Intro.\n\n```python\ndef f():\n\n    pass\n```\n\nOutro."
        result = split_paragraphs(text)
        self.assertEqual(result, ["Intro.", "```python\ndef f():\n\n    pass\n```", "Outro."])

    def test_chapter_level_flags_deterministic_across_reruns(self):
        source = "Para one with `code_span()`.\n\nPara two."
        humanized = "We rewrote para one, dropping `code_span()` entirely.\n\nPara two unchanged."
        flags1 = run_deterministic_checks_for_chapter(source, humanized, "ch1.md")
        flags2 = run_deterministic_checks_for_chapter(source, humanized, "ch1.md")
        self.assertEqual(sorted(f["flag_id"] for f in flags1), sorted(f["flag_id"] for f in flags2))

    def test_paragraph_count_mismatch_flagged_at_chapter_scope(self):
        source = "Para one.\n\nPara two.\n\nPara three."
        humanized = "Para one and two merged.\n\nPara three unchanged."
        flags = run_deterministic_checks_for_chapter(source, humanized, "chX.md")
        mismatch = [f for f in flags if f["para_index"] == -1]
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0]["category"], "structural_drift")

    def test_rerun_before_resolution_does_not_duplicate_in_file(self):
        source = "Run `pip install requests==2.28.0` to install.\n\nSecond para stays put."
        humanized = "Install the requests library.\n\nSecond para stays put too."
        with tempfile.TemporaryDirectory() as tmpdir:
            flags_path = os.path.join(tmpdir, "flags.json")
            for _ in range(3):
                run_deterministic_checks_for_chapter(source, humanized, "ch01.md", flags_path=flags_path)
            with open(flags_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(len(data), 1)


if __name__ == "__main__":
    unittest.main()
