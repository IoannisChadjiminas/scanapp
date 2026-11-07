#!/usr/bin/env python3
"""Run the authenticated, visible Cardmarket collector on the owner's Mac."""
from __future__ import annotations

import os
import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "data/catalogue-gaps/ja-set-recovery-20261029-v3"
KEY_FILE = RUN / "scraper-local.key"
PROFILE = Path.home() / "Library/Application Support/PokeSingle/CardmarketScraperProfile"


def private_key() -> str:
    RUN.mkdir(parents=True, exist_ok=True)
    try:
        return KEY_FILE.read_text().strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(32)
        descriptor = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(key + "\n")
        return key


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("This launcher is for the owner's macOS machine.")
    if not (Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file()):
        raise SystemExit("Install Google Chrome at /Applications/Google Chrome.app first.")
    PROFILE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PROFILE.chmod(0o700)
    os.environ.update({
        "SCRAPER_API_KEY": private_key(),
        "SCRAPER_IN_PROCESS": "1",
        "SCRAPER_MAC_MODE": "1",
        "SCRAPER_CHROME_PROFILE": str(PROFILE),
        "PROXY_ENABLED": "false",
        "MAX_BROWSERS": "1",
        "SCRAPER_RATE_LIMIT_S": os.environ.get("SCRAPER_RATE_LIMIT_S", "900"),
        "SCRAPER_LISTING_PAGE_GAP_S": os.environ.get("SCRAPER_LISTING_PAGE_GAP_S", "1"),
    })
    for name in ("PROXY_HOST", "PROXY_USER", "PROXY_PASS", "PROXY_COUNTRY", "PROXY_USER_TEMPLATE"):
        os.environ.pop(name, None)
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-browser", action="store_true",
                        help="launch the dedicated visible Chrome profile on about:blank, then exit")
    args = parser.parse_args()
    scraper = ROOT / "scraper"
    api = ROOT / "api"
    sys.path[:0] = [str(scraper), str(api)]
    if args.check_browser:
        from browser import ChromeSession
        session = ChromeSession(None, net_log=False)
        try:
            session.open("about:blank")
            if not session.current_url().startswith("about:blank"):
                raise SystemExit("Chrome did not reach about:blank")
        finally:
            session.quit()
        print("Local Chrome profile opened and closed successfully on about:blank.")
        return
    import uvicorn
    import main as scraper_app

    print("Local scraper listening on http://127.0.0.1:8000")
    print(f"Dedicated Chrome profile: {PROFILE}")
    print(f"Local auth key stored mode 0600 at: {KEY_FILE}")
    print("No staging URL, proxy, or credentials are configured.")
    uvicorn.run(scraper_app.app, host="127.0.0.1", port=8000, workers=1, log_level="info")


if __name__ == "__main__":
    main()
