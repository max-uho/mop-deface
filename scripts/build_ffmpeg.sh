#!/usr/bin/env bash
set -euo pipefail
# Run in native Unix or the MSYS2 MINGW64 shell on Windows.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="$ROOT/build/video-tools"
mkdir -p "$PREFIX" "$ROOT/build/sources"
cd "$ROOT/build/sources"
curl -fL --retry 3 https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz -o ffmpeg-8.0.1.tar.xz
curl -fL --retry 3 https://codeload.github.com/mirror/x264/tar.gz/31e19f92f00c7003fa115047ce50978bc98c3a0d -o x264.tar.gz
python3 "$ROOT/scripts/verify_sources.py"
tar xf ffmpeg-8.0.1.tar.xz
tar xf x264.tar.gz
cd x264-31e19f92f00c7003fa115047ce50978bc98c3a0d
./configure --prefix="$PREFIX" --enable-static --disable-cli --disable-opencl --disable-asm
make -j4
make install
cd ../ffmpeg-8.0.1
EXTRA_LINK="-L$PREFIX/lib"
case "$(uname -s)" in MINGW*|MSYS*) EXTRA_LINK="$EXTRA_LINK -static" ;; esac
PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ./configure --prefix="$PREFIX" --pkg-config-flags=--static --extra-cflags="-I$PREFIX/include" --extra-ldflags="$EXTRA_LINK" --enable-gpl --enable-libx264 --disable-shared --enable-static --disable-doc --disable-debug --disable-autodetect --disable-x86asm --disable-network
make -j4
make install
mkdir -p "$ROOT/licenses"
cp COPYING.GPLv2 "$ROOT/licenses/FFmpeg-GPL-2.0.txt"
cp ../x264-31e19f92f00c7003fa115047ce50978bc98c3a0d/COPYING "$ROOT/licenses/x264-GPL-2.0.txt"
