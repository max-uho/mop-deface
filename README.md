# Deface desktop

Offline Tauri 2 / React / TypeScript application using the actual PyPI deface 1.5.0 package and its CenterFace detector and anonymize_frame API. Always dark. No settings, accounts, onboarding, network calls, telemetry, or automatic saves. Processed/exported videos discard source EXIF/XMP, GPS/location, camera/device, author, creation-time, stream metadata and chapters. MP4 playback structure (codec/dimensions/frame rate, container brands and generic stream identifiers) remains.

Drop a video or choose a file → automatic anonymization → switch between original and processed preview → Save MP4. Default strong blur, threshold 0.2, mask scale 1.3; detection scaled proportionally to fit 1280 × 720 (output stays at source resolution); first audio stream preserved and transcoded to AAC. The output retains source dimensions and average frame rate. Variable-frame-rate input becomes constant-frame-rate; original timestamps, rotation metadata, HDR, subtitles, chapters, extra audio tracks, and container metadata are not preserved. Odd dimensions use yuv444p, which some webviews cannot preview. Linux DEBs declare GStreamer codec dependencies and AppImages request a bundled media framework; clean-machine codec playback still needs verification. Review the entire video before sharing.

## Build prerequisites (developers only)

Node 24+, Rust stable, Python 3.14, a C compiler, make, pkg-config and curl. Install platform Tauri prerequisites: https://v2.tauri.app/start/prerequisites/. Windows video tool builds require MSYS2 MINGW64. End users need none of these. Windows installers include the offline WebView2 installer; AppImage builds request the media framework, and DEBs declare codec dependencies.

```sh
npm ci
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
bash scripts/build_ffmpeg.sh
.venv/bin/python scripts/build_sidecar.py --tools build/video-tools/bin
npm run desktop
npm run tauri -- build
```

On Windows use `.venv\Scripts\python.exe` and run the video-tools script in MSYS2. Sidecars must be built on their own architecture. The build script names each binary using the Tauri target triple. GitHub Actions builds macOS ARM64/x86_64, Windows x86_64, Linux x86_64 separately, then produces DMG, NSIS/MSI, AppImage/DEB through Tauri. The resource directory is resolved through Tauri APIs; frozen Python assets are resolved relative to PyInstaller's extraction directory.

This implementation uses PyInstaller **one-file** to avoid platform-dependent relocation of loader-relative libraries between Tauri executable/resource directories. All models, native libraries, and FFmpeg/ffprobe are inside the binary; nothing is downloaded at runtime. Startup extracts libraries to OS temporary storage and can take several seconds. PyInstaller removes its extraction directory on normal shutdown. A future one-folder optimization needs platform-specific bundle placement validation.

## Verification

```sh
npm run build
npm test
cargo test --locked --manifest-path src-tauri/Cargo.toml
DEFACE_TEST_SIDECAR="$PWD/src-tauri/binaries/deface-worker-aarch64-apple-darwin" \
DEFACE_TEST_TOOLS="$PWD/build/video-tools/bin" \
.venv/bin/python -m unittest discover -s tests -v
```

Tests exercise the real blur/mosaic/solid face-mask API (including frozen lazy dependencies), bounded FFmpeg shutdown after injected processing errors, real processing, frame rate/resolution, audio preservation/removal, Unicode/space paths, cancellation cleanup and structured error output. The frozen-sidecar test clears PATH so Python/FFmpeg cannot be discovered from developer tools. This is an offline isolation test, not full clean-machine installer verification. Before distribution, install each artifact in a clean VM/physical machine without development tools; test drag/drop, native dialogs, preview seeking/comparison, cancellation during decoding/encoding, repeated runs, disk-full errors, long/large videos and uninstall. Untested platforms are not verified.

## Architecture and lifecycle

Rust owns process spawning and the selected source/output state. The frontend has no shell or filesystem capability. tauri-plugin-shell is used only from Rust. Each sidecar accepts one JSON request over stdin, sends newline-delimited progress/completion/error events over stdout, and exits. Cancellation sends a control line: the worker terminates its actual FFmpeg subprocesses, stops inference after the current frame, cleans partial output, and exits. The window defers closing until cancellation finishes. Inference and video I/O run in a sidecar, export copies use a blocking thread pool. Progress reports actual frame counts with an indeterminate indicator; it never invents percentages.

Rust allocates OS temporary directories. Output is finalized and probed before playback; it is retained while needed for preview/export, then removed after export (preview switches to the saved file), when replaced, or when the app exits. Cancellation/error removes it immediately. Hard crashes or forced termination can leave OS temporary directories; OS cleanup or manual deletion is needed. Never delete another live instance's files.

Export uses create_new: existing destinations, symlinks and hardlinks cannot be overwritten, including the source. Choose a new filename if a native save dialog proposes replacement. Original files are opened read-only. Long videos stream one frame at a time; sufficient temporary disk space is required.

## Signing and public distribution

CI produces **unsigned development installers**, not public releases. See LICENSING.md for unresolved redistribution issues and required corresponding source packages. License texts and native build configuration are generated into the app's About dialog; Rust licenses are also shipped as a text inventory. Do not publish artifacts until the release review is complete.

macOS distribution needs a Developer ID Application certificate, signing identity/private key, hardened runtime, nested sidecar/library signing, and Apple notarization. Supply genuine Tauri signing/notarization secrets (`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, and supported Apple ID or App Store Connect API credentials) in a trusted release workflow; see https://v2.tauri.app/distribute/sign/macos/. Test stapled DMGs with Gatekeeper on a clean machine. The embedded PyInstaller executable and extracted native libraries must pass hardened-runtime validation; this has not been verified here.

Windows signing requires a real Authenticode certificate or signing service and a trusted timestamp. Configure Tauri's certificate thumbprint/digest/timestamp or signCommand with the real service. See https://v2.tauri.app/distribute/sign/windows/. Do not embed private keys or passwords in this repository. Unsigned installers can trigger SmartScreen.
