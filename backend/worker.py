"""One request per process. stdout is exclusively newline-delimited JSON."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

for stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

CANCEL = threading.Event()
PROCESSES = []
POPEN_OPTIONS = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

def emit(kind, **data):
    print(json.dumps({'type': kind, **data}, ensure_ascii=False), flush=True)

def tool(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    path = root / 'tools' / (name + ('.exe' if os.name == 'nt' else ''))
    if not path.is_file():
        raise RuntimeError(f'Bundled {name} is missing. Rebuild the sidecar.')
    return str(path)

def run(args):
    if CANCEL.is_set():
        raise InterruptedError('Cancelled')
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **POPEN_OPTIONS)
    PROCESSES.append(process)
    out, err = process.communicate()
    PROCESSES.remove(process)
    if CANCEL.is_set():
        raise InterruptedError('Cancelled')
    if process.returncode:
        raise RuntimeError(err.decode('utf-8', errors='replace')[-3000:])
    return out

def metadata(path):
    info = json.loads(run([tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video:
        raise ValueError('The selected file has no video stream.')
    return {'width': video['width'], 'height': video['height'], 'fps': video.get('avg_frame_rate'), 'duration': float(info.get('format', {}).get('duration', 0)), 'codec': video['codec_name'], 'audio': any(s['codec_type'] == 'audio' for s in info['streams'])}

def process(req):
    if CANCEL.is_set():
        raise InterruptedError('Cancelled')
    source = Path(req['source']).resolve(strict=True)
    mode = req.get('mode', 'blur')
    threshold = float(req.get('threshold', .2))
    mosaic = int(req.get('mosaic', 20))
    if mode not in ('blur', 'mosaic', 'solid') or not .01 <= threshold <= .99 or not 4 <= mosaic <= 100:
        raise ValueError('Invalid anonymization settings.')
    meta = metadata(source)
    w, h = meta['width'], meta['height']
    fps = meta['fps']
    if not fps or fps == '0/0':
        raise ValueError('Source frame rate is unavailable.')
    emit('metadata', metadata=meta)
    emit('progress', message='Loading detector…')
    import numpy as np
    # Keep upstream diagnostic output off the protocol channel.
    with contextlib.redirect_stdout(sys.stderr):
        from deface.centerface import CenterFace
        from deface.deface import anonymize_frame
        scale = min(1.0, 1280 / w, 720 / h)
        detector = CenterFace(in_shape=(max(1, round(w * scale)), max(1, round(h * scale))), backend='onnxrt', override_execution_provider='CPUExecutionProvider')
    emit('progress', message='Anonymizing video…')
    output = Path(req['workdir']) / 'result.mp4'
    raw = output.with_name('silent.mp4')
    decode_log = open(Path(req['workdir']) / 'decode.log', 'wb')
    decode = subprocess.Popen([tool('ffmpeg'), '-nostdin', '-v', 'error', '-noautorotate', '-i', str(source), '-map', '0:v:0', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=decode_log, **POPEN_OPTIONS)
    decode_log.close()
    PROCESSES.append(decode)
    # yuv444p retains odd dimensions; common even dimensions use yuv420p.
    pixel_format = 'yuv420p' if w % 2 == 0 and h % 2 == 0 else 'yuv444p'
    encode_log = open(Path(req['workdir']) / 'encode.log', 'wb')
    encode = subprocess.Popen([tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', fps, '-i', '-', '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', pixel_format, '-movflags', '+faststart', str(raw)], stdin=subprocess.PIPE, stderr=encode_log, **POPEN_OPTIONS)
    encode_log.close()
    PROCESSES.append(encode)
    frames = 0
    try:
        size = w * h * 3
        while not CANCEL.is_set():
            data = bytearray()
            while len(data) < size:
                chunk = decode.stdout.read(size - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            if not data:
                break
            if len(data) != size:
                raise RuntimeError('Incomplete decoded frame.')
            frame = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3).copy()
            dets, _ = detector(frame, threshold=threshold)
            anonymize_frame(dets, frame, mask_scale=1.3, replacewith=mode, ellipse=mode != 'solid', draw_scores=False, replaceimg=None, mosaicsize=mosaic)
            encode.stdin.write(frame.tobytes())
            frames += 1
            if frames == 1 or frames % 5 == 0:
                emit('progress', frames=frames, message=f'Anonymized {frames} frames')
        if CANCEL.is_set():
            raise InterruptedError('Cancelled')
        encode.stdin.close()
        if decode.wait() != 0 or encode.wait() != 0 or frames == 0:
            raise RuntimeError('Video decoding/encoding failed. Source may be damaged or unsupported.')
        emit('progress', frames=frames, message='Finalizing video and audio…')
        args = [tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-i', str(raw)]
        if not req.get('removeAudio', False) and meta['audio']:
            args += ['-i', str(source), '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'copy', '-c:a', 'aac']
        else:
            args += ['-map', '0:v:0', '-c:v', 'copy', '-an']
        # Disable automatic copying from every input, including preserved audio.
        # Raw decoded frames carry no EXIF/XMP; the final mux must not restore
        # container, stream or chapter tags from the original.
        run(args + ['-map_metadata', '-1', '-map_metadata:s', '-1',
                    '-map_chapters', '-1', '-fflags', '+bitexact',
                    '-metadata', 'encoder=', '-metadata:s', 'encoder=',
                    '-movflags', '+faststart', str(output)])
        metadata(output)
        raw.unlink()
        return {'path': str(output), 'metadata': meta, 'frames': frames}
    finally:
        # Close both pipe endpoints before waiting: FFmpeg may be blocked in a
        # pipe write/read and SIGTERM alone does not reliably unblock it.
        for child in list(PROCESSES):
            for stream in (child.stdin, child.stdout):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if child.poll() is None:
                child.terminate()
        for child in list(PROCESSES):
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        PROCESSES.clear()

def cancel_listener():
    for line in sys.stdin:
        if line.strip():
            CANCEL.set()
            for child in list(PROCESSES):
                try:
                    child.kill()
                except OSError:
                    pass
            return
    CANCEL.set()
    for child in list(PROCESSES):
        try:
            child.kill()
        except OSError:
            pass

def selftest():
    import numpy as np
    from deface.deface import anonymize_frame
    original = np.arange(96 * 96 * 3, dtype=np.uint8).reshape(96, 96, 3)
    dets = np.array([[20., 20., 60., 60., .9]])
    for mode in ('blur', 'mosaic', 'solid'):
        frame = original.copy()
        anonymize_frame(dets, frame, mask_scale=1.3, replacewith=mode,
                        ellipse=mode != 'solid', draw_scores=False,
                        replaceimg=None, mosaicsize=20)
        if np.array_equal(frame, original):
            raise RuntimeError(f'{mode} did not modify the test face region')
    return {'message': 'All deface face-mask methods passed'}

def main():
    req = json.loads(sys.stdin.readline())
    threading.Thread(target=cancel_listener, daemon=True).start()
    try:
        if req['action'] == 'selftest':
            result = selftest()
        elif req['action'] == 'probe':
            result = {'metadata': metadata(Path(req['source']).resolve(strict=True))}
        elif req['action'] == 'process':
            result = process(req)
        else:
            raise ValueError('Unknown request')
        if CANCEL.is_set():
            raise InterruptedError('Cancelled')
        emit('complete', **result)
    except InterruptedError:
        emit('cancelled')
    except Exception as exc:
        if CANCEL.is_set():
            emit('cancelled')
        else:
            emit('error', message=str(exc))
    finally:
        if req.get('workdir') and (CANCEL.is_set() or not (Path(req['workdir']) / 'result.mp4').is_file()):
            shutil.rmtree(req['workdir'], ignore_errors=True)

if __name__ == '__main__':
    main()
