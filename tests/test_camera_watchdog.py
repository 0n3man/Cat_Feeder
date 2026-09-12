import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('watchdog', Path(__file__).resolve().parents[1] / 'scripts/camera_watchdog.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class WatchdogTests(unittest.TestCase):
    def test_missing_camera_recovers_despite_stale_halted_flag(self):
        self.assertTrue(m.needs_recovery('inactive', 0, 200, True, False, 200, True))

    def test_live_halted_camera_is_respected(self):
        self.assertFalse(m.needs_recovery('active', 123, 200, True, True, 200, True))

    def test_startup_gets_grace_period(self):
        self.assertFalse(m.needs_recovery('active', 123, 20, False, True, 200, True))

    def test_disabled_missing_service_is_not_started(self):
        self.assertFalse(m.needs_recovery('inactive', 0, 200, False, True, 200, False))

    def test_stale_live_camera_recovers(self):
        self.assertTrue(m.needs_recovery('active', 123, 200, False, True, 200, True))

    def test_fresh_preview_is_left_running(self):
        self.assertFalse(m.needs_recovery('active', 123, 200, False, True, 1, True))

    def test_hidden_preview_and_service_transitions_are_respected(self):
        self.assertFalse(m.needs_recovery('active', 123, 200, False, False, 200, True))
        self.assertFalse(m.needs_recovery('deactivating', 123, 200, False, True, 200, True))
