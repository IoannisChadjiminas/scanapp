"""Mirror TCGdex card art into the public R2 bucket the API hands out as image_url.

Run inside the API container, where the catalogue and the data volume are:

    python scripts/mirror_card_images.py --limit 200      # first, check the CDN URLs
    python scripts/mirror_card_images.py                  # then everything, resumable

Needs CARD_IMAGE_R2_ACCOUNT_ID, CARD_IMAGE_R2_ACCESS_KEY_ID,
CARD_IMAGE_R2_SECRET_ACCESS_KEY and CARD_IMAGE_R2_BUCKET. The running API
starts returning mirrored URLs within a minute once CARD_IMAGE_CDN_BASE_URL is
set. Prints counts only, never credentials. See docs/card-image-cdn.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, "/app")
from app.card_image_mirror import DryRunStore, http_fetcher, mirror_card_images, r2_client  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Databases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="cards to upload this run")
    parser.add_argument("--language", default=None, help="only this catalogue language, e.g. en")
    parser.add_argument("--gap", type=float, default=0.1, help="seconds between cards (TCGdex courtesy)")
    parser.add_argument("--dry-run", action="store_true", help="download nothing, upload nothing, count only")
    args = parser.parse_args()

    settings = Settings()
    if args.dry_run:
        store = DryRunStore()
        bucket = "dry-run"
    else:
        if settings.card_image_r2() is None:
            print("CARD_IMAGE_R2_ACCOUNT_ID, _ACCESS_KEY_ID, _SECRET_ACCESS_KEY and _BUCKET must all be set", file=sys.stderr)
            return 2
        store = r2_client(settings)
        bucket = settings.card_image_r2_bucket

    dbs = Databases(settings)
    try:
        with httpx.Client(headers={"User-Agent": "pokesingle-card-image-mirror"}) as http:
            fetch = (lambda url: b"RIFF\0\0\0\0WEBPdry") if args.dry_run else http_fetcher(http)
            report = mirror_card_images(
                dbs.catalog,
                settings,
                store=store,
                bucket=bucket,
                fetch=fetch,
                limit=args.limit,
                language=args.language,
                gap_s=0.0 if args.dry_run else args.gap,
                log=print,
            )
    finally:
        dbs.close()
    for key, value in report.as_dict().items():
        print(f"{key}: {value}")
    if args.dry_run:
        print("dry run: nothing was stored or recorded")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
