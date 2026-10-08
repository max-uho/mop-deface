"""Actual protocol, codec, cancellation, and Unicode-path integration tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = os.environ.get('DEFACE_TEST_SIDECAR')
COMMAND = [BIN] if BIN else [sys.executable, str(ROOT / 'backend/worker.py')]
TOOLS = Path(os.environ.get('DEFACE_TEST_TOOLS', ROOT / 'backend/tools'))
SUFFIX = '.exe' if os.name == 'nt' else ''
FFMPEG = str(TOOLS / ('ffmpeg' + SUFFIX))

class Processing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='déface 日本語 ')
        self.root = Path(self.temp.name)
        self.source = self.root / 'original video.mp4'
        chapters = self.root / 'chapters.txt'
        chapters.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=900\ntitle=Private chapter\n')
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=96x64:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-f', 'ffmetadata', '-i', str(chapters), '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', 'use_metadata_tags',
                        '-metadata', 'title=Private title', '-metadata', 'artist=Private author',
                        '-metadata', 'location=+48.8566+002.3522/',
                        '-metadata', 'creation_time=2020-01-01T12:00:00Z',
                        '-metadata', 'com.apple.quicktime.make=Private camera',
                        '-metadata', 'exif=Private EXIF payload',
                        '-metadata:s:a:0', 'handler_name=Private audio device', str(self.source)], check=True)
        self.before = self.source.read_bytes()
        self.source_tags = json.loads(subprocess.check_output([str(TOOLS / ('ffprobe' + SUFFIX)), '-v', 'error', '-show_format', '-show_streams', '-show_chapters', '-of', 'json', str(self.source)]))
        self.assertEqual(self.source_tags['format']['tags']['exif'], 'Private EXIF payload')
        self.assertEqual(self.source_tags['chapters'][0]['tags']['title'], 'Private chapter')
    def tearDown(self):
        self.temp.cleanup()
    def request(self, req, cancel=False):
        process = subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env={**os.environ, 'PATH': ''} if BIN else None)
        process.stdin.write(json.dumps(req,ensure_ascii=False)+'\n'); process.stdin.flush()
        if cancel:
            process.stdin.write('cancel\n'); process.stdin.flush()
        events=[]
        while True:
            line=process.stdout.readline()
            if not line:
                break
            event=json.loads(line);events.append(event)
        process.wait(timeout=90)
        diagnostic=process.stderr.read()
        process.stdin.close();process.stdout.close();process.stderr.close()
        self.assertEqual(process.returncode,0,diagnostic)
        return events
    def test_actual_face_mask_lazy_dependencies(self):
        events = self.request({'action': 'selftest'})
        self.assertEqual(events[-1]['type'], 'complete', events)
    @unittest.skipIf(BIN, 'Fault injection only for the source-worker test')
    def test_processing_failure_cannot_deadlock_ffmpeg_shutdown(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('worker', ROOT / 'backend/worker.py')
        worker = importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        work = self.root / 'failure';work.mkdir()
        with patch('deface.deface.anonymize_frame', side_effect=RuntimeError('injected mask failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected mask failure'):
                worker.process({'source': str(self.source), 'workdir': str(work)})
        self.assertFalse(worker.PROCESSES)
    def test_processing_and_audio(self):
        for remove_audio in (False,True):
            work=self.root / str(remove_audio);work.mkdir()
            events=self.request({'action':'process','source':str(self.source),'workdir':str(work),'removeAudio':remove_audio})
            self.assertEqual(events[-1]['type'],'complete',events)
            output=Path(events[-1]['path'])
            probe=self.request({'action':'probe','source':str(output)})[-1]
            self.assertEqual(probe['metadata']['audio'],not remove_audio)
            self.assertEqual(probe['metadata']['width'],96)
            self.assertEqual(probe['metadata']['height'],64)
            self.assertEqual(probe['metadata']['fps'],'10/1')
            self.assertEqual(events[-1]['frames'],10)
            details = json.loads(subprocess.check_output([str(TOOLS / ('ffprobe' + SUFFIX)), '-v', 'error', '-show_format', '-show_streams', '-show_chapters', '-of', 'json', str(output)]))
            self.assertFalse(details.get('chapters'))
            self.assertLessEqual(set(details['format'].get('tags', {})), {'major_brand', 'minor_version', 'compatible_brands'})
            for stream in details['streams']:
                self.assertLessEqual(set(stream.get('tags', {})), {'language', 'handler_name', 'vendor_id'})
                self.assertNotIn('Private', json.dumps(stream.get('tags', {})))
            self.assertEqual(self.source.read_bytes(),self.before)
    def test_cancel_cleans_output(self):
        work=self.root/'cancel';work.mkdir()
        events=self.request({'action':'process','source':str(self.source),'workdir':str(work)},cancel=True)
        self.assertEqual(events[-1]['type'],'cancelled',events)
        self.assertFalse(work.exists())
    def test_invalid_file_reports_json(self):
        events=self.request({'action':'probe','source':str(self.root/'missing.mp4')})
        self.assertEqual(events[-1]['type'],'error')

if __name__=='__main__':
    unittest.main()
