import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name, digest in json.loads((root / 'scripts/sources.lock.json').read_text()).items():
    actual = hashlib.sha256((root / 'build/sources' / name).read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f'Source checksum mismatch: {name}')
