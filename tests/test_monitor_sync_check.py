from email.message import Message
import io
import unittest
from urllib.error import HTTPError
from scripts.check_monitor_sync import check, ORIGIN


class SyncCheckTests(unittest.TestCase):
    text = '$env:HASHMARGIN_ACCOUNT_ORIGIN = "' + ORIGIN + '"\n$env:HASHMARGIN_MONITOR_KEY = "' + 'k'*44 + '"\n'

    def error_opener(self, code, body=b'{}', date='Thu, 01 Jan 1970 00:16:40 GMT'):
        def opener(request, timeout):
            self.assertEqual(request.data, b'{"workers":null}')
            self.assertNotIn(b'kkkk', request.data)
            self.assertEqual(request.full_url, ORIGIN + '/api/monitor/publish')
            headers = Message(); headers['Date'] = date
            raise HTTPError(request.full_url, code, 'private error must never display', headers, io.BytesIO(body))
        return opener

    def test_authenticated_validation_is_success_without_write(self):
        self.assertEqual(check(self.text, self.error_opener(400, b'{"error":"Expected at most 200 workers"}')),
                         'KEY_MATCH_OK_NO_DATA_WRITTEN')

    def test_key_mismatch_and_clock_are_distinguished(self):
        self.assertEqual(check(self.text, self.error_opener(401), clock=lambda:1000), 'WINDOWS_AND_RENDER_KEYS_DO_NOT_MATCH')
        self.assertEqual(check(self.text, self.error_opener(401), clock=lambda:2000), 'WINDOWS_CLOCK_DIFFERS_BY_OVER_FIVE_MINUTES')

    def test_local_configuration_checked_without_network(self):
        self.assertEqual(check(''), 'ORIGIN_SETTING_MISSING_OR_INCORRECT')
        self.assertEqual(check(self.text.replace('k'*44,'short')), 'WINDOWS_MONITOR_KEY_TOO_SHORT')
        self.assertEqual(check(self.text.replace(ORIGIN,'https://other.example')), 'ORIGIN_SETTING_MISSING_OR_INCORRECT')

    def test_raw_http_error_is_not_exposed(self):
        self.assertEqual(check(self.text, self.error_opener(502)), 'SERVER_HTTP_502')
