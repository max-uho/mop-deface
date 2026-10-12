"""Bounded stdin/protocol smoke tests without video-tool prerequisites."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.TestCase):
    def request(self, cancel=False):
        binary = os.environ.get('DEFACE_TEST_SIDECAR')
        command = [binary] if binary else [sys.executable, str(ROOT / 'backend/worker.py')]
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding='utf-8')
        output = []; errors = []
        readers = [threading.Thread(target=lambda: output.append(child.stdout.read()), daemon=True),
                   threading.Thread(target=lambda: errors.append(child.stderr.read()), daemon=True)]
        for reader in readers:
            reader.start()
        child.stdin.write(json.dumps({'action': 'selftest'}) + '\n' + ('cancel\n' if cancel else ''))
        child.stdin.flush()
        try:
            child.wait(timeout=90)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=5)
            self.fail(f'Worker failed to exit with stdin open; stdout={output}, stderr={errors}')
        finally:
            child.stdin.close()
        for reader in readers:
            reader.join(timeout=5)
        child.stdout.close(); child.stderr.close()
        self.assertEqual(child.returncode, 0, ''.join(errors))
        return [json.loads(line) for line in ''.join(output).splitlines()]

    def test_terminal_event_exits_without_parent_closing_stdin(self):
        self.assertEqual(self.request()[-1]['type'], 'complete')

    def test_control_line_in_same_write_is_not_lost(self):
        self.assertEqual(self.request(cancel=True)[-1]['type'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
