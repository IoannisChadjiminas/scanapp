"""Replay a frozen photo panel with N scans in flight, and compare recognition responses.

Replay (one JSON line per scan, the full response included):
  python scripts/lane_replay.py replay --panel cases.json --root PANEL_DIR --out run.jsonl \
      --concurrency 2 [--rounds 2] [--server-pid PID] [--settle] [--hint]

Compare two replays (byte-identical after dropping the scan id and *_ms timing values):
  python scripts/lane_replay.py compare base.jsonl other.jsonl

--server-pid samples the server's resident memory while the replay runs. --settle waits until
the server is idle before each scan (sequential runs only), so late label reads finish first.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time

import httpx


def recognition(body):
    """The response without values that differ on every run: the scan id and timings."""
    body = dict(body)
    body.pop('id', None)
    timings = body.pop('timings_ms', None) or {}
    body['timings'] = {k: v for k, v in timings.items() if not k.endswith('_ms')}
    return body


def digest(body):
    return hashlib.sha256(json.dumps(recognition(body), sort_keys=True).encode()).hexdigest()


class RssSampler(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True)
        import psutil
        self.process = psutil.Process(pid)
        self.peak = self.start_rss = self.process.memory_info().rss
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(.1):
            try:
                self.peak = max(self.peak, self.process.memory_info().rss)
            except Exception:  # noqa: BLE001 - the server may exit first
                return


def settle(pid, idle=1.2, limit=30):
    import psutil
    process = psutil.Process(pid)
    last, quiet, end = sum(process.cpu_times()[:2]), time.time(), time.time() + limit
    while time.time() < end:
        time.sleep(.25)
        now = sum(process.cpu_times()[:2])
        if now - last > .02:
            last, quiet = now, time.time()
        elif time.time() - quiet >= idle:
            return


def replay(a):
    cases = json.loads(a.panel.read_text())[:a.limit]
    jobs = [(round_, case) for round_ in range(a.rounds) for case in cases]
    sampler = RssSampler(a.server_pid) if a.server_pid else None
    if sampler:
        sampler.start()
    lock = threading.Lock()
    client = httpx.Client(timeout=300)

    def scan(job):
        round_, case = job
        if a.settle and a.server_pid:
            settle(a.server_pid)
        path = a.root / case['photo_file']
        started = time.perf_counter()
        form = {'language': 'auto'}
        if a.hint:
            form['graded'] = 'true' if case['kind'] == 'slab' else 'false'
        reply = client.post(a.url, data=form,
                            files={'image': (path.name, path.read_bytes(), 'image/jpeg')})
        http_ms = (time.perf_counter() - started) * 1000
        body = reply.json() if reply.status_code == 200 else {}
        row = dict(id=case['id'], round=round_, http=reply.status_code, http_ms=round(http_ms, 1),
                   status=body.get('status'), digest=digest(body) if body else None,
                   total_ms=(body.get('timings_ms') or {}).get('total_ms'), response=body)
        with lock:
            handle.write(json.dumps(row) + '\n')
            handle.flush()
        print(case['id'], reply.status_code, round(http_ms), row['status'], flush=True)
        return row

    started = time.perf_counter()
    with a.out.open('w') as handle, ThreadPoolExecutor(a.concurrency) as pool:
        rows = list(pool.map(scan, jobs))
    wall = time.perf_counter() - started
    client.close()
    walls = sorted(r['http_ms'] for r in rows)
    summary = dict(scans=len(rows), concurrency=a.concurrency, wall_s=round(wall, 1),
                   scans_per_min=round(len(rows) / wall * 60, 2),
                   http_ms_p50=walls[len(walls) // 2], http_ms_p90=walls[min(len(walls) - 1, int(len(walls) * .9))],
                   errors=sum(r['http'] != 200 for r in rows))
    if sampler:
        sampler.stop.set()
        summary.update(rss_start_mb=round(sampler.start_rss / 2**20), rss_peak_mb=round(sampler.peak / 2**20))
    print(json.dumps(summary))
    a.out.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2) + '\n')


def compare(a):
    def load(path):
        rows = {}
        for row in map(json.loads, Path(path).read_text().splitlines()):
            rows.setdefault(row['id'], []).append(row)
        return rows

    base, other = load(a.base), load(a.other)
    same, changed = 0, []
    for case_id, reference in base.items():
        expected = reference[0]['digest']
        for row in other.get(case_id, []):
            if row['digest'] == expected and expected is not None:
                same += 1
                continue
            left, right = recognition(reference[0]['response']), recognition(row['response'])
            changed.append(dict(id=case_id, round=row['round'],
                                fields=sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))))
    unstable = [i for i, rows in base.items() if len({r['digest'] for r in rows}) > 1]
    print(json.dumps(dict(compared=same + len(changed), identical=same, changed=changed,
                          base_unstable=unstable), indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('replay')
    r.add_argument('--panel', type=Path, required=True)
    r.add_argument('--root', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--url', default='http://127.0.0.1:8000/api/v1/scans')
    r.add_argument('--concurrency', type=int, default=1)
    r.add_argument('--rounds', type=int, default=1)
    r.add_argument('--limit', type=int, default=10**9)
    r.add_argument('--server-pid', type=int)
    r.add_argument('--settle', action='store_true')
    r.add_argument('--hint', action='store_true', help="send the phone's slab hint: graded=true for slabs only")
    c = sub.add_parser('compare')
    c.add_argument('base')
    c.add_argument('other')
    a = p.parse_args()
    replay(a) if a.command == 'replay' else compare(a)


if __name__ == '__main__':
    main()
