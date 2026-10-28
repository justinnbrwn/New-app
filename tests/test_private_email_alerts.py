import unittest
from unittest.mock import Mock, patch
from email.message import EmailMessage
from integrations.monitor_analysis import detect_changes
import private_email_alerts as alerts

class EmailAlertTests(unittest.TestCase):
    def test_sync_diagnostic_never_returns_exception_details(self):
        from urllib.error import HTTPError
        from customer_service import ServiceError
        self.assertEqual(alerts.sync_error_code(HTTPError('https://private.example/secret',401,'secret',{},None)), 'HTTP_401')
        self.assertEqual(alerts.sync_error_code(ValueError('private-secret-value')), 'LOCAL_CONFIGURATION')
        self.assertEqual(alerts.sync_error_code(ServiceError(400,'Invalid hashrate unit')), 'WORKER_HASHRATE_UNIT')
        self.assertEqual(alerts.sync_error_code(RuntimeError('private-secret-value')), 'UNEXPECTED_ERROR')
    def test_no_alert_on_first_observation(self):
        send = Mock()
        current = alerts.check_once(None, fetch=lambda: [{"name":"rig","state":"off"}], send=send)
        self.assertEqual(current[0]["state"], "off")
        send.assert_not_called()

    def test_new_offline_sends_once(self):
        send = Mock()
        healthy = [{"name":"rig","state":"ok"}]
        offline = [{"name":"rig","state":"off"}]
        alerts.check_once(healthy, fetch=lambda: offline, send=send)
        alerts.check_once(offline, fetch=lambda: offline, send=send)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0][0]["state"], "off")

    def test_no_email_for_empty_events(self):
        smtp = Mock()
        self.assertFalse(alerts.send_email([], smtp_factory=smtp))
        smtp.assert_not_called()

    def test_email_contains_counts_not_worker_names(self):
        env = {"HASHMARGIN_SMTP_HOST":"mail.example.org", "HASHMARGIN_EMAIL_FROM":"sender@example.org",
               "HASHMARGIN_EMAIL_TO":"recipient@example.org", "HASHMARGIN_SMTP_USER":"sender",
               "HASHMARGIN_SMTP_PASSWORD":"example"}
        server = Mock()
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=server)
        factory.return_value.__exit__ = Mock(return_value=False)
        with patch.dict("os.environ", env):
            alerts.send_email([{"worker":"private-worker","state":"off"}], smtp_factory=factory)
        msg = server.send_message.call_args.args[0]
        self.assertIsInstance(msg, EmailMessage)
        self.assertNotIn("private-worker", msg.get_content())
        self.assertIn("Offline: 1", msg.get_content())

if __name__ == "__main__":
    unittest.main()
