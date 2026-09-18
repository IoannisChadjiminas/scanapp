from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.cardmarket import apply_cardmarket_links
from app.db import connect, init_catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Write stored Cardmarket product URLs onto local catalogue cards. "
            "Does not open Cardmarket. Use after a helper set-page import or Save URL."
        )
    )
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    conn = connect(data_dir / "catalog.sqlite")
    init_catalog(conn)
    stats = apply_cardmarket_links(conn, data_dir)
    conn.close()
    print(
        f"cardmarket maps {stats['helper_maps']}, "
        f"expansion linked {stats['expansion_linked']}, "
        f"unmatched {stats['expansion_unmatched']}"
    )


if __name__ == "__main__":
    main()
