"""Replay a frozen photo panel against one API instance and record server CPU per scan.

Runs inside the API container (needs app.recognition.detect and cgroup v2). CPU is the
container cgroup's usage delta, measured until the server has been idle for a moment,
so background grading and OCR work after the response is counted. Memory per scan is
the server process's resident set (VmRSS) and its high-water mark (VmHWM, peak RSS since
start) from /proc, plus the container cgroup's memory.peak where the kernel provides it.

Modes (phone behaviour is simulated from the photo, nothing else is sent):
  --hint   send graded=true for slab photos and graded=false for all others
  --quad   send the server detector's own card corners as card_quad
  --warp   upload the server-warped card with skip_detect=true
"""
import argparse
import json
from pathlib import Path
import sys
import time

import httpx
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, '/app')
from app.recognition.detect import server_frame_rect, warp_to_rect  # noqa: E402

CPU_STAT = Path('/sys/fs/cgroup/cpu.stat')
MEMORY_PEAK = Path('/sys/fs/cgroup/memory.peak')


SERVER_PID = None


def cpu_usec():
    """CPU microseconds used by the server: the container cgroup, or the process tree with --server-pid."""
    if SERVER_PID is not None:
        import psutil
        root = psutil.Process(SERVER_PID)
        total = 0.0
        for proc in [root, *root.children(recursive=True)]:
            try:
                times = proc.cpu_times()
                total += times.user + times.system
            except psutil.Error:
                pass
        return int(total * 1e6)
    for line in CPU_STAT.read_text().splitlines():
        if line.startswith('usage_usec'):
            return int(line.split()[1])


def memory_mb():
    """Server RSS now and its peak (MiB): --server-pid's tree, else PID 1 (the API in its container)."""
    pid = SERVER_PID or 1
    if SERVER_PID is not None:
        import psutil
        root = psutil.Process(pid)
        pids = [root.pid, *(child.pid for child in root.children(recursive=True))]
    else:
        pids = [pid]
    rss = hwm = 0
    for each in pids:
        try:
            fields = dict(line.split(':', 1) for line in Path(f'/proc/{each}/status').read_text().splitlines())
        except OSError:
            continue
        rss += int(fields.get('VmRSS', '0 kB').split()[0])
        hwm += int(fields.get('VmHWM', '0 kB').split()[0])
    out = dict(rss_mb=round(rss / 1024, 1), peak_rss_mb=round(hwm / 1024, 1))
    if SERVER_PID is None and MEMORY_PEAK.exists():
        out['cgroup_peak_mb'] = round(int(MEMORY_PEAK.read_text()) / (1 << 20), 1)
    return out


def settle(idle=1.2, limit=20):
    """Wait until the cgroup burns no CPU for `idle` seconds; return the final reading."""
    last, quiet, end = cpu_usec(), time.time(), time.time() + limit
    while time.time() < end:
        time.sleep(.25)
        now = cpu_usec()
        if now - last > 20_000:
            last, quiet = now, time.time()
        elif time.time() - quiet >= idle:
            break
    return last


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--panel', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--url', default='http://127.0.0.1:8000/api/v1/scans')
    p.add_argument('--hint', action='store_true')
    p.add_argument('--quad', action='store_true')
    p.add_argument('--warp', action='store_true')
    p.add_argument('--limit', type=int, default=10**9)
    p.add_argument('--server-pid', type=int)
    a = p.parse_args()
    global SERVER_PID
    SERVER_PID = a.server_pid
    cases = json.loads(a.panel.read_text())[:a.limit]
    with httpx.Client(timeout=120) as client, a.out.open('w') as handle:
        for case in cases:
            path = a.root / case['photo_file']
            data, form = path.read_bytes(), {'language': 'auto'}
            if a.hint:
                form['graded'] = 'true' if case['kind'] == 'slab' else 'false'
            if a.quad or a.warp:
                image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
                rect = server_frame_rect(image)
                if rect is not None and a.quad:
                    w, h = image.size
                    form['card_quad'] = ','.join(f'{x / (w - 1):.4f},{y / (h - 1):.4f}' for x, y in rect)
                    form['quad_source'] = 'replay'
                if rect is not None and a.warp:
                    import io
                    buffer = io.BytesIO()
                    warp_to_rect(image, rect).save(buffer, 'JPEG', quality=95)
                    data, form['skip_detect'] = buffer.getvalue(), 'true'
            before = settle()
            started = time.perf_counter()
            reply = client.post(a.url, data=form, files={'image': (path.name, data, 'image/jpeg')})
            http_ms = (time.perf_counter() - started) * 1000
            after = settle()
            body = reply.json() if reply.status_code == 200 else {}
            best = body.get('best_match') or {}
            row = dict(id=case['id'], kind=case['kind'], expected=case.get('expected_card_ids', []),
                http=reply.status_code, http_ms=http_ms, cpu_ms=(after - before) / 1000,
                status=body.get('status'), card_id=best.get('card_id'),
                alternatives=[s.get('card_id') for s in body.get('suggestions', [])][:5],
                ocr=(body.get('ocr') or {}), grading=body.get('grading'),
                timings=body.get('timings_ms'), printing=(body.get('confidence') or {}).get('printing'),
                quad_sent='card_quad' in form, warped='skip_detect' in form, **memory_mb())
            handle.write(json.dumps(row) + '\n')
            handle.flush()
            print(case['id'], reply.status_code, round(row['cpu_ms']), round(http_ms), row['status'], flush=True)


if __name__ == '__main__':
    main()
