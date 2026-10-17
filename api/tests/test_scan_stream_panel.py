"""The review panel can target a local API and resume after an interrupted run."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'run_scan_stream_panel.py'


class Scans(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        Scans.calls.append(self.path)
        body = json.dumps({'type': 'final', 'result': {'status': 'matched', 'best_match': {'card_id': 'sv1-1'}}})
        payload = (body + '\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def panel(tmp_path, ids):
    cases = []
    for ident in ids:
        photo = tmp_path / f'{ident}.jpg'
        photo.write_bytes(ident.encode())
        cases.append(dict(id=ident, photo_file=photo.name, sha256=hashlib.sha256(ident.encode()).hexdigest(),
                          expected_card_ids=['en:sv1-1']))
    path = tmp_path / 'panel.json'
    path.write_text(json.dumps(cases))
    return path


def run(tmp_path, server, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), '--panel', str(tmp_path / 'panel.json'),
                           '--photos-root', str(tmp_path), '--output', str(tmp_path / 'out.jsonl'),
                           '--base-url', f'http://127.0.0.1:{server.server_port}', '--pause', '0', *extra],
                          capture_output=True, text=True, check=True)


def test_resume_scans_only_unfinished_cases(tmp_path):
    panel(tmp_path, ['a', 'b', 'c'])
    server = ThreadingHTTPServer(('127.0.0.1', 0), Scans)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        done = {'case': {'id': 'a'}, 'response': {}, 'events': [], 'first_provisional_ms': None, 'http_ms': 5.0}
        # One finished case and a line cut off by the earlier crash.
        (tmp_path / 'out.jsonl').write_text(json.dumps(done) + '\n{"case": {"id": "b"')
        Scans.calls.clear()
        run(tmp_path, server, '--resume')
        assert Scans.calls == ['/api/v1/scans', '/api/v1/scans']
        rows = [json.loads(line) for line in (tmp_path / 'out.jsonl').read_text().splitlines()]
        assert [r['case']['id'] for r in rows] == ['a', 'b', 'c']
        summary = json.loads((tmp_path / 'out.summary.json').read_text())
        assert summary['scans'] == 3
    finally:
        server.shutdown()
