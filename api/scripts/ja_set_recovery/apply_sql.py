"""Apply candidate.sql from prepare_sql.py in one transaction. Never prints the URL.

    python3 apply_sql.py SQL_FILE ROLE_JSON

ROLE_JSON is a short-lived admin role (`--inherited-roles postgres --ttl 1h`, needed for
CREATE SCHEMA). The file's own BEGIN/COMMIT are replaced by one psycopg transaction; any
error (including the final guard) rolls everything back, leaving no schema behind.
"""
import json
import sys
import time
from pathlib import Path

import certifi
import psycopg


def statements(text):
    current = []
    for line in text.splitlines():
        if current and (line[:1].isspace() or line.startswith("END $acl$")):
            current.append(line)
            continue
        if current:
            yield "\n".join(current)
        current = [line]
    if current:
        yield "\n".join(current)


def main(sql_file, role_file):
    role = json.loads(Path(role_file).read_text())
    parts = [s for s in statements(Path(sql_file).read_text()) if s.strip() not in ("BEGIN;", "COMMIT;", "")]
    started = time.time()
    try:
        with psycopg.connect(role["database_url"], port=6432, sslmode="verify-full", sslrootcert=certifi.where(),
                             prepare_threshold=None, autocommit=False) as conn:
            for number, statement in enumerate(parts, 1):
                conn.execute(statement)
                if number % 25 == 0 or number == len(parts):
                    print(json.dumps({"statement": number, "of": len(parts), "seconds": round(time.time() - started)}), flush=True)
            conn.commit()
    except psycopg.Error as exc:
        print(json.dumps({"rolled_back": True, "error": type(exc).__name__,
                          "message": (exc.diag.message_primary or "")[:300] if exc.diag else ""}), flush=True)
        raise SystemExit(1) from None
    print(json.dumps({"committed": True, "statements": len(parts), "seconds": round(time.time() - started)}), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
