"""Serve the matching-audit review and store pair comments.

The page posts choices to /manual/pair-comments.json. Only that file is writable.

With --manifest, serve the catalogue-completion review queue instead. Accept and
reject write straight to that SQLite manifest. Images are read from the stored
file path for the requested card only.
"""

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Catalogue-completion cases.sqlite")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.manifest:
        _serve_manifest(args.manifest, args.port or 8768)
        return
    COMMENTS.parent.mkdir(parents=True, exist_ok=True)
    if not COMMENTS.exists():
        COMMENTS.write_text("{}\n")
    server = ThreadingHTTPServer(("127.0.0.1", args.port or 8767), ReviewHandler)
    server.serve_forever()


def _serve_manifest(path: Path, port: int) -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "catalogue"))
    from bootstrap.manifest import apply_decision, connect, review_rows

    class ManifestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlparse(self.path)
            if route.path == "/":
                body = _review_page(review_rows(connect(path))).encode()
                self._send(200, "text/html; charset=utf-8", body)
                return
            if route.path == "/cases.json":
                body = json.dumps(review_rows(connect(path))).encode()
                self._send(200, "application/json", body)
                return
            if route.path == "/image":
                card_id = parse_qs(route.query).get("card_id", [""])[0]
                self._send_image(card_id)
                return
            self.send_error(404)

        def do_POST(self):
            if urlparse(self.path).path != "/decisions":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 100_000:
                self.send_error(400, "Unexpected decision payload")
                return
            try:
                payload = json.loads(self.rfile.read(length).decode())
                saved = apply_decision(
                    connect(path),
                    str(payload.get("card_id") or ""),
                    str(payload.get("decision") or ""),
                    str(payload.get("reason") or ""),
                )
            except (UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
                self.send_error(400, str(exc))
                return
            body = json.dumps(
                {"ok": True, "card_id": saved["card_id"], "state": saved["state"]}
            ).encode()
            self._send(200, "application/json", body)

        def _send_image(self, card_id: str) -> None:
            row = connect(path).execute(
                "SELECT file_path FROM cases WHERE card_id = ?", (card_id,)
            ).fetchone()
            if row is None or not row["file_path"]:
                self.send_error(404)
                return
            file = Path(row["file_path"])
            if not file.is_file():
                self.send_error(404)
                return
            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._send(200, mime, file.read_bytes())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    ThreadingHTTPServer(("127.0.0.1", port), ManifestHandler).serve_forever()


def _review_page(rows: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["set_id"], []).append(row)
    parts = []
    for set_id, items in groups.items():
        cards = []
        for row in items:
            reason = row.get("check_reason") or row.get("hold_reason") or ""
            accept = ""
            if row["state"] != "held":
                accept = "<button type=\"button\" data-decision=\"accept\">Accept</button>"
            cards.append(
                "<article>"
                f"<h3>{_esc(row['name'])} <small>{_esc(row['card_id'])}</small></h3>"
                f"<p>{_esc(row['state'])} · {_esc(row.get('check_result') or '')} · {_esc(reason)}</p>"
                f"<img alt='' src=\"/image?card_id={_esc(row['card_id'])}\">"
                "<form method=\"post\" action=\"/decisions\">"
                f"<input type=\"hidden\" name=\"card_id\" value=\"{_esc(row['card_id'])}\">"
                f"{accept}"
                "<input name=\"reason\" placeholder=\"Reject reason\">"
                "<button type=\"button\" data-decision=\"reject\">Reject</button>"
                "</form></article>"
            )
        parts.append(f"<section><h2>{_esc(set_id)}</h2>{''.join(cards)}</section>")
    return (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<title>Catalogue completion review</title>"
        "<style>body{font:16px system-ui;margin:24px}article{border-bottom:1px solid #ccc;padding:12px}"
        "img{width:180px;height:250px;object-fit:contain;background:#f4f4f4}</style>"
        f"<h1>Review queue</h1><p>{len(rows)} items, grouped by set.</p>"
        f"{''.join(parts)}"
        "<script>document.body.addEventListener('click',async e=>{const b=e.target.closest('button');"
        "if(!b)return;const f=b.closest('form');const body={card_id:f.card_id.value,decision:b.dataset.decision,"
        "reason:f.reason.value};const r=await fetch('/decisions',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify(body)});if(r.ok)f.closest('article').remove();else alert(await r.text())})</script>"
    )


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    main()
