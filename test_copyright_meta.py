import unittest
import os
import tempfile
import json
import shutil

import kbg_web.app as kbg_app
from kbg_web.app import app
from common.copyright_meta import load_copyright_meta, save_copyright_meta, generate_copyright_text


class TestCopyrightMeta(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_repo_dir = kbg_app.repo_dir
        kbg_app.repo_dir = self.temp_dir
        kbg_app.users_data["admin"] = "pbkdf2:sha256:1000$dummy$dummy"

        self.slug = "test-copyright-book"
        self.book_dir = os.path.join(self.temp_dir, "books", self.slug)
        os.makedirs(self.book_dir, exist_ok=True)

        with open(os.path.join(self.book_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"slug": self.slug, "title": "Test Copyright Book"}, f)

        app.config["TESTING"] = True
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def tearDown(self):
        kbg_app.repo_dir = self.original_repo_dir
        shutil.rmtree(self.temp_dir)

    def test_data_model_and_atomic_save(self):
        # 1. Load default
        meta = load_copyright_meta(self.book_dir)
        self.assertEqual(meta["translator_name"], "")
        self.assertIsNone(meta["edited_text_uk"])

        # 2. Generate and save
        meta["translator_name"] = "Іван Франко"
        meta["original_title"] = "The Python Manual"
        meta["original_author"] = "Guido van Rossum"
        meta["original_url"] = "https://docs.python.org"
        meta["original_license"] = "PSF License"

        uk, en = generate_copyright_text(meta)
        meta["generated_text_uk"] = uk
        meta["generated_text_en"] = en
        save_copyright_meta(self.book_dir, meta)

        # 3. Reload
        reloaded = load_copyright_meta(self.book_dir)
        self.assertEqual(reloaded["translator_name"], "Іван Франко")
        self.assertIn("Іван Франко", reloaded["generated_text_uk"])
        self.assertIn("Guido van Rossum", reloaded["generated_text_en"])

    def test_post_endpoint(self):
        payload = {
            "translator_name": "Олесь Гончар",
            "original_title": "Clean Code",
            "original_author": "Robert C. Martin",
            "original_url": "https://example.com/clean-code",
            "original_license": "CC-BY-4.0"
        }
        res = self.client.post(f"/api/book/{self.slug}/copyright-meta", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "success")
        uk = data.get("generated_text_uk", "")
        en = data.get("generated_text_en", "")

        self.assertIn("Олесь Гончар", uk)
        self.assertIn("Clean Code", uk)
        self.assertIn("Robert C. Martin", uk)
        self.assertNotIn("{translator_name}", uk)
        self.assertNotIn("{original_title}", uk)

        self.assertIn("Олесь Гончар", en)
        self.assertIn("Clean Code", en)

        # Verify on disk
        saved = load_copyright_meta(self.book_dir)
        self.assertEqual(saved["translator_name"], "Олесь Гончар")
        self.assertEqual(saved["generated_text_uk"], uk)

    def test_put_endpoint(self):
        # First populate POST
        self.client.post(f"/api/book/{self.slug}/copyright-meta", json={
            "translator_name": "Тарас Шевченко",
            "original_title": "Kobzar",
        })
        meta_before = load_copyright_meta(self.book_dir)
        gen_uk_before = meta_before["generated_text_uk"]

        # Now PUT edited_text_uk
        edited_text = "Кастомний текст копірайту після редакції."
        res = self.client.put(f"/api/book/{self.slug}/copyright-meta/text", json={
            "edited_text_uk": edited_text
        })
        self.assertEqual(res.status_code, 200)

        meta_after = load_copyright_meta(self.book_dir)
        self.assertEqual(meta_after["edited_text_uk"], edited_text)
        self.assertEqual(meta_after["generated_text_uk"], gen_uk_before)


if __name__ == '__main__':
    unittest.main()
