import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('setup', Path(__file__).resolve().parents[1] / 'scripts/setup.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RestoreTests(unittest.TestCase):
    def test_uninstall_restores_original_and_archives_new_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state_dir = root / 'state'
            state_dir.mkdir()
            state = {'paths': [], 'apache_active': False}
            web = root / 'web'
            web.mkdir()
            (web / 'original').write_text('original')
            config = root / 'new.conf'
            with patch.object(m, 'STATE', state_dir), patch.object(m, 'run'), patch.object(m.subprocess, 'run'):
                m.reserve(state, web)
                web.mkdir()
                (web / 'recording.mp4').write_text('keep me')
                m.put(state, config, 'new')
                m.uninstall(None)
            self.assertEqual((web / 'original').read_text(), 'original')
            self.assertFalse(config.exists())
            archive = next(root.glob('cat-feeder-uninstalled-*'))
            self.assertEqual((archive / 'removed/0/recording.mp4').read_text(), 'keep me')

    def test_backup_is_not_overwritten_by_second_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state_dir = root / 'state'
            state_dir.mkdir()
            target = root / 'file'
            target.write_text('original')
            state = {'paths': []}
            with patch.object(m, 'STATE', state_dir):
                m.put(state, target, 'first')
                m.put(state, target, 'second')
            self.assertEqual(len(state['paths']), 1)
            self.assertEqual(Path(state['paths'][0]['backup']).read_text(), 'original')

    def test_uninstall_preserves_original_when_backup_move_did_not_happen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state_dir = root / 'state'
            state_dir.mkdir()
            target = root / 'original'
            target.write_text('untouched')
            state = {'apache_active': False, 'paths': [{'path': str(target), 'backup': str(root / 'missing'), 'existed': True}]}
            with patch.object(m, 'STATE', state_dir), patch.object(m, 'run'), patch.object(m.subprocess, 'run'):
                m.save(state)
                m.uninstall(None)
            self.assertEqual(target.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()
