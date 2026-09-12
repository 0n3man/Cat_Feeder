#!/usr/bin/python3
"""Recover an enabled camera service; honor halted status only for a live camera."""
from pathlib import Path
import subprocess
import time

UNIT = 'cat-feeder-camera.service'


def needs_recovery(state, pid, age, halted, show_preview, preview_age, enabled):
    if state in ('activating', 'deactivating', 'reloading'):
        return False
    if state != 'active' or pid == 0:
        return enabled
    if age < 90 or halted or not show_preview:
        return False
    return preview_age > 90


def main():
    result = subprocess.run(['systemctl', 'show', UNIT, '-p', 'ActiveState',
        '-p', 'MainPID', '-p', 'ActiveEnterTimestampMonotonic', '-p', 'UnitFileState'],
        capture_output=True, text=True, check=True, timeout=10)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    config = {}
    for filename in ('/etc/raspimjpeg', '/var/www/html/uconfig'):
        path = Path(filename)
        if path.exists():
            for line in path.read_text().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2 and not line.lstrip().startswith('#'):
                    config[parts[0]] = parts[1].strip()
    status = Path(config.get('status_file', '/dev/shm/mjpeg/status_mjpeg.txt'))
    preview = Path(config.get('preview_path', '/dev/shm/mjpeg/cam.jpg'))
    try:
        preview_age = time.time() - preview.stat().st_mtime
    except FileNotFoundError:
        preview_age = float('inf')
    age = time.monotonic() - int(props.get('ActiveEnterTimestampMonotonic', '0')) / 1000000
    if needs_recovery(props.get('ActiveState', ''), int(props.get('MainPID', '0')),
                      age, status.exists() and status.read_text().strip() == 'halted',
                      config.get('show_preview', 'true') != 'false', preview_age,
                      props.get('UnitFileState') in ('enabled', 'enabled-runtime')):
        print('Recovering missing/stale camera service', flush=True)
        subprocess.run(['systemctl', '--no-block', 'restart', UNIT], check=True, timeout=10)


if __name__ == '__main__':
    main()
