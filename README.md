# Cat_Feeder — initial clean-Pi test installer

Combines `0n3man/RasPyCam`, `0n3man/RPi_Cam_Web_Interface`, and this repository's
`networkControl.py`. Intended for the spare Pi 3B with a camera and a fresh
Raspberry Pi OS installation. This is an initial installer, not yet hardware
validated on that OS. It refuses an existing `/opt/vc/bin/raspycam` or legacy
`feeder.service` installation. Do not use it to upgrade the working feeder.

## Try it

From your normal login account (the checkout should belong to that account):

```bash
cd ~/Cat_Feeder
./install.sh --dry-run
sudo ./install.sh
```

APT installs the distro Picamera2/OpenCV/Pillow/GPIO packages, FFmpeg,
Apache/PHP, netcat-traditional, rsyslog, cron and zip. It checks Python imports
before installing application files. If packages are unavailable, it stops;
it does not use pip to replace the distro's camera stack. Enable/connect the
camera beforehand and verify camera detection with the OS camera tools.

The installer clones the two forks into `Cat_Feeder/RasPyCam/` and
`Cat_Feeder/RPi_Cam_Web_Interface/`, both ignored by Git. Existing clean clones
are reused without automatically pulling changes. Wrong origins or dirty
clones are rejected. To choose tested revisions explicitly:

```bash
sudo ./install.sh --raspycam-ref CAMERA_COMMIT --web-ref WEB_COMMIT
```

Actual installed commit IDs are recorded in
`/var/lib/cat-feeder-install/manifest.json`. Ensure your RasPyCam fork contains
the latest bounded FFmpeg writer and diagnostics before installing.

Open `http://<pi-address>/` for the camera interface and feeding buttons.
Automatic feeding is OFF by default; the controller runs and manual buttons
operate the motor. To install the old 06:00 / 14:00 / 21:00 schedule:

```bash
sudo ./install.sh --enable-feeding
```

Choose this flag on your first install, or uninstall before reinstalling.
Alternatively edit `/etc/cron.d/cat-feeder` after installing. Cron uses the
**system timezone**; PHP gets `America/New_York` through separate drop-in files
(use `--timezone AREA/CITY` to change PHP timezone). Check `timedatectl` before
using scheduled feeding. The installer does not change your system timezone.

The motor controller retains GPIO 17, 26-second motor operation, and 300-second
recording from your supplied script. That script currently ignores the requested
portion count, so Feed-2 behaves like Feed-1. Its other behavior is not rewritten
by this initial installer. Root runs the controller for GPIO access; camera and
scheduler run as www-data. The existing controller listens on TCP port 33333;
this installation is intended for your trusted local network.

## What is installed

* Camera Python files: `/opt/vc/bin/raspycam`, config: `/etc/raspimjpeg`.
* Web files: `/var/www/html`, owned by www-data, including FIFO/FIFO1 and preview
  links. Existing web root is moved to the installation backup first.
* Your `userbuttons`, feed macros and `schedule.json` are overlaid. This preserves
  your 168-hour retention and 30% minimum-free-space settings and sun-based
  camera settings; review location and GMT offset in the GUI.
* Upstream PHP pages/config are retained. Legacy gimbal frames, directional
  buttons, `config.php`, and backup scheduler files are not overlaid.
* Motor script: `/opt/cat-feeder/networkControl.py`.
* Services: `cat-feeder-camera`, `cat-feeder-scheduler`, `cat-feeder`.
* A `cat-feeder-watchdog.timer` checks for stale previews every two minutes.
  Systemd is the sole camera supervisor; no legacy launcher or reboot cron job.
* Dedicated Apache site, PHP timezone drop-ins, cron file and tmpfiles rule.
* Diagnostics: `/var/log/raspycam`, bounded by the camera code. Other service
  output goes to the existing system journal.

The combined installer deliberately does not execute the dependency installers:
they modify rc.local and contain older PHP assumptions. Your RasPyCam installer
should still be updated to use your web fork for standalone installations, but
that edit does not have to be pushed before using this combined installer.

## Starting, stopping, and restarting services

There is **no single service that starts the entire feeder**. The installer
independently enables three application services and a watchdog timer at boot.
`cat-feeder.service` runs only the motor/network controller. The watchdog checks
only the camera; it does not start the controller or PHP scheduler.

| Systemd unit | Program / purpose | Effect of stopping it |
| --- | --- | --- |
| `cat-feeder-camera.service` | Runs `/opt/vc/bin/raspycam/main.py --config /etc/raspimjpeg` directly; replaces the legacy raspimjpeg camera process | Preview and recording stop |
| `cat-feeder.service` | Runs `/opt/cat-feeder/networkControl.py`, listening on port 33333 | Feeding requests cannot be handled; the stop hook turns GPIO 17 off |
| `cat-feeder-scheduler.service` | Runs `/var/www/html/schedule.php`; translates FIFO1 recording requests into camera commands and manages retention/settings | Feed-triggered recording and scheduled web housekeeping stop; the motor controller can still dispense food |
| `cat-feeder-watchdog.timer` | Invokes `cat-feeder-watchdog.service` approximately every two minutes | Camera health checks stop |
| `apache2.service` | Serves the browser interface | Web access stops; the other services and scheduled feeding can continue |

