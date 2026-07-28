import unittest
import os
import tempfile
import json
import shutil

import kbg_web.app as kbg_app
from kbg_web.app import app

class TestApiContractSmoke(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Redirect app's repo_dir to temp directory for clean isolated tests
        self.original_repo_dir = kbg_app.repo_dir
        kbg_app.repo_dir = self.temp_dir

        # Ensure test admin user is recognized by require_login
        kbg_app.users_data["admin"] = "pbkdf2:sha256:1000$dummy$dummy"

        # Create books directory and fixture book
        self.slug = "test-contract-book"
        self.book_dir = os.path.join(self.temp_dir, "books", self.slug)
        os.makedirs(self.book_dir, exist_ok=True)

        # 1. Book config.json
        self.config_data = {
            "slug": self.slug,
            "title": "Test Contract Book",
            "is_manga": False,
            "generate_audiobook": True,
            "enable_asr_verify": False,
            "enable_mqm_review": False,
            "enable_agent_editor": False,
            "manga_resolution": 1600,
            "batch_pages": 50,
            "cooldown_seconds": 30,
            "target_lang": "uk",
            "source_lang": "en"
        }
        with open(os.path.join(self.book_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(self.config_data, f)

        # 2. Translated markdown file
        self.translated_dir = os.path.join(self.book_dir, "translated")
        os.makedirs(self.translated_dir, exist_ok=True)
        with open(os.path.join(self.translated_dir, "merged_translated_uk.md"), "w", encoding="utf-8") as f:
            f.write("# Header\n\nПерший тестовий абзац перекладу.\n\nДругий тестовий абзац перекладу.")

        # 3. Stress cache
        self.cache_dir = os.path.join(self.book_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(os.path.join(self.translated_dir, "stress_cache_uk.json"), "w", encoding="utf-8") as f:
            json.dump({"hash1": "Перший т+естовий абз+ац п+ерекладу."}, f)

        # 4. ASR quality flags queue
        with open(os.path.join(self.book_dir, "asr_stress_queue.json"), "w", encoding="utf-8") as f:
            json.dump([{
                "chunk_id": "a" * 64,
                "original_text": "тест",
                "transcribed_text": "тест2",
                "char_error_rate": 0.25,
                "reason": "asr_mismatch"
            }], f)

        # 5. MQM quality flags queue
        with open(os.path.join(self.book_dir, "translation_quality_flags.json"), "w", encoding="utf-8") as f:
            json.dump([{
                "segment_id": "test_seg_01",
                "original": "test",
                "translated": "тест",
                "score": 7,
                "reason": "mqm_low_score",
                "issues": ["minor accuracy"]
            }], f)

        # Setup Flask test client
        app.config["TESTING"] = True
        self.client = app.test_client()

        # Login session for authenticated test client
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def tearDown(self):
        kbg_app.repo_dir = self.original_repo_dir
        shutil.rmtree(self.temp_dir)

    def test_api_books_contract(self):
        res = self.client.get("/api/books")
        self.assertEqual(res.status_code, 200, msg="GET /api/books should return 200 OK")
        data = res.get_json()
        book_list = data if isinstance(data, list) else data.get("books", [])
        self.assertGreater(len(book_list), 0, msg="GET /api/books should return at least 1 book item")

        book = book_list[0]
        self.assertIn("slug", book, msg="Dashboard.tsx reads book.slug for routing and identification — removing this field breaks book cards")
        self.assertIn("title", book, msg="Dashboard.tsx reads book.title for header display")
        self.assertIn("is_running", book, msg="Dashboard.tsx reads book.is_running to show running/stopped badge — removing this field silently breaks running status")
        self.assertIn("stalled", book, msg="Dashboard.tsx reads book.stalled to show stalled conversion resume modal")
        self.assertIn("stalled_reason", book, msg="Dashboard.tsx reads book.stalled_reason for status subtext and modal notice")
        self.assertIn("progress", book, msg="Dashboard.tsx reads book.progress object")
        self.assertIn("output_files", book, msg="Dashboard.tsx reads book.output_files for downloadable assets")

        progress = book.get("progress") or {}
        self.assertIn("overall_percent", progress, msg="Dashboard.tsx reads book.progress.overall_percent for progress bar percentage — reading raw number breaks UI")
        self.assertIn("marker_percent", progress, msg="Dashboard.tsx reads book.progress.marker_percent for PDF extraction progress")
        self.assertIn("translation_percent", progress, msg="Dashboard.tsx reads book.progress.translation_percent for translation progress")
        self.assertIn("stress_percent", progress, msg="Dashboard.tsx reads book.progress.stress_percent for stress accent progress")
        self.assertIn("tts_percent", progress, msg="Dashboard.tsx reads book.progress.tts_percent for TTS synthesis progress")

    def test_api_models_contract(self):
        res = self.client.get("/api/models")
        self.assertEqual(res.status_code, 200, msg="GET /api/models should return 200 OK")
        data = res.get_json()

        self.assertIn("server_status", data, msg="SettingsView.tsx reads server_status object for LLM status")
        server_status = data.get("server_status") or {}
        self.assertIn("running", server_status, msg="SettingsView.tsx reads server_status.running boolean")
        self.assertIn("loaded_model", server_status, msg="SettingsView.tsx reads server_status.loaded_model name")
        self.assertIn("translation_model", data, msg="SettingsView.tsx reads translation_model name")
        self.assertIn("available_models", data, msg="SettingsView.tsx reads available_models list")

    def test_api_book_settings_contract(self):
        res = self.client.get(f"/api/book-settings/{self.slug}")
        self.assertEqual(res.status_code, 200, msg="GET /api/book-settings/<slug> should return 200 OK")
        data = res.get_json()

        self.assertIn("is_manga", data, msg="BookSettingsModal.tsx reads is_manga setting toggle")
        self.assertIn("generate_audiobook", data, msg="BookSettingsModal.tsx reads generate_audiobook setting toggle")
        self.assertIn("enable_asr_verify", data, msg="BookSettingsModal.tsx reads enable_asr_verify setting toggle")
        self.assertIn("enable_mqm_review", data, msg="BookSettingsModal.tsx reads enable_mqm_review setting toggle")
        self.assertIn("enable_agent_editor", data, msg="BookSettingsModal.tsx reads enable_agent_editor setting toggle")
        self.assertIn("manga_resolution", data, msg="BookSettingsModal.tsx reads manga_resolution setting")
        self.assertIn("batch_pages", data, msg="BookSettingsModal.tsx reads per-book batch_pages setting")
        self.assertIn("cooldown_seconds", data, msg="BookSettingsModal.tsx reads per-book cooldown_seconds setting")
        self.assertIn("entitled", data, msg="BookSettingsModal.tsx reads entitled boolean for premium options")

    def test_api_preview_book_contract(self):
        res = self.client.get(f"/api/preview/book/{self.slug}")
        self.assertEqual(res.status_code, 200, msg="GET /api/preview/book/<slug> should return 200 OK")
        data = res.get_json()

        self.assertIn("paragraphs", data, msg="StagesView.tsx reads paragraphs array for book text preview")
        paragraphs = data.get("paragraphs") or []
        self.assertGreater(len(paragraphs), 0, msg="GET /api/preview/book/<slug> should return parsed paragraphs")

        para = paragraphs[0]
        self.assertIn("hash", para, msg="StagesView.tsx reads paragraph.hash for audio playback and inline editing")
        self.assertIn("original", para, msg="StagesView.tsx reads paragraph.original text for original tab display")
        self.assertIn("translated", para, msg="StagesView.tsx reads paragraph.translated text for Ukrainian translation display")
        self.assertIn("stressed", para, msg="StagesView.tsx reads paragraph.stressed text for accent-annotated preview")
        self.assertIn("has_audio", para, msg="StagesView.tsx reads paragraph.has_audio boolean for synthesis play button gating")

    def test_api_asr_quality_flags_contract(self):
        res = self.client.get(f"/api/preview/asr-quality-flags/{self.slug}")
        self.assertEqual(res.status_code, 200, msg="GET /api/preview/asr-quality-flags/<slug> should return 200 OK")
        data = res.get_json()

        self.assertEqual(data.get("status"), "success", msg="StagesView.tsx expects status=success for ASR quality flags endpoint")
        self.assertIn("flags", data, msg="StagesView.tsx reads flags list for ASR quality warnings")

    def test_api_mqm_quality_flags_contract(self):
        res = self.client.get(f"/api/preview/mqm-quality-flags/{self.slug}")
        self.assertEqual(res.status_code, 200, msg="GET /api/preview/mqm-quality-flags/<slug> should return 200 OK")
        data = res.get_json()

        self.assertEqual(data.get("status"), "success", msg="StagesView.tsx expects status=success for MQM quality flags endpoint")
        self.assertIn("flags", data, msg="StagesView.tsx reads flags list for MQM quality warnings")

if __name__ == '__main__':
    unittest.main()
