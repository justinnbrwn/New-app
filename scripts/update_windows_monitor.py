"""Run from the existing Windows checkout. Preserve local settings; never print them."""
import datetime
import ast
import os
from pathlib import Path
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)


def safe_error(error):
    """Describe the failing operation without source lines, secrets, or raw stderr."""
    if isinstance(error, RuntimeError):
        return str(error)
    if isinstance(error, subprocess.CalledProcessError):
        command = error.cmd if isinstance(error.cmd, list) else []
        operation = command[1] if len(command) > 1 and command[0] == 'git' else 'task restart'
        reason = (error.stderr or b'').lower()
        known = [('untracked working tree files', 'untracked-file collision'),
                 ('local changes', 'local-file collision'),
                 ('not possible to fast-forward', 'branch needs merge'),
                 ('unable to create', 'Git lock or file permission'),
                 ('index.lock', 'Git index is locked'),
                 ('authentication failed', 'GitHub authentication required')]
        category = next((label for marker, label in known if marker.encode() in reason), 'operation failed')
        return f'Stopped: {operation}, exit {error.returncode}, {category}. Task restart not confirmed.'
    if isinstance(error, SyntaxError):
        return f'Stopped: Python syntax check, line {error.lineno}. No source or keys displayed.'
    if isinstance(error, OSError):
        return f'Stopped: {type(error).__name__}, system code {error.errno}, Windows code {getattr(error, "winerror", None)}.'
    return f'Stopped: {type(error).__name__}. No settings or keys displayed.'


def update(repo, backup_root):
    os.chdir(repo)
    branch = 'feature/hashmargin-pro-dashboard'
    if git('branch', '--show-current').decode().strip() != branch:
        raise RuntimeError('Open the existing feature/hashmargin-pro-dashboard checkout first.')
    changed = set(git('diff', '--name-only', 'HEAD').decode().splitlines())
    if changed - {'private_email_alerts.py'} or git('diff', '--cached', '--name-only').strip():
        raise RuntimeError('Additional tracked changes need review; no local files were changed.')
    git('fetch', 'origin', branch)
    # Verify fast-forward before touching the locally customized collector.
    subprocess.run(['git', 'merge-base', '--is-ancestor', 'HEAD', 'origin/' + branch],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    alert = Path('private_email_alerts.py')
    original = alert.read_bytes()
    base = git('show', 'HEAD:private_email_alerts.py')
    backup = Path(backup_root) / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, exist_ok=False)
    (backup / 'original.py').write_bytes(original)
    (backup / 'base.py').write_bytes(base)
    # Backup stays outside the repository: private startup changes are never stashed/committed.
    alert.write_bytes(base)
    try:
        git('merge', '--ff-only', 'origin/' + branch)
        (backup / 'upstream.py').write_bytes(alert.read_bytes())
        merged = backup / 'merged.py'
        merged.write_bytes(original)
        result = subprocess.run(['git', 'merge-file', '--quiet', str(merged),
            str(backup / 'base.py'), str(backup / 'upstream.py')],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError('Your email settings overlap the update. Original collector restored; manual merge needed.')
        alert.write_bytes(merged.read_bytes())
        for name in ['private_email_alerts.py', 'account_monitor.py',
                     'customer_service.py', 'integrations/monitor_publish.py']:
            compile(Path(name).read_bytes(), name, 'exec')
        parsed = ast.parse(alert.read_bytes())
        if not (any(isinstance(n, ast.ImportFrom) and n.module == 'integrations.monitor_publish' for n in ast.walk(parsed))
                and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'publish_workers' for n in ast.walk(parsed))):
            raise RuntimeError('Local collector still lacks account sync. Original file restored; review needed.')
    except Exception:
        alert.write_bytes(original)
        raise
    return backup


def main():
    if os.name != 'nt':
        raise RuntimeError('Run this updater on the Windows monitor computer.')
    appdata = Path(os.environ['APPDATA']) / 'HashMarginPro'
    startup = appdata / 'start-monitor.ps1'
    if not startup.is_file():
        raise RuntimeError('Existing start-monitor.ps1 was not found; no task was changed.')
    backup = update(Path.cwd(), appdata / 'update-backups')
    # The previous setup already added this line. Fail safely if it is missing.
    startup_text = startup.read_text(encoding='utf-8-sig')
    if 'HASHMARGIN_ACCOUNT_ORIGIN' not in startup_text:
        raise RuntimeError('Add HASHMARGIN_ACCOUNT_ORIGIN to start-monitor.ps1 before restarting.')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "$ErrorActionPreference='Stop'; Stop-ScheduledTask -TaskName 'HashMargin Pro Monitor'; "
        "Start-ScheduledTask -TaskName 'HashMargin Pro Monitor'; "
        "Get-ScheduledTask -TaskName 'HashMargin Pro Monitor' | Select-Object TaskName,State"], check=True)
    print('Update passed. Existing task restarted. Local changes preserved.')
    print('Private backup location:', backup)
    print('Next verify Account snapshot synced in the monitor log.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Command stdout/stderr and file contents may contain settings; never display them.
        print(safe_error(error))
        sys.exit(1)
