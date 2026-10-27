"""Basic HTTP smoke tests for the safe public beta."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from staging import Handler


class BetaPublicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def get(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        status = response.status
        connection.close()
        return status, body

    def test_health(self):
        status, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_homepage(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Free calculator beta", body)

    def test_privacy_and_terms(self):
        for path in ("/privacy", "/terms"):
            status, body = self.get(path)
            self.assertEqual(status, 200)
            self.assertGreater(len(body), 100)

    def test_no_private_api(self):
        status, _ = self.get("/api/miners")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
