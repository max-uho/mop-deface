"""Release validation and artifact staging; no third-party Python dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'aarch64-apple-darwin': {'.dmg'},
    'x86_64-apple-darwin': {'.dmg'},
    'x86_64-pc-windows-msvc': {'.exe'},
    'x86_64-unknown-linux-gnu': {'.AppImage', '.deb'},
}


def version():
    value = json.loads((ROOT / 'package.json').read_text())['version']
    versions = [json.loads((ROOT / 'package-lock.json').read_text())['version'],
                json.loads((ROOT / 'src-tauri/tauri.conf.json').read_text())['version'],
                tomllib.loads((ROOT / 'src-tauri/Cargo.toml').read_text())['package']['version']]
    lock = tomllib.loads((ROOT / 'src-tauri/Cargo.lock').read_text())
    versions += [p['version'] for p in lock['package'] if p['name'] == 'mop-deface']
    if any(v != value for v in versions):
        raise ValueError('Application versions and lockfiles disagree')
    tag = os.environ.get('GITHUB_REF', '')
    if tag.startswith('refs/tags/') and tag != 'refs/tags/v' + value:
        raise ValueError(f'Tag must be v{value}')
    return value


def stage(target, signed, destination):
    bundle = ROOT / f'src-tauri/target/{target}/release/bundle'
    destination.mkdir(parents=True, exist_ok=True)
    installers = sorted(p for p in bundle.rglob('*') if p.is_file() and p.suffix in TARGETS[target])
    if len(installers) != len(TARGETS[target]) or {p.suffix for p in installers} != TARGETS[target]:
        raise ValueError(f'Expected {TARGETS[target]} installers, got {installers}')
    status = 'signed' if signed else 'unsigned'
    assets = []
    for path in installers:
        name = f'Deface-{version()}-{target}-{status}{path.suffix}'
        shutil.copy2(path, destination / name)
        assets.append(name)
    # Corresponding GPL sources plus exact build recipe and notices accompany each native build.
    sources = list((ROOT / 'build/sources').glob('*.tar.*'))
    if len(sources) != 2:
        raise ValueError('Missing corresponding FFmpeg/x264 source archives')
    archive = destination / f'Deface-{version()}-{target}-sources-notices.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sources + [ROOT / 'scripts/build_ffmpeg.sh', ROOT / 'scripts/sources.lock.json',
                              ROOT / 'scripts/verify_sources.py', ROOT / 'licenses',
                              ROOT / 'src-tauri/resources/licenses', ROOT / 'LICENSING.md']:
            tar.add(path, arcname=str(path.relative_to(ROOT)))
    manifest = {'target': target, 'version': version(), 'signing': status, 'installers': assets,
                'commit': os.environ.get('GITHUB_SHA'), 'sources': archive.name}
    (destination / f'{target}.json').write_text(json.dumps(manifest, indent=2) + '\n')


def aggregate(directory):
    manifests = [json.loads(p.read_text()) for p in directory.glob('*.json')]
    if len(manifests) != 4 or {m['target'] for m in manifests} != set(TARGETS):
        raise ValueError('All four successful native builds are required')
    lines = ['Offline video face anonymization. Review every video before sharing.', '',
             'Signing status (verified by the native build jobs):', '']
    expected = set()
    for m in sorted(manifests, key=lambda m: m['target']):
        if m['version'] != version() or m['signing'] not in ('signed', 'unsigned'):
            raise ValueError('Invalid release manifest')
        if m['commit'] != os.environ.get('GITHUB_SHA'):
            raise ValueError('Build commit mismatch')
        if len(m['installers']) != len(TARGETS[m['target']]):
            raise ValueError('Incomplete installer manifest')
        expected.update(m['installers'] + [m['sources']])
        lines.append(f"- {m['target']}: **{m['signing']}**")
    for name in expected:
        if Path(name).name != name or not (directory / name).is_file():
            raise ValueError(f'Missing/invalid asset: {name}')
    actual = {p.name for p in directory.iterdir() if p.suffix in {'.dmg', '.exe', '.deb', '.AppImage'}}
    if actual != {n for m in manifests for n in m['installers']}:
        raise ValueError('Unexpected or missing installers')
    checksums = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != 'SHA256SUMS':
            with path.open('rb') as file:
                checksums.append(f'{hashlib.file_digest(file, "sha256").hexdigest()}  {path.name}')
    (directory / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
    lines += ['', 'Unsigned macOS builds are ad-hoc signed, without Apple notarization. '
              'Unsigned Windows builds can trigger SmartScreen. Signing does not guarantee absence of warnings.',
              '', 'These are initial builds; clean-machine validation is not complete. '
              'See LICENSING.md in the repository and accompanying sources/notices for unresolved redistribution questions.']
    (ROOT / 'build/release-notes.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['version', 'stage', 'aggregate'])
    parser.add_argument('--target', choices=TARGETS)
    parser.add_argument('--signed', action='store_true')
    parser.add_argument('--directory', type=Path, default=ROOT / 'build/release-assets')
    args = parser.parse_args()
    if args.command == 'version':
        print(version())
    elif args.command == 'stage':
        stage(args.target, args.signed, args.directory)
    else:
        aggregate(args.directory)
