"""Browser process. The supervisor is its parent and kills the whole process group on a deadline."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(API))


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _stage(name: str) -> None:
    sys.stderr.write(json.dumps({"stage": name}) + "\n")
    sys.stderr.flush()


def main() -> None:
    from browser import acquire_browser, run_attempt
    from proxy import proxy_server

    from app.cardmarket_html import parse_cardmarket_html

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except ValueError:
            _emit({"outcome": "error", "error": "bad-command"})
            continue
        op = str(command.get("op") or "")
        if op == "ready":
            _emit({"ok": True})
            continue
        if op == "quit":
            _emit({"ok": True})
            return
        session_id = str(command.get("session_id") or "")
        try:
            _stage("browser_start")
            session = acquire_browser(proxy_server(session_id) if session_id else None)
            if op == "warm":
                _emit({"ok": True, "reused": bool(session.reused), "stage": session.stage})
                continue
            if op != "scrape":
                _emit({"outcome": "error", "error": "unknown-op"})
                continue
            _stage("navigation")
            result = run_attempt(
                session, str(command.get("url") or ""), parse_html=parse_cardmarket_html
            )
            result["reused"] = bool(getattr(session, "reused", False))
            result["cleared"] = bool(getattr(session, "cleared", False))
            result["stage"] = str(getattr(session, "stage", "") or "")
            result["net_summary"] = getattr(session, "net_summary", None)
            _emit(result)
        except Exception as exc:
            frames = traceback.extract_tb(exc.__traceback__)[-8:]
            _emit(
                {
                    "outcome": "error",
                    "error": type(exc).__name__,
                    "stage": "worker",
                    "frames": " > ".join(
                        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames
                    ),
                }
            )


if __name__ == "__main__":
    main()
