from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.cardmarket import PROMO_SLUG_CODES, apply_cardmarket_links
from app.db import connect, init_catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Write stored Cardmarket product URLs onto local catalogue cards. "
            "Unique SKU → attach URL. Two or more listings for the same "
            "expansion+code+number → leave unassigned for the scan picker. "
            "Does not open Cardmarket."
        )
    )
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument(
        "--promo",
        action="store_true",
        help=(
            "Only hyphenated promo SKUs: "
            + ", ".join(PROMO_SLUG_CODES)
        ),
    )
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated SKU codes to link, e.g. S-P,SWSH,MEW",
    )
    args = parser.parse_args()
    codes: set[str] | None = None
    extra = {item.strip().upper() for item in args.codes.split(",") if item.strip()}
    if args.promo and extra:
        codes = {code.upper() for code in PROMO_SLUG_CODES} | extra
    elif args.promo:
        codes = {code.upper() for code in PROMO_SLUG_CODES}
    elif extra:
        codes = extra
    data_dir = Path(args.data_dir)
    conn = connect(data_dir / "catalog.sqlite")
    init_catalog(conn)
    stats = apply_cardmarket_links(conn, data_dir, codes=codes)
    conn.close()
    print(
        f"cardmarket maps {stats['helper_maps']}, "
        f"considered {stats['considered']}, "
        f"expansion linked {stats['expansion_linked']}, "
        f"unmatched {stats['expansion_unmatched']}, "
        f"variant-sku skipped {stats['skipped_variants']}, "
        f"ambiguous cleared {stats['ambiguous_cleared']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
