#!/usr/bin/env python3
"""Call the localhost-only scraper without exposing its local bearer key."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "data/catalogue-gaps/ja-set-recovery-20261029-v3"
KEY_FILE = RUN / "scraper-local.key"
BASE_URL = "http://127.0.0.1:8000"


def request(method: str, path: str, payload: dict | None = None) -> dict:
    key = KEY_FILE.read_text().strip()
    body = json.dumps(payload).encode() if payload is not None else None
    while True:
        req = urllib.request.Request(
            BASE_URL + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=130) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace")
            try:
                rate_limited = exc.code == 503 and json.loads(detail).get("detail") == "Rate limited"
            except (json.JSONDecodeError, AttributeError):
                rate_limited = False
            if rate_limited:
                try:
                    retry_after = max(1, int(exc.headers.get("Retry-After", "5")))
                except (TypeError, ValueError):
                    retry_after = 5
                print(f"Cardmarket rate limit active; resuming in {retry_after}s.",
                      file=sys.stderr, flush=True)
                time.sleep(retry_after)
                continue
            raise SystemExit(f"Scraper returned HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, FileNotFoundError) as exc:
            raise SystemExit(f"Local scraper is unavailable or its private key is missing: {type(exc).__name__}") from None


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    listing = commands.add_parser("listing")
    listing.add_argument("group_id")
    listing.add_argument("url")
    listing.add_argument("--session-id", required=True)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("url")
    confirm.add_argument("--session-id", required=True)
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(request("GET", "/status"), indent=2))
    elif args.command == "confirm":
        print(json.dumps(request("POST", "/catalogue-listing/confirm", {
            "session_id": args.session_id, "url": args.url,
        }), indent=2))
    else:
        allowed = {row["group_id"] for row in json.loads((RUN / "set-registry.json").read_text())}
        if not re.fullmatch(r"ja-ref-\d+", args.group_id) or args.group_id not in allowed:
            raise SystemExit("group_id must name one of the 336 groups in the recovery registry")
        result = request("POST", "/catalogue-listing", {
            "session_id": args.session_id, "url": args.url,
        })
        payload = {
            "group_id": args.group_id,
            "requested_url": args.url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        digest = hashlib.sha256(encoded).hexdigest()
        folder = RUN / "source-pages" / args.group_id
        folder.mkdir(parents=True, exist_ok=True)
        page = folder / f"{digest[:20]}.json"
        if not page.exists():
            page.write_bytes(encoded)
        if result.get("owner_verification_required") is True:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from recovery import finish_job
            finish_job(RUN, f"{args.group_id}:cardmarket_listing", "waiting_for_owner",
                       "Waiting for manual verification in the same local Chrome session")
        print(json.dumps({"outcome": result.get("outcome"), "products": len(result.get("products", [])),
                          "pagination_urls": result.get("pagination_urls", []),
                          "owner_verification_required": result.get("owner_verification_required", False),
                          "evidence_file": str(page), "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
