import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ci_release, ci_signing


class ReleaseTests(unittest.TestCase):
    def test_tag_version_must_match(self):
        with patch.dict(os.environ, {'GITHUB_REF': 'refs/tags/v999.0.0'}):
            with self.assertRaises(ValueError):
                ci_release.version()

    def test_partial_credentials_fail_and_empty_is_unsigned(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ci_signing.complete(['ONE', 'TWO']))
            os.environ['ONE'] = 'test'
            with self.assertRaises(ValueError):
                ci_signing.complete(['ONE', 'TWO'])

    def test_complete_release_requires_all_platforms_and_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaises(ValueError):
                ci_release.aggregate(directory)
            for target, suffixes in ci_release.TARGETS.items():
                names = [f'Deface-{ci_release.version()}-{target}-unsigned{s}' for s in suffixes]
                source = f'{target}-sources.tar.gz'
                for name in names + [source]:
                    (directory / name).write_bytes(b'installer fixture')
                (directory / f'{target}.json').write_text(json.dumps({
                    'target': target, 'version': ci_release.version(), 'signing': 'unsigned',
                    'commit': 'test-commit', 'sources': source, 'installers': names}))
            with patch.dict(os.environ, {'GITHUB_SHA': 'test-commit'}):
                ci_release.aggregate(directory)
                self.assertEqual(len((directory / 'SHA256SUMS').read_text().splitlines()), 5)
                next(directory.glob('*.dmg')).unlink()
                with self.assertRaises(ValueError):
                    ci_release.aggregate(directory)

    def test_build_commit_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for target, suffixes in ci_release.TARGETS.items():
                (directory / f'{target}.json').write_text(json.dumps({
                    'target': target, 'version': ci_release.version(), 'signing': 'unsigned',
                    'commit': 'another-commit', 'sources': 'missing.tar.gz',
                    'installers': ['missing' + s for s in suffixes]}))
            with patch.dict(os.environ, {'GITHUB_SHA': 'expected-commit'}):
                with self.assertRaisesRegex(ValueError, 'commit mismatch'):
                    ci_release.aggregate(directory)


if __name__ == '__main__':
    unittest.main()
