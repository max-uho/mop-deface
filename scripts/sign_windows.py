"""Azure Artifact Signing Authenticode signing; called by Tauri too."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
path = str(Path(sys.argv[1]).resolve())
subprocess.run(['artifact-signing-cli', '-e', os.environ['AZURE_SIGNING_ENDPOINT'],
                '-a', os.environ['AZURE_ARTIFACT_SIGNING_ACCOUNT'],
                '-c', os.environ['AZURE_ARTIFACT_SIGNING_CERTIFICATE_PROFILE'],
                '-d', 'Deface', path], check=True)
# Validate Authenticode trust, timestamp and the entire signature after every signing operation.
subprocess.run(['powershell', '-NoProfile', '-Command',
                '$s=Get-AuthenticodeSignature -LiteralPath $env:DEFACE_SIGNED_FILE; '
                'if ($s.Status -ne "Valid" -or !$s.TimeStamperCertificate) { throw "Invalid Authenticode signature or missing timestamp" }'], check=True, env={**os.environ, 'DEFACE_SIGNED_FILE': path})
