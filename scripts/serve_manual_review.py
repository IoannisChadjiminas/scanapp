"""Serve the matching-audit review and store pair comments.

The page posts choices to /manual/pair-comments.json. Only that file is writable.
"""

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "exports" / "matching-audit"
COMMENTS = ROOT / "manual" / "pair-comments.json"
CHOICES = {"", "1", "2", "original"}


class ReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/manual/pair-comments.json":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            self.send_error(400, "Unexpected comment payload")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except (UnicodeError, json.JSONDecodeError):
            self.send_error(400, "Comments must be JSON")
            return
        if not isinstance(payload, dict) or len(payload) > 200:
            self.send_error(400, "Unexpected comment payload")
            return
        clean = {}
        for card_id, note in payload.items():
            if not isinstance(card_id, str) or not isinstance(note, dict):
                self.send_error(400, "Unexpected comment payload")
                return
            choice = note.get("choice") or ""
            comment = note.get("comment") or ""
            if choice not in CHOICES or not isinstance(comment, str) or len(comment) > 4000:
                self.send_error(400, "Unexpected comment payload")
                return
            if not choice and not comment.strip():
                continue
            clean[card_id] = {
                "card_id": card_id,
                "name": str(note.get("name") or "")[:200],
                "set_name": str(note.get("set_name") or "")[:200],
                "choice": choice,
                "comment": comment,
                "scan_url": str(note.get("scan_url") or "")[:300],
                "also_url": str(note.get("also_url") or "")[:300],
                "updated_at": str(note.get("updated_at") or "")[:40],
            }
        COMMENTS.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n")
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.split("?", 1)[0].endswith("pair-comments.json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    COMMENTS.parent.mkdir(parents=True, exist_ok=True)
    if not COMMENTS.exists():
        COMMENTS.write_text("{}\n")
    server = ThreadingHTTPServer(("127.0.0.1", 8767), ReviewHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