Systemd starts the applications at boot. Startup ordering is configured, but
starting or restarting one application does **not** automatically start or
restart the other two. The camera uses `Restart=always` to recover even after
an unexpected clean exit; the controller and scheduler use `Restart=on-failure`.

Perform routine maintenance when no feeding or recording is in progress.
Restarting the motor controller resets `rec_len` to its default of 300 seconds.

### Restart one component

```bash
sudo systemctl restart cat-feeder-camera.service
sudo systemctl restart cat-feeder-scheduler.service
sudo systemctl restart cat-feeder.service
```

Run only the command for the component you need. Restart Apache separately if
its configuration changes:

```bash
sudo systemctl restart apache2.service
```

### Stop the whole feeder for maintenance

Stop the watchdog first so it cannot bring the camera back. Stop the controller
before the scheduler and camera:

```bash
sudo systemctl stop cat-feeder-watchdog.timer
sudo systemctl stop cat-feeder-watchdog.service
sudo systemctl stop cat-feeder.service
sudo systemctl stop cat-feeder-scheduler.service
sudo systemctl stop cat-feeder-camera.service
```

Apache remains available, but camera/feeding controls will not work. You may
also stop `apache2.service` if you want the web page offline.

**Stopping the camera alone is not a lasting stop while the watchdog is on:**
although `systemctl stop` suppresses systemd's own automatic restart, the
watchdog will recover an enabled camera service that is no longer running.
A live camera paused through the GUI is respected by the watchdog.

### Start the whole feeder again

```bash
sudo systemctl start cat-feeder-camera.service
sudo systemctl start cat-feeder-scheduler.service
sudo systemctl start cat-feeder.service
sudo systemctl start cat-feeder-watchdog.timer
```

Also start `apache2.service` if you stopped it. Allow time for camera
initialization; `systemctl start` returning does not mean the preview is ready.
To restart the whole feeder, use the stop sequence followed by the start
sequence above. The watchdog gets invoked by its timer; do not enable the
one-shot `cat-feeder-watchdog.service` as a separate boot service.

### Keep the feeder stopped across reboots

After the maintenance stop sequence, disable automatic startup:

```bash
sudo systemctl disable cat-feeder-camera.service cat-feeder-scheduler.service cat-feeder.service cat-feeder-watchdog.timer
```

To restore automatic startup, enable them and then use the start sequence:

```bash
sudo systemctl enable cat-feeder-camera.service cat-feeder-scheduler.service cat-feeder.service cat-feeder-watchdog.timer
```

Feeding times, if enabled during installation, live separately in
`/etc/cron.d/cat-feeder`. Stopping services does not remove those entries. Comment
out the feeding line there to disable scheduled feeding while retaining manual
feeding. Do not stop the system-wide cron service just to disable cat feeds.

### Check status and logs

```bash
systemctl status cat-feeder-camera cat-feeder-scheduler cat-feeder cat-feeder-watchdog.timer
sudo journalctl -u cat-feeder-camera -u cat-feeder-scheduler -u cat-feeder --since "10 minutes ago" --no-pager
sudo journalctl -u cat-feeder-watchdog --since "10 minutes ago" --no-pager
```

To test automatic camera recovery while idle, signal the camera process without
explicitly stopping its service:

```bash
sudo systemctl kill --kill-whom=main --signal=SIGTERM cat-feeder-camera.service
```

Check for a new PID and a fresh preview after shutdown, the five-second restart
delay, and initialization. `SIGKILL` can be used instead to test an abrupt crash.

## Uninstall and repeat

```bash
./uninstall.sh --dry-run
sudo ./uninstall.sh
```

Stops/disables the dedicated services and restores original files, directories
and Apache default-site link. Test files, recordings, logs and installation
backups are retained under `/var/lib/cat-feeder-uninstalled-TIMESTAMP/` rather
than deleting footage. Empty parent directories may remain. Remove the dated
archive manually once you no longer need its recordings or backups.

**APT packages and source clones remain installed.** Uninstall does not purge
shared packages or run autoremove; this keeps repeated tests quick and avoids
removing unrelated software. A reimaged SD card is the way to repeat a truly
clean OS/package installation. Package installations that fail before the
manifest is created may also leave installed packages behind.

This is an install/uninstall testing workflow, not an in-place updater. A second
install refuses while a manifest exists. If application installation fails,
run uninstall to restore saved paths before retrying. It does not feed the cat
as part of validation. A fresh preview and active services are checked, but you
should test recording, manual feeding, reboot and a scheduled event yourself.

```bash
systemctl status cat-feeder-camera cat-feeder-scheduler cat-feeder
journalctl -u cat-feeder-camera -u cat-feeder-scheduler -u cat-feeder --since today
python3 -m unittest discover -s tests -v
```
