"""Prepare native signing. Missing secrets means unsigned; partial secrets fail."""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
BUILD.mkdir(exist_ok=True)


def run(*args):
    subprocess.run(args, check=True)


def stapler(action, path):
    # Error 68 is Apple's ticket-service/network failure, not a signature failure.
    for attempt in range(5):
        try:
            run('xcrun', 'stapler', action, str(path))
            return
        except subprocess.CalledProcessError as error:
            if error.returncode != 68 or attempt == 4:
                raise
            print('Apple ticket service unavailable; retrying stapler', flush=True)
            time.sleep(10 * (attempt + 1))


def export(name, value):
    # GitHub masks supplied secrets. Never print secret values.
    if '\n' in value or '\r' in value:
        raise ValueError(f'{name} must be a single line')
    with open(os.environ['GITHUB_ENV'], 'a') as file:
        file.write(f'{name}={value}\n')


def complete(names):
    present = [bool(os.environ.get(n)) for n in names]
    if any(present) and not all(present):
        raise ValueError('Incomplete signing secrets: ' + ', '.join(n for n, p in zip(names, present) if not p))
    return all(present)


def prepare():
    config = {}
    signed = False
    if sys.platform == 'darwin':
        names = ['APPLE_CERTIFICATE', 'APPLE_CERTIFICATE_PASSWORD', 'APPLE_SIGNING_IDENTITY',
                 'APPLE_ID', 'APPLE_PASSWORD', 'APPLE_TEAM_ID']
        signed = complete(names)
        identity = os.environ['APPLE_SIGNING_IDENTITY'] if signed else '-'
        if signed:
            if not identity.startswith('Developer ID Application:'):
                raise ValueError('A Developer ID Application identity is required')
            keychain = str(BUILD / 'signing.keychain-db')
            password = secrets.token_urlsafe(32)
            certificate = BUILD / 'certificate.p12'
            certificate.write_bytes(base64.b64decode(os.environ['APPLE_CERTIFICATE'], validate=True))
            try:
                run('security', 'create-keychain', '-p', password, keychain)
                run('security', 'set-keychain-settings', '-lut', '21600', keychain)
                run('security', 'unlock-keychain', '-p', password, keychain)
                run('security', 'import', str(certificate), '-k', keychain, '-P',
                    os.environ['APPLE_CERTIFICATE_PASSWORD'], '-T', '/usr/bin/codesign')
                run('security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:',
                    '-s', '-k', password, keychain)
                run('security', 'list-keychains', '-d', 'user', '-s', keychain, 'login.keychain-db')
                run('security', 'find-identity', '-v', '-p', 'codesigning', keychain)
            finally:
                certificate.unlink(missing_ok=True)
            for name in ['APPLE_ID', 'APPLE_PASSWORD', 'APPLE_TEAM_ID']:
                export(name, os.environ[name])
        export('APPLE_SIGNING_IDENTITY', identity)
        config = {'bundle': {'macOS': {'signingIdentity': identity, 'hardenedRuntime': signed,
                                      'entitlements': 'entitlements.plist'}}}
    elif sys.platform == 'win32':
        names = ['AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID',
                 'AZURE_SIGNING_ENDPOINT', 'AZURE_ARTIFACT_SIGNING_ACCOUNT',
                 'AZURE_ARTIFACT_SIGNING_CERTIFICATE_PROFILE']
        signed = complete(names)
        if signed:
            for name in names:
                export(name, os.environ[name])
            config = {'bundle': {'windows': {'signCommand': {
                'cmd': 'python', 'args': ['../scripts/sign_windows.py', '%1']}}}}
    export('SIGNING_STATUS', 'signed' if signed else 'unsigned')
    (BUILD / 'tauri-ci.json').write_text(json.dumps(config))
    print('Signing status: ' + ('signed (verification required)' if signed else 'unsigned'))


def verify_mac(target):
    bundle = ROOT / f'src-tauri/target/{target}/release/bundle'
    app = bundle / 'macos/Deface.app'
    run('codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app))
    stapler('validate', app)
    run('spctl', '--assess', '--type', 'execute', '--verbose=2', str(app))
    for dmg in bundle.glob('dmg/*.dmg'):
        run('codesign', '--verify', '--strict', str(dmg))
        result = subprocess.check_output(['xcrun', 'notarytool', 'submit', str(dmg), '--wait',
            '--apple-id', os.environ['APPLE_ID'], '--password', os.environ['APPLE_PASSWORD'],
            '--team-id', os.environ['APPLE_TEAM_ID'], '--output-format', 'json'])
        if json.loads(result)['status'] != 'Accepted':
            raise ValueError('DMG notarization was not accepted')
        stapler('staple', dmg)
        stapler('validate', dmg)
        run('spctl', '--assess', '--type', 'open', '--context', 'context:primary-signature',
            '--verbose=2', str(dmg))


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        verify_mac(sys.argv[2])
