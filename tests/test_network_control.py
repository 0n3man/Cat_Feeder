import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch, mock_open

spec = importlib.util.spec_from_file_location('controller', Path(__file__).resolve().parents[1] / 'networkControl.py')
m = importlib.util.module_from_spec(spec)
with patch.dict('sys.modules', {'RPi': MagicMock(), 'RPi.GPIO': MagicMock()}):
    spec.loader.exec_module(m)

class RecordingLengthTests(unittest.TestCase):
    def setUp(self):
        m.FEED_REC_SECS = 300
        m.recording = True

    def test_valid_and_invalid_values(self):
        self.assertEqual(m.handle_command('rec_len 120'), 'OK rec_len 120')
        for text in ('rec_len', 'rec_len 1 2', 'rec_len -1', 'rec_len 2.5', 'rec_len 0', 'rec_len 26', 'rec_len 86401'):
            self.assertTrue(m.handle_command(text).startswith('ERR'))
            self.assertEqual(m.FEED_REC_SECS, 120)

    def test_split_and_combined_commands(self):
        conn = MagicMock()
        conn.recv.side_effect = [b'rec_', b'len 120\nrec_len 180\n', b'']
        m.serve_connection(conn)
        self.assertEqual(m.FEED_REC_SECS, 180)
        self.assertEqual(conn.sendall.call_count, 2)

    def test_eof_and_send_only_clients(self):
        conn = MagicMock()
        conn.recv.side_effect = [b'rec_len 60', b'']
        conn.sendall.side_effect = BrokenPipeError
        m.serve_connection(conn)
        self.assertEqual(m.FEED_REC_SECS, 60)

    def test_invalid_and_oversized_input_recovers(self):
        conn = MagicMock()
        conn.recv.side_effect = [b'x'*300 + b'\n\xff\nrec_len 90\n', b'']
        m.serve_connection(conn)
        self.assertEqual(m.FEED_REC_SECS, 90)

    def test_legacy_feed_command_still_dispatches(self):
        conn = MagicMock()
        conn.recv.side_effect = [b'f\n', b'']
        with patch.object(m, 'feed') as feed:
            m.serve_connection(conn)
            feed.assert_called_once_with(1)

    def test_feed_uses_requested_duration_including_motor_time(self):
        m.handle_command('rec_len 120')
        with patch('builtins.open', mock_open()), patch.object(m, 'feed_drop_motor'), patch.object(m.time, 'monotonic', side_effect=[100,127]), patch.object(m.time, 'sleep') as sleep:
            m.feed(1)
            self.assertEqual(sleep.call_args_list[-1].args, (93,))
