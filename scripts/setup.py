#!/usr/bin/env python3
"""Initial clean-Pi installer. Never runs either dependency's legacy installer."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/cat-feeder-install')
CAM = Path('/opt/vc/bin/raspycam')
WEB = Path('/var/www/html')
PACKAGES = ['git', 'apache2', 'php', 'php-cli', 'libapache2-mod-php',
            'python3-picamera2', 'python3-opencv', 'python3-pil', 'python3-rpi.gpio',
            'ffmpeg', 'netcat-traditional', 'rsyslog', 'cron', 'zip']
UNITS = ['cat-feeder-camera.service', 'cat-feeder-scheduler.service',
         'cat-feeder.service', 'cat-feeder-watchdog.timer']


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def exists(path):
    return path.exists() or path.is_symlink()


def save(state):
    staged = STATE / 'manifest.new'
    staged.write_text(json.dumps(state, indent=2))
    staged.replace(STATE / 'manifest.json')


def reserve(state, path):
    """Move each destination aside, preserving original permissions and contents."""
    path = Path(path)
    if any(item['path'] == str(path) for item in state['paths']):
        return
    backup = STATE / 'original' / str(len(state['paths']))
    item = {'path': str(path), 'backup': str(backup), 'existed': exists(path)}
    state['paths'].append(item)
    save(state)  # Journal intent before changing a destination.
    if item['existed']:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup))
    path.parent.mkdir(parents=True, exist_ok=True)


def put(state, path, text, mode=0o644):
    reserve(state, path)
    Path(path).write_text(text)
    Path(path).chmod(mode)


def copytree(state, source, target):
    reserve(state, target)
    shutil.copytree(source, target)


def own_tree(path, user='www-data'):
    account = pwd.getpwnam(user)
    for entry in [path, *path.rglob('*')]:
        if not entry.is_symlink():
            os.chown(entry, account.pw_uid, account.pw_gid)


def checkout(url, path, ref, user):
    if not path.exists():
        run('runuser', '-u', user, '--', 'git', 'clone', url, path)
    origin = run('runuser', '-u', user, '--', 'git', '-C', path,
                 'remote', 'get-url', 'origin', capture_output=True, text=True).stdout.strip()
    if origin.removesuffix('.git') != url.removesuffix('.git'):
        raise RuntimeError(f'Unexpected repository at {path}: {origin}')
    dirty = run('runuser', '-u', user, '--', 'git', '-C', path,
                'status', '--porcelain', capture_output=True, text=True).stdout
    if dirty:
        raise RuntimeError(f'Refusing to modify a dirty dependency: {path}')
    if ref:
        run('runuser', '-u', user, '--', 'git', '-C', path, 'fetch', 'origin', ref)
        run('runuser', '-u', user, '--', 'git', '-C', path, 'checkout', '--detach', 'FETCH_HEAD')
    return run('runuser', '-u', user, '--', 'git', '-C', path, 'rev-parse', 'HEAD',
               capture_output=True, text=True).stdout.strip()


def service(description, command, user='www-data', extra='', after='', restart='on-failure'):
    return f'''[Unit]
Description={description}
After=network.target {after}
[Service]
Type=simple
User={user}
{extra}
ExecStart={command}
Restart={restart}
RestartSec=5
TimeoutStopSec=35
[Install]
WantedBy=multi-user.target
'''


def install(args):
    ZoneInfo(args.timezone)
    if not re.fullmatch(r'[A-Za-z0-9_+/-]+', args.timezone):
        raise RuntimeError('Invalid timezone')
    user = args.user or os.environ.get('SUDO_USER')
    if not user or user == 'root':
        raise RuntimeError('Run with sudo from your login account, or supply --user USER')
    pwd.getpwnam(user)
    if STATE.exists():
        raise RuntimeError(f'{STATE} exists; uninstall the previous test first')
    if CAM.exists() or Path('/etc/systemd/system/feeder.service').exists():
        raise RuntimeError('Existing camera/feeder detected. Use the clean test Pi.')
    for name in UNITS:
        if subprocess.run(['systemctl', 'cat', name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            raise RuntimeError(f'Existing unit {name}; refusing to replace it')
    apache_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'apache2']).returncode == 0
    run('apt-get', 'update')
    run('apt-get', 'install', '-y', *PACKAGES)
    run('/usr/bin/python3', '-c', 'import picamera2, cv2, PIL, RPi.GPIO')
    camera = ROOT / 'RasPyCam'
    web = ROOT / 'RPi_Cam_Web_Interface'
    revisions = {
        'RasPyCam': checkout('https://github.com/0n3man/RasPyCam.git', camera, args.raspycam_ref, user),
        'RPi_Cam_Web_Interface': checkout('https://github.com/0n3man/RPi_Cam_Web_Interface.git', web, args.web_ref, user),
    }
    for path in [camera / 'app/main.py', camera / 'app/utilities/diagnostics.py',
                 camera / 'app/utilities/video_output.py', web / 'www/index.php']:
        if not path.is_file():
            raise RuntimeError(f'Required source missing: {path}')
    STATE.mkdir(mode=0o700)
    state = {'paths': [], 'revisions': revisions, 'timezone': args.timezone,
             'apache_active': apache_active}
    save(state)
    try:
        copytree(state, camera / 'app', CAM)
        copytree(state, web / 'www', WEB)
        # Only feeding overlays: retain upstream PHP, omit old gimbal pages/config.
        overlay = ROOT / 'RPi_Cam_Web_Interface-updates'
        for name in ('userbuttons', 'schedule.json'):
            shutil.copy2(overlay / name, WEB / name)
        (WEB / 'macros').mkdir(exist_ok=True)
        for name in ('feed1.sh', 'feed2.sh'):
            shutil.copy2(overlay / 'macros' / name, WEB / 'macros' / name)
            (WEB / 'macros' / name).chmod(0o755)
        (WEB / 'media').mkdir(exist_ok=True)
        put(state, '/etc/raspimjpeg', (ROOT / 'etc/etc-raspimjpeg').read_text())
        for name, target in [('raspimjpeg', '/etc/raspimjpeg'),
                             ('cam.jpg', '/dev/shm/mjpeg/cam.jpg'),
                             ('status_mjpeg.txt', '/dev/shm/mjpeg/status_mjpeg.txt')]:
            link = WEB / name
            if exists(link):
                link.unlink()
            link.symlink_to(target)
        for name in ('FIFO', 'FIFO1'):
            path = WEB / name
            if exists(path):
                path.unlink()
            os.mkfifo(path, 0o660)
        own_tree(WEB)
        for directory in ('/var/log/raspycam', '/dev/shm/mjpeg'):
            reserve(state, directory)
            Path(directory).mkdir()
            own_tree(Path(directory))
        put(state, '/etc/tmpfiles.d/cat-feeder.conf', 'd /dev/shm/mjpeg 0755 www-data www-data -\n')
        put(state, '/opt/cat-feeder/networkControl.py', (ROOT / 'networkControl.py').read_text(), 0o755)
        put(state, '/etc/systemd/system/cat-feeder-camera.service', service(
            'Cat feeder camera', '/usr/bin/python3 -u /opt/vc/bin/raspycam/main.py --config /etc/raspimjpeg',
            restart='always',
            extra='SupplementaryGroups=video\nExecStartPre=+/usr/bin/systemd-tmpfiles --create /etc/tmpfiles.d/cat-feeder.conf'))
        put(state, '/etc/systemd/system/cat-feeder-scheduler.service', service(
            'Cat feeder web scheduler', '/usr/bin/php /var/www/html/schedule.php',
            after='cat-feeder-camera.service'))
        put(state, '/opt/cat-feeder/motor_off.py',
            'import RPi.GPIO as GPIO\nGPIO.setmode(GPIO.BCM)\nGPIO.setup(17, GPIO.OUT, initial=GPIO.LOW)\nGPIO.cleanup()\n')
        put(state, '/etc/systemd/system/cat-feeder.service', service(
            'Cat feeder motor controller', '/usr/bin/python3 -u /opt/cat-feeder/networkControl.py',
            user='root', extra='ExecStopPost=/usr/bin/python3 /opt/cat-feeder/motor_off.py',
            after='cat-feeder-camera.service cat-feeder-scheduler.service'))
        # Use systemd as sole camera owner; no legacy launcher/cron restart.
        put(state, '/usr/local/sbin/cat-feeder-watchdog',
            (ROOT / 'scripts/camera_watchdog.py').read_text(), 0o755)
        put(state, '/etc/systemd/system/cat-feeder-watchdog.service',
            '[Unit]\nDescription=Check cat feeder preview\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/cat-feeder-watchdog\n')
        put(state, '/etc/systemd/system/cat-feeder-watchdog.timer',
            '[Unit]\nDescription=Check camera every two minutes\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=2min\n[Install]\nWantedBy=timers.target\n')
        for directory in Path('/etc/php').glob('*/apache2/conf.d'):
            put(state, directory / '99-cat-feeder.ini', f'date.timezone = {args.timezone}\n')
        for directory in Path('/etc/php').glob('*/cli/conf.d'):
            put(state, directory / '99-cat-feeder.ini', f'date.timezone = {args.timezone}\n')
        put(state, '/etc/apache2/sites-available/cat-feeder.conf', '''<VirtualHost *:80>
DocumentRoot /var/www/html
<Directory /var/www/html>
Require all granted
AllowOverride None
Options -Indexes +FollowSymLinks
</Directory>
</VirtualHost>
''')
        reserve(state, '/etc/apache2/sites-enabled/000-default.conf')
        reserve(state, '/etc/apache2/sites-enabled/000-cat-feeder.conf')
        Path('/etc/apache2/sites-enabled/000-cat-feeder.conf').symlink_to('../sites-available/cat-feeder.conf')
        cron = '# Cat_Feeder: times use the system timezone, not PHP timezone.\n'
        if args.enable_feeding:
            cron += '0 6,14,21 * * * root /var/www/html/macros/feed1.sh\n'
        put(state, '/etc/cron.d/cat-feeder', cron)
        run('apache2ctl', 'configtest')
        run('systemctl', 'daemon-reload')
        run('systemctl', 'enable', '--now', *UNITS)
        run('systemctl', 'restart', 'apache2')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            preview = Path('/dev/shm/mjpeg/cam.jpg')
            if preview.exists() and time.time() - preview.stat().st_mtime < 5:
                break
            time.sleep(1)
        else:
            raise RuntimeError('No fresh preview within 60 seconds')
        run('systemctl', 'is-active', *UNITS)
        print('Installed. Open http://<pi-address>/ . Revisions saved in', STATE)
        print('Automatic feeding:', args.enable_feeding, '; PHP timezone:', args.timezone)
    except BaseException:
        print('Installation incomplete. Run sudo ./uninstall.sh to restore saved paths.', file=sys.stderr)
        raise


def uninstall(args):
    if not (STATE / 'manifest.json').exists():
        raise RuntimeError('No Cat_Feeder installation manifest found')
    state = json.loads((STATE / 'manifest.json').read_text())
    for name in ['cat-feeder-watchdog.timer', 'cat-feeder-watchdog.service',
                 'cat-feeder.service', 'cat-feeder-scheduler.service', 'cat-feeder-camera.service']:
        subprocess.run(['systemctl', 'disable', '--now', name], check=False)
    archive = STATE / 'removed'
    archive.mkdir(exist_ok=True)
    for index, item in reversed(list(enumerate(state['paths']))):
        path, backup = Path(item['path']), Path(item['backup'])
        # If reserve was interrupted before its move, leave the original alone.
        if item['existed'] and not exists(backup):
            continue
        if exists(path):
            shutil.move(str(path), str(archive / str(index)))
        if item['existed']:
            shutil.move(str(backup), str(path))
    run('systemctl', 'daemon-reload')
    if state['apache_active']:
        run('systemctl', 'restart', 'apache2')
    else:
        run('systemctl', 'stop', 'apache2')
    destination = STATE.with_name('cat-feeder-uninstalled-' + time.strftime('%Y%m%d-%H%M%S'))
    STATE.rename(destination)
    print('Uninstalled and restored original paths. Removed files/recordings retained at', destination)
    print('APT packages and source clones retained for reuse; no autoremove or unrelated service removal.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--dry-run', action='store_true', help='Describe actions without modifying the Pi')
    parser.add_argument('--user', help='Login account that owns this checkout')
    parser.add_argument('--timezone', default='America/New_York')
    parser.add_argument('--raspycam-ref', help='Optional exact camera commit/tag; otherwise keep cloned HEAD')
    parser.add_argument('--web-ref', help='Optional exact web commit/tag; otherwise keep cloned HEAD')
    parser.add_argument('--enable-feeding', action='store_true', help='Schedule feeds at 06:00, 14:00, 21:00 system time')
    args = parser.parse_args()
    if args.dry_run:
        print(args.action, 'Cat_Feeder on this Pi; root checkout:', ROOT)
        print('Forks: 0n3man/RasPyCam, 0n3man/RPi_Cam_Web_Interface; clones ignored by Git.')
        print('Packages:', ' '.join(PACKAGES))
        print('Destinations:', CAM, WEB, '/etc/raspimjpeg; dedicated services, cron, PHP and Apache configuration.')
        print('Backups/manifest:', STATE, '; uninstall restores paths and archives recordings; packages/clones retained.')
        print('Automatic feeding:', args.enable_feeding)
        return
    if os.geteuid() != 0:
        parser.error('Use sudo for installation/uninstallation, or --dry-run')
    (install if args.action == 'install' else uninstall)(args)


if __name__ == '__main__':
    main()
