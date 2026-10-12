# Deface desktop

Blur faces in your videos on your own computer.

<img width="872" height="759" alt="Screenshot 2026-10-08 at 10 37 18" src="https://github.com/user-attachments/assets/36061871-199b-4e4b-b606-5b9e37ae71d2" />

## Download

[Download the latest release](https://github.com/max-uho/mop-deface/releases/latest).

Choose the installer for your computer: macOS Apple Silicon or Intel (`.dmg`), Windows x64 (`.exe`), or Linux x64 (`.AppImage` or `.deb`). Python and FFmpeg are included.

Check the release notes for signing status. Unsigned macOS installers are not notarized and may need approval in **System Settings → Privacy & Security**. Windows may display a SmartScreen warning. Only install files from a source you trust. Initial builds still need clean-machine testing on each platform.

## What it does

Deface automatically detects and blurs faces, then lets you compare the original and processed video before saving an MP4. It keeps the original file untouched, preserves audio, and removes source metadata such as location, camera details and creation dates. Processing can be cancelled. There are no settings or accounts.

## How to use

1. Drop a video into the window, or choose a file.
2. Let Deface anonymize it automatically.
3. Review the entire processed video. Switch to the original to compare.
4. Choose **Save MP4** and a new filename.

## Privacy

Video processing happens locally. Videos are never uploaded. The app has no cloud service or telemetry. Temporary video files are removed after saving, replacement or normal exit; a forced shutdown can leave temporary files behind.

## Limitations

Automatic detection can miss faces. Review the entire video before sharing.

Large videos need enough temporary disk space. Output keeps source resolution and average frame rate where possible, but does not preserve variable frame timing, HDR, rotation metadata, subtitles or extra audio tracks. Some source formats and odd-sized videos may not preview in the system webview.

## Maintenance

This project is unlikely to receive regular maintenance.
If you find it useful, please fork it and continue its
development. Contributions are welcome, but responses
and updates are not guaranteed.

## For developers

Use Node.js 24, Python 3.14 (3.12 on Intel macOS), Rust stable and the [Tauri platform prerequisites](https://v2.tauri.app/start/prerequisites/). Build on the target operating system and CPU architecture.

```sh
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
bash scripts/build_ffmpeg.sh
.venv/bin/python scripts/build_sidecar.py --tools build/video-tools/bin
npm run desktop
```

On Windows, use `py -3.14 -m venv .venv` and `.venv\Scripts\python.exe`; run the FFmpeg script in an MSYS2 MINGW64 shell with GCC, make, curl, tar, pkgconf and Python installed.

Package with `npm run tauri -- build --bundles app,dmg -- --locked` on macOS, `--bundles nsis -- --locked` on Windows, or `--bundles appimage,deb -- --locked` on Linux. Run `npm test`, `cargo test --locked --manifest-path src-tauri/Cargo.toml`, and Python tests as described in [BUILDING.md](BUILDING.md).

[BUILDING.md](BUILDING.md) covers native CI builds, signing secrets and release publishing. The backend uses the real [deface](https://github.com/ORB-HD/deface) package, frozen with PyInstaller; no detector is reimplemented.

## Licensing

An application license has not yet been selected. Public source availability does not grant a general reuse license.

Third-party dependencies include deface and CenterFace (MIT), ONNX Runtime (MIT), OpenCV and ONNX (Apache-2.0), Python (PSF), Tauri (MIT/Apache-2.0), and frontend libraries with their own notices. Bundled FFmpeg and x264 use GPL licenses; corresponding sources and build recipes accompany releases. See [LICENSING.md](LICENSING.md) for notices and unresolved redistribution questions. Dependency notices are also available in the app’s About dialog.
