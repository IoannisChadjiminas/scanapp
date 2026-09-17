from __future__ import annotations

import argparse

from app.cardmarket_queue import issue_helper_credential, revoke_helper_credential
from app.config import get_settings
from app.db import connect, init_catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision or revoke the Scanapp Cardmarket helper credential."
    )
    parser.add_argument("--revoke", metavar="HELPER_ID", help="Revoke an existing helper credential")
    parser.add_argument("--helper-id", help="Reuse a helper id when rotating a token")
    args = parser.parse_args()
    settings = get_settings()
    conn = connect(settings.catalog_sqlite)
    init_catalog(conn)
    if args.revoke:
        revoke_helper_credential(conn, args.revoke)
        print(f"revoked helper_id={args.revoke}")
        return
    helper_id, token = issue_helper_credential(conn, args.helper_id)
    print(f"helper_id={helper_id}")
    print(f"token={token}")
    print("Enter the token once in the Scanapp Cardmarket helper popup. It will not be shown again.")


if __name__ == "__main__":
    main()
