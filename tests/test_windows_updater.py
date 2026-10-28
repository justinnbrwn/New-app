import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.update_windows_monitor import update, safe_error


class WindowsUpdaterTests(unittest.TestCase):
    def test_diagnostic_never_returns_stderr_or_source(self):
        error = subprocess.CalledProcessError(128, ['git','merge','private-value'], stderr=b'index.lock private-secret-value')
        text = safe_error(error)
        self.assertIn('Git index is locked', text)
        self.assertNotIn('private', text)
        syntax = SyntaxError('private-secret-value', ('private-file', 9, 1, 'SECRET=private-value'))
        self.assertNotIn('private', safe_error(syntax))

    def command(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, stderr=subprocess.PIPE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repo = root / 'checkout'
        origin = root / 'origin.git'
        subprocess.run(['git', 'init', '--bare', str(origin)], check=True, capture_output=True)
        subprocess.run(['git', 'clone', str(origin), str(self.repo)], check=True, capture_output=True)
        self.command('config', 'user.name', 'Fixture'); self.command('config', 'user.email', 'fixture@example.invalid')
        self.command('checkout', '-b', 'feature/hashmargin-pro-dashboard')
        (self.repo / 'private_email_alerts.py').write_text('SETTING = 1\n\ndef main():\n    print("old")\n')
        for name in ['account_monitor.py','customer_service.py','integrations/monitor_publish.py']:
            file = self.repo / name; file.parent.mkdir(exist_ok=True); file.write_text('pass\n')
        self.command('add', '.'); self.command('commit', '-m', 'base')
        self.base = self.command('rev-parse', 'HEAD').decode().strip()
        self.cwd = Path.cwd()

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def remote_update(self):
        file = self.repo / 'private_email_alerts.py'
        file.write_text(file.read_text().replace('print("old")',
            'from integrations.monitor_publish import publish_workers\n    print("synced")\n    publish_workers([])'))
        self.command('add', '.'); self.command('commit', '-m', 'sync update')
        self.command('push', 'origin', 'feature/hashmargin-pro-dashboard')
        self.command('reset', '--hard', self.base)

    def test_preserves_local_settings_untracked_files_and_upstream_sync(self):
        self.remote_update()
        file = self.repo / 'private_email_alerts.py'
        file.write_text(file.read_text().replace('SETTING = 1', 'SETTING = 2'))
        demo = self.repo / 'demo.py'; demo.write_text('preserve me')
        backup = update(self.repo, Path(self.temp.name) / 'backups')
        self.assertIn('SETTING = 2', file.read_text())
        self.assertIn('print("synced")', file.read_text())
        self.assertEqual(demo.read_text(), 'preserve me')
        self.assertIn('SETTING = 2', (backup / 'original.py').read_text())
        self.assertNotIn(str(self.repo), str(backup))

    def test_conflict_restores_original_without_markers(self):
        self.remote_update()
        file = self.repo / 'private_email_alerts.py'
        original = file.read_text().replace('print("old")', 'print("local")')
        file.write_text(original)
        with self.assertRaises(RuntimeError): update(self.repo, Path(self.temp.name) / 'backups')
        self.assertEqual(file.read_text(), original)

    def test_windows_line_endings_preserve_settings_and_sync(self):
        self.remote_update()
        self.command('config', 'core.autocrlf', 'true')
        file = self.repo / 'private_email_alerts.py'
        file.write_bytes(file.read_bytes().replace(b'SETTING = 1', b'SETTING = 2').replace(b'\n', b'\r\n'))
        update(self.repo, Path(self.temp.name) / 'backups')
        self.assertIn('SETTING = 2', file.read_text())
        self.assertIn('publish_workers([])', file.read_text())

    def test_other_tracked_changes_stop_before_mutation(self):
        self.remote_update()
        file = self.repo / 'customer_service.py'; file.write_text('LOCAL = True\n')
        with self.assertRaises(RuntimeError): update(self.repo, Path(self.temp.name) / 'backups')
        self.assertEqual(file.read_text(), 'LOCAL = True\n')
        self.assertEqual(self.command('rev-parse','HEAD').decode().strip(), self.base)
