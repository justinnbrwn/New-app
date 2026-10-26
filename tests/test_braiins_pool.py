import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.braiins_pool import fetch_workers, summarize

class FakeResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit):
        return b'{"btc":{"workers":{"miner.one":{"state":"ok","hash_rate_5m":100,"hash_rate_unit":"Gh/s"},"miner.two":{"state":"off","hash_rate_5m":0}}}}'

class BraiinsTests(unittest.TestCase):
    def test_workers(self):
        def fake_open(request, timeout):
            self.assertEqual(request.get_header('Pool-auth-token'), 'example')
            self.assertEqual(timeout, 12)
            return FakeResponse()
        workers = fetch_workers('example', opener=fake_open)
        self.assertEqual(len(workers), 2)
        self.assertEqual(summarize(workers)['offline_count'], 1)
    def test_missing_token(self):
        with patch.dict('os.environ', {'BRAIINS_POOL_TOKEN':''}):
            with self.assertRaises(ValueError):
                fetch_workers(token='')
    def test_reject_newline(self):
        with self.assertRaises(ValueError):
            fetch_workers('secret\ninvalid')

if __name__ == '__main__': unittest.main()
