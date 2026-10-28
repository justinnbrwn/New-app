import os
import unittest
from unittest.mock import patch
import private_monitor as monitor

class PrivateMonitorTests(unittest.TestCase):
    def setUp(self):
        monitor._cache.update(at=0.0, result=None)

    def test_summary_and_cache(self):
        calls = []
        def fetch():
            calls.append(True)
            return [{"name": "one", "state": "off"}, {"name": "two", "state": "low"}]
        first = monitor.snapshot(now=100.0, fetch=fetch)
        second = monitor.snapshot(now=101.0, fetch=fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["offline_count"], 1)
        self.assertEqual(first["summary"]["low_count"], 1)

    def test_cache_expiry(self):
        calls = []
        def fetch():
            calls.append(True)
            return []
        monitor.snapshot(now=100.0, fetch=fetch)
        monitor.snapshot(now=161.0, fetch=fetch)
        self.assertEqual(len(calls), 2)

if __name__ == "__main__":
    unittest.main()
