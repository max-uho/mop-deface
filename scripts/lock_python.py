"""Lock the tested Python environment with all upstream artifact hashes.
Run only when intentionally upgrading dependencies; commit the resulting lock.
"""
import concurrent.futures
import importlib.metadata as md
import json
from pathlib import Path
import urllib.request

def entry(item):
    name, version, marker = item
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=60) as response:
        data = json.load(response)
    hashes = sorted({f['digests']['sha256'] for f in data['urls']})
    if not hashes:
        raise ValueError(f'No artifacts for {name}')
    return f'{name}=={version}{marker} \\\n' + ' \\\n'.join('    --hash=sha256:' + digest for digest in hashes)

if __name__ == '__main__':
    packages = [(d.metadata['Name'], d.version, '') for d in md.distributions() if d.metadata['Name'].lower() != 'pip']
    intel = '; sys_platform == "darwin" and platform_machine == "x86_64"'
    other = '; sys_platform != "darwin" or platform_machine != "x86_64"'
    packages = [(n, v, other if n.lower() == 'onnxruntime' else m) for n, v, m in packages]
    packages.extend([('onnxruntime', '1.20.1', intel), ('coloredlogs', '15.0.1', intel), ('humanfriendly', '10.0', intel)])
    packages.extend([('pywin32-ctypes', '0.2.3', '; sys_platform == "win32"'), ('pefile', '2024.8.26', '; sys_platform == "win32"'), ('colorama', '0.4.6', '; sys_platform == "win32"')])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        content = '\n\n'.join(pool.map(entry, sorted(packages)))
    root = Path(__file__).resolve().parents[1]
    (root / 'backend/requirements.lock').write_text('# Python 3.14; macOS Intel uses Python 3.12 / ONNX Runtime 1.20.1. All artifacts SHA256 locked.\n' + content + '\n')
