"""Move catalogue-completion cases one state forward from the case manifest.

    python -m bootstrap.complete --run 20261004-01 --step all

``all`` imports evidence, checks new images, writes the unexecuted batch-sample
plan, and prints readiness counts. It does not build features or write to PlanetScale.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bootstrap.manifest import (
    checkpoint,
    connect,
    counts,
    import_readiness,
    run_checks,
    write_sample_plan,
)


def repo_root() -> Path:
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / "catalogue" / "bootstrap" / "complete.py").exists():
            return candidate
    return here


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="20261004-01")
    parser.add_argument(
        "--step",
        choices=("import", "checks", "sample", "dry-run", "all"),
        default="dry-run",
    )
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expect", help="unique,passes,hash_checked,release_ready")
    args = parser.parse_args()
    root = repo_root()
    run_dir = root / "data" / "catalogue-completion" / args.run
    manifest_path = args.manifest or (run_dir / "cases.sqlite")
    readiness = args.readiness or (
        run_dir
        / "english-batch-readiness-20261011"
        / "consolidated-readiness-v3.json"
    )
    conn = connect(manifest_path)
    if args.step in {"import", "dry-run", "all"}:
        document = json.loads(readiness.read_text())
        import_readiness(conn, document)
        checkpoint(conn, "import", counts(conn))
        conn.commit()
    if args.step in {"checks", "all"}:
        run_checks(conn)
        checkpoint(conn, "checks", counts(conn))
        conn.commit()
    if args.step in {"sample", "all"}:
        write_sample_plan(conn, run_dir / "sample-plan.json")
    payload = counts(conn)
    checkpoint(conn, args.step, payload)
    conn.commit()
    manifest_path.with_name("cases-checkpoint.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(payload, sort_keys=True))
    if args.expect:
        unique, passes, hashed, ready = (int(part) for part in args.expect.split(","))
        actual = (
            payload["unique_cases"],
            payload["conditional_passes"],
            payload["hash_checked"],
            payload["release_ready"],
        )
        if actual != (unique, passes, hashed, ready):
            raise SystemExit(f"readiness counts {actual} != {(unique, passes, hashed, ready)}")


if __name__ == "__main__":
    main()
