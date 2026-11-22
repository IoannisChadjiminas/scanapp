"""Fills TCGplayer's price history from TCGCSV's daily archives.

TCGCSV keeps one archive a day since 8 February 2024. This reads one every
[--step] days, oldest first, and keeps each Pokémon price where it moved,
exactly as the daily import does (TcgplayerPrices.record_day). Run it once
against the server's tcgplayer.sqlite; days already past are safe to repeat.

    pip install py7zr
    python scripts/backfill_tcgplayer_history.py /data/tcgplayer.sqlite --step 7
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tcgplayer import CATEGORIES, SOURCE, USER_AGENT, TcgplayerPrices  # noqa: E402

FIRST_DAY = date(2024, 2, 8)


def day_rows(archive: Path, work: Path):
    import py7zr

    with py7zr.SevenZipFile(archive) as packed:
        wanted = [
            name for name in packed.getnames()
            if name.endswith("/prices") and name.split("/")[1] in {str(c) for c in CATEGORIES}
        ]
        packed.extract(path=work, targets=wanted)
    for name in wanted:
        try:
            results = json.loads((work / name).read_text()).get("results") or []
        except (ValueError, OSError):
            continue
        for item in results:
            yield (
                int(item["productId"]),
                str(item.get("subTypeName") or "Normal"),
                item.get("marketPrice"),
                item.get("lowPrice"),
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--since", type=date.fromisoformat, default=FIRST_DAY)
    parser.add_argument("--until", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--step", type=int, default=7)
    parser.add_argument("--pause", type=float, default=5.0)
    args = parser.parse_args()
    store = TcgplayerPrices(args.store)
    client = httpx.Client(base_url=SOURCE, timeout=120, headers={"User-Agent": USER_AGENT})
    day = max(args.since, FIRST_DAY)
    while day <= args.until:
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            reply = client.get(f"/archive/tcgplayer/prices-{day.isoformat()}.ppmd.7z")
            # Asked to slow down: wait as long as it says, then ask again.
            for _ in range(6):
                if reply.status_code != 429:
                    break
                wait = reply.headers.get("retry-after", "")
                time.sleep(min(900, int(wait)) if wait.isdigit() else 120)
                reply = client.get(f"/archive/tcgplayer/prices-{day.isoformat()}.ppmd.7z")
            if reply.status_code == 429:
                # Still refused: stop here, to be run again from this day.
                print(day.isoformat(), "limited; resume with --since", day.isoformat(), flush=True)
                break
            if reply.status_code == 200:
                (work / "day.7z").write_bytes(reply.content)
                kept = store.record_day(day.isoformat(), day_rows(work / "day.7z", work / "out"))
                print(day.isoformat(), "kept", kept, flush=True)
            else:
                print(day.isoformat(), "no archive", reply.status_code, flush=True)
        day += timedelta(days=args.step)
        time.sleep(args.pause)
    store.close()


if __name__ == "__main__":
    main()
