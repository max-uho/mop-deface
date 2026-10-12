"""Build on the target OS/architecture. Never cross-freeze Python."""
import argparse
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def target():
    machine = platform.machine().lower()
    if sys.platform == 'darwin':
        return ('aarch64' if machine in ('arm64', 'aarch64') else 'x86_64') + '-apple-darwin'
    if sys.platform == 'win32':
        return 'x86_64-pc-windows-msvc'
    return 'x86_64-unknown-linux-gnu'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', type=Path, required=True, help='Directory containing target-native ffmpeg and ffprobe')
    args = parser.parse_args()
    tools = args.tools.resolve()
    extension = '.exe' if sys.platform == 'win32' else ''
    for name in ('ffmpeg', 'ffprobe'):
        if not (tools / (name + extension)).is_file():
            raise SystemExit(f'Missing {name} in {tools}')
    configuration = subprocess.check_output([str(tools / ('ffmpeg' + extension)), '-buildconf'], stderr=subprocess.STDOUT).decode(errors='replace')
    if '--enable-nonfree' in configuration:
        raise SystemExit('Nonfree FFmpeg builds cannot be redistributed.')
    encoders = subprocess.check_output([str(tools / ('ffmpeg' + extension)), '-encoders'], stderr=subprocess.STDOUT).decode(errors='replace')
    if 'libx264' not in encoders:
        raise SystemExit('FFmpeg must include libx264.')
    licenses = ROOT / 'src-tauri/resources/licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    sections = [(ROOT / 'LICENSING.md').read_text(), 'FFmpeg build configuration\n' + configuration]
    for dist in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        sections.append(f'\n{name} {dist.version}\nLicense metadata: {dist.metadata.get("License-Expression", dist.metadata.get("License", "unspecified"))}')
        for file in dist.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice', 'copyright')) for part in file.parts):
                path = dist.locate_file(file)
                if path.is_file():
                    try:
                        sections.append(f'\n{name}/{file}\n' + path.read_text())
                    except UnicodeError:
                        pass
    for path in (ROOT / 'licenses').glob('*'):
        if path.is_file():
            sections.append('\n' + path.name + '\n' + path.read_text())
    # Include licenses shipped by every installed JS package.
    for path in (ROOT / 'node_modules').rglob('*'):
        if path.is_file() and path.name.lower().startswith(('license', 'notice', 'copying')):
            try:
                sections.append('\n' + str(path.relative_to(ROOT)) + '\n' + path.read_text())
            except UnicodeError:
                pass
    python_license = Path(sys.base_prefix) / ('LICENSE.txt' if os.name == 'nt' else 'lib/python' + platform.python_version_tuple()[0] + '.' + platform.python_version_tuple()[1] + '/LICENSE.txt')
    if python_license.exists():
        sections.append(python_license.read_text())
    (licenses / 'THIRD_PARTY.txt').write_text('\n'.join(sections), encoding='utf-8')
    (licenses / 'ffmpeg-buildconf.txt').write_text(configuration)
    # One-file avoids relocating PyInstaller's loader-relative libraries across
    # Tauri's different macOS/Linux/Windows resource layouts.
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', 'deface-worker', '--distpath', str(ROOT / 'sidecar-dist'), '--workpath', str(ROOT / 'build/pyinstaller'), '--specpath', str(ROOT / 'build'), '--recursive-copy-metadata', 'deface', '--collect-all', 'deface', '--collect-all', 'onnx', '--collect-all', 'onnxruntime', '--collect-all', 'cv2', '--collect-all', 'skimage', '--hidden-import', 'skimage.draw', '--exclude-module', 'tkinter', '--exclude-module', 'matplotlib', '--exclude-module', 'pytest', '--add-binary', f'{tools / ("ffmpeg" + extension)}{os.pathsep}tools', '--add-binary', f'{tools / ("ffprobe" + extension)}{os.pathsep}tools', str(ROOT / 'backend/worker.py')]
    identity = os.environ.get('APPLE_SIGNING_IDENTITY')
    if sys.platform == 'darwin' and identity and identity != '-':
        # PyInstaller signs collected extensions/libraries and the bootloader before
        # embedding them, so the one-file extraction also works with hardened runtime.
        command[3:3] = ['--codesign-identity', identity, '--osx-entitlements-file',
                        str(ROOT / 'src-tauri/entitlements.plist')]
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    subprocess.run(command, check=True, cwd=ROOT, env=environment)
    destination = ROOT / 'src-tauri/binaries' / ('deface-worker-' + target() + extension)
    staged = destination.with_name(destination.name + '.staged')
    shutil.copy2(ROOT / 'sidecar-dist' / ('deface-worker' + extension), staged)
    os.replace(staged, destination)
    print(destination)

if __name__ == '__main__':
    main()
