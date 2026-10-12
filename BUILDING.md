# Building and releasing

## Native builds

Follow the [README setup](README.md#for-developers) and [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). Use native Python 3.14 (3.12 on Intel macOS), Node 24 and Rust stable. Do not cross-freeze the Python sidecar.

| Runner           | Sidecar target triple    | Installers    |
| ---------------- | ------------------------ | ------------- |
| macos-15 (ARM64) | aarch64-apple-darwin     | DMG           |
| macos-15-intel   | x86_64-apple-darwin      | DMG           |
| windows-2022     | x86_64-pc-windows-msvc   | NSIS EXE      |
| ubuntu-22.04     | x86_64-unknown-linux-gnu | AppImage, DEB |

`scripts/build_ffmpeg.sh` builds hash-verified FFmpeg/x264 sources with GPL enabled and networking disabled. Windows uses MSYS2 MINGW64. `scripts/build_sidecar.py --tools build/video-tools/bin` freezes Python, deface, ONNX models, native libraries, FFmpeg and ffprobe into `src-tauri/binaries/deface-worker-<triple>[.exe]`. The existing one-file layout is retained; it extracts its runtime into OS temporary storage. No runtime downloads or system Python/FFmpeg are required.

Node, Python and Cargo dependencies use committed lockfiles. CI caches npm, pip, Cargo and native video tools, verifies source hashes even after a cache hit, generates Python/frontend/Rust license inventories and ships corresponding GPL sources beside each installer. Windows bundles the offline WebView2 installer; Linux packages include/request media dependencies through the existing Tauri configuration.

## Tests

```sh
npm run build
npm test
cargo test --locked --manifest-path src-tauri/Cargo.toml
DEFACE_TEST_TOOLS="$PWD/build/video-tools/bin" \
DEFACE_TEST_SIDECAR="$PWD/src-tauri/binaries/deface-worker-aarch64-apple-darwin" \
.venv/bin/python -m unittest discover -s tests -v
```

Substitute the native triple and Windows `.exe` suffix. On PowerShell set `$env:DEFACE_TEST_TOOLS` and `$env:DEFACE_TEST_SIDECAR`, then use `.venv\Scripts\python.exe`. Frozen tests clear PATH and exercise real anonymization, audio, metadata removal, Unicode paths, errors and cancellation. They do not replace clean-machine installation and playback tests.

## GitHub Actions and publishing

PRs and pushes to `main` or the current default branch, `master`, build and test all platforms. Manual **Actions → Desktop build and release → Run workflow** also builds. PRs and branch builds receive no signing credentials and never publish.

To release, update the matching version in `package.json`, `package-lock.json`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` and `src-tauri/tauri.conf.json`, commit and push, then:

```sh
git tag v0.1.1
git push origin v0.1.1
```

Use the actual new version. A tag must match every version file. A dispatch on an existing version tag can retry a release. Only the final job has `contents: write`. It runs only after all four native builds/tests/signature checks succeed, validates their commit/version/artifact manifests, creates `SHA256SUMS`, uploads five installers plus source/notice archives and manifests to a draft, then publishes it. Failed jobs publish nothing; upload/publishing failures can leave an unpublished draft. Delete that draft explicitly before retrying. Existing releases are never overwritten.

Each installer filename and release note says `signed` or `unsigned`. macOS ad-hoc signatures are labeled **unsigned**. Without signing secrets builds remain downloadable; partial secret configurations fail rather than silently downgrading. Signing credentials are read only on version tags, never PRs. Restrict repository tag creation and secret access to trusted maintainers.

## macOS signing secrets

Set all six repository Actions Secrets, or none:

| Secret                       | Value                                                                      |
| ---------------------------- | -------------------------------------------------------------------------- |
| `APPLE_CERTIFICATE`          | Base64-encoded Developer ID Application `.p12`, containing the private key |
| `APPLE_CERTIFICATE_PASSWORD` | Export password                                                            |
| `APPLE_SIGNING_IDENTITY`     | Full `Developer ID Application: … (TEAMID)` identity                       |
| `APPLE_ID`                   | Apple account email                                                        |
| `APPLE_PASSWORD`             | App-specific password for notarization                                     |
| `APPLE_TEAM_ID`              | Developer team ID                                                          |

Export the certificate/private key from Keychain Access and base64-encode the `.p12`. Never commit it. CI imports it into a temporary keychain before PyInstaller, which signs collected libraries, Python extensions, nested FFmpeg executables and its bootloader. Tauri signs the app with hardened runtime, notarizes it and staples its ticket. CI verifies the app using codesign, stapler and Gatekeeper, submits the DMG to `notarytool`, requires `Accepted`, staples and verifies the DMG. The temporary keychain is deleted even on failure. The Python runtime entitlement permits executable memory for native extension/libffi use.

Without credentials CI uses ad-hoc signing (`-`), with no notarization. Signed paths require verification with real credentials and a clean Mac before treating them as production-ready. See the [official macOS signing guide](https://v2.tauri.app/distribute/sign/macos/) and [PyInstaller signing notes](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing).

## Windows signing secrets

The workflow uses **Azure Artifact Signing**, not an exportable legacy certificate. Configure a signing account, validated public-trust certificate profile and a service principal with the **Artifact Signing Certificate Profile Signer** role at the appropriate scope. Set all six secrets, or none:

- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SIGNING_ENDPOINT` (your account's regional HTTPS endpoint)
- `AZURE_ARTIFACT_SIGNING_ACCOUNT`
- `AZURE_ARTIFACT_SIGNING_CERTIFICATE_PROFILE`

CI installs pinned `artifact-signing-cli` 0.11.0, uses the runner's Azure CLI/.NET/Windows SDK, and signs bundled FFmpeg tools before freezing, the frozen sidecar, the application executable and NSIS installer through Tauri's custom `signCommand`. SHA-256 signatures use Microsoft's RFC 3161 timestamp service. Every signing operation must produce a valid, timestamped Authenticode signature. Windows signing is unverified until run with real credentials; signing does not guarantee SmartScreen reputation. See the [official Windows signing guide](https://v2.tauri.app/distribute/sign/windows/).

## Optional Linux GPG signing

Set `GPG_PRIVATE_KEY` to an ASCII-armored private key and optionally `GPG_PASSPHRASE`. The final job imports it into an ephemeral keyring, signs AppImage, DEB and `SHA256SUMS`, verifies each detached signature, exports the public key and deletes the keyring. This is detached package signing, not a change to the package format. Without a key Linux artifacts remain unsigned. Obtain the public-key fingerprint from a separate trusted channel before trusting it.

## Release validation and licensing

Before promoting a release, install every architecture's package on a clean machine without developer tools. Check launch, offline processing, preview playback/seeking, export, cancellation, Unicode paths and uninstall. CI frozen-backend checks are automated coverage, not proof of clean-machine GUI operation. Signing/notarization cannot be verified locally without credentials.

Preserve all existing license texts. See [LICENSING.md](LICENSING.md): the application license, model provenance, wheel/native multimedia dependencies and redistribution obligations remain unresolved. Publishing a binary does not resolve those questions. Release notes disclose them rather than claiming legal clearance.

Intel macOS uses the last available ONNX Runtime Intel wheel, 1.20.1, with Python 3.12. ARM64 macOS, Windows and Linux use 1.24.3 with Python 3.14. The dependency lock includes platform markers and hashes for both; upgrading Intel requires a separately validated source build or newer compatible wheel.
