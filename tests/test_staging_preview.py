"""Smoke tests for the public preview. Run: python -m unittest discover -s tests"""
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from staging import Handler

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("GET", path)
        response = conn.getresponse()
        result = response.status, response.getheader("Content-Type"), response.read()
        conn.close()
        return result

    def test_health(self):
        status, content_type, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(json.loads(body)["mode"], "preview-only")

    def test_homepage(self):
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"HashMargin Pro", body)

    def test_unknown_route(self):
        self.assertEqual(self.get("/unknown")[0], 404)

if __name__ == "__main__":
    unittest.main()
