#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from bin.run_book_pipeline import stage_humanize, _strip_frontmatter
from common.notebooklm_client import NotebookLMConnectionError, NotebookLMToolError


class TestHybridHumanize(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_hybrid_humanize_")
        self.source_docs_dir = os.path.join(self.temp_dir, "source_docs")
        os.makedirs(self.source_docs_dir, exist_ok=True)

        self.normal_content = "# Chapter 1\nThis is a normal chapter."
        self.thin_content = "---\ntitle: Thin Stub\n---\nThin stub content."

        with open(os.path.join(self.source_docs_dir, "000_ch1.md"), "w", encoding="utf-8") as f:
            f.write(self.normal_content)
        with open(os.path.join(self.source_docs_dir, "001_ch2.md"), "w", encoding="utf-8") as f:
            f.write(self.thin_content)
        with open(os.path.join(self.source_docs_dir, "002_ch3.md"), "w", encoding="utf-8") as f:
            f.write(self.thin_content)

        self.manifest = [
            {"index": 0, "source_rel": "ch1.md", "manifest_file": "000_ch1.md"},
            {"index": 1, "source_rel": "ch2.md", "manifest_file": "001_ch2.md"},
            {"index": 2, "source_rel": "ch3.md", "manifest_file": "002_ch3.md"},
        ]
        self.config = {"notebook_id": "nb-test-123", "gemini_api_key": "dummy_key"}

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("bin.run_book_pipeline.NotebookLMClient")
    @patch("common.gemini_humanizer.GeminiHumanizer")
    def test_hybrid_flow_and_per_chapter_fresh_primary(self, mock_gemini_cls, mock_notebook_cls):
        mock_notebook_client = MagicMock()
        mock_notebook_cls.return_value = mock_notebook_client

        mock_gemini_instance = MagicMock()
        mock_gemini_cls.return_value = mock_gemini_instance

        # Chapter 0 (ch1): NotebookLM succeeds
        # Chapter 1 (ch2): NotebookLM refuses ("I'm sorry, but I couldn't find enough context in the document") -> Gemini succeeds
        # Chapter 2 (ch3): NotebookLM connection error -> Gemini also refuses (SemanticGenerationError) -> copy through
        mock_notebook_client.sources_add_text.side_effect = [
            {"id": "src-0"},
            {"id": "src-1"},
            NotebookLMConnectionError("Network timeout"),
        ]
        mock_notebook_client.chat_ask.side_effect = [
            "NotebookLM rewritten chapter 1 prose",
            "I'm sorry, but I couldn't find enough context in the document to answer your query.",
        ]

        from common.gemini_humanizer import SemanticGenerationError
        mock_gemini_instance.humanize_chapter.side_effect = [
            "Gemini rewritten chapter 2 prose",
            SemanticGenerationError("Too thin for Gemini"),
        ]

        humanized_dir = stage_humanize(self.temp_dir, self.config, self.manifest)

        h0 = os.path.join(humanized_dir, "000_ch1.md")
        h1 = os.path.join(humanized_dir, "001_ch2.md")
        h2 = os.path.join(humanized_dir, "002_ch3.md")

        with open(h0, "r", encoding="utf-8") as f:
            c0 = f.read()
        with open(h1, "r", encoding="utf-8") as f:
            c1 = f.read()
        with open(h2, "r", encoding="utf-8") as f:
            c2 = f.read()

        self.assertEqual(c0, "NotebookLM rewritten chapter 1 prose")
        self.assertEqual(c1, "Gemini rewritten chapter 2 prose")
        self.assertEqual(c2, "Thin stub content.")

        # Verify NotebookLM sources_add_text was called 3 times (tried fresh for every chapter!)
        self.assertEqual(mock_notebook_client.sources_add_text.call_count, 3)

    @patch("bin.run_book_pipeline.NotebookLMClient")
    def test_importerror_gemini_fallback(self, mock_notebook_cls):
        """When GeminiHumanizer cannot be imported, fallback copies stripped source through without crashing."""
        mock_notebook_client = MagicMock()
        mock_notebook_cls.return_value = mock_notebook_client

        mock_notebook_client.sources_add_text.side_effect = NotebookLMConnectionError("Service offline")

        manifest = [
            {"index": 0, "source_rel": "ch2.md", "manifest_file": "001_ch2.md"},
        ]

        # Hide common.gemini_humanizer from sys.modules to simulate ImportError
        with patch.dict("sys.modules", {"common.gemini_humanizer": None}):
            humanized_dir = stage_humanize(self.temp_dir, self.config, manifest)

        h0 = os.path.join(humanized_dir, "000_ch2.md")
        with open(h0, "r", encoding="utf-8") as f:
            c0 = f.read()

        self.assertEqual(c0, "Thin stub content.")


if __name__ == "__main__":
    unittest.main()
