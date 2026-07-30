import unittest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from kbg_web.app import app

class TestProtocolAndRunAudio(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "vokov"
            sess["authenticated"] = True

    def test_protocol_endpoint(self):
        res = self.client.get("/api/books/data-engineering/protocol")
        self.assertIn(res.status_code, (200, 400))
        data = res.get_json()
        self.assertIn("stages", data)
        self.assertIn("current_stage", data)
        self.assertEqual(len(data["stages"]), 9)

    def test_run_audio_endpoint(self):
        res = self.client.post("/api/run-audio/data-engineering")
        self.assertIn(res.status_code, (200, 400))
        data = res.get_json()
        self.assertEqual(data.get("status"), "success")

    def test_stop_endpoint(self):
        res = self.client.post("/api/stop/data-engineering")
        self.assertIn(res.status_code, (200, 400))
        data = res.get_json()
        self.assertIn("status", data)

if __name__ == "__main__":
    unittest.main()
