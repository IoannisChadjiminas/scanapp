#!/usr/bin/env python3
"""Initialize and report the resumable Japanese set recovery acquisition ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "data/catalogue-gaps/ja-set-audit-20261028/comparison.json"
RUN = ROOT / "data/catalogue-gaps/ja-set-recovery-20261029-v3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scope_from_audit(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [g for g in groups if g.get("coverage") in {"absent", "partial_by_count"}]
    if len(selected) != 336:
        raise ValueError(f"Expected 336 audited groups; found {len(selected)}")
    def queue_rank(group: dict[str, Any]) -> tuple[int, int, int]:
        code = group.get("code")
        if code == "MBG":
            rank = 0
            pilot = 0
        elif code == "MBD":
            rank = 0
            pilot = 1
        elif group.get("coverage") == "absent" and group.get("era") == "Mega Evolution Era":
            rank = 1
            pilot = 0
        elif group.get("coverage") == "absent" and group.get("era") == "Scarlet & Violet Era":
            rank = 2
            pilot = 0
        elif group.get("coverage") == "partial_by_count":
            rank = 3
            pilot = 0
        else:
            rank = 4
            pilot = 0
        return rank, pilot, int(group.get("line", 0))

    result = []
    for index, group in enumerate(sorted(selected, key=queue_rank), 1):
        result.append({
            "group_id": f"ja-ref-{group['source_link_id']}",
            "priority": index,
            "name": group["name"],
            "code": group["code"],
            "era": group["era"],
            "listed_cards": group.get("listed_cards"),
            "source_link_id": group["source_link_id"],
            "line": group.get("line"),
            "coverage": group["coverage"],
            "catalogue_codes": group.get("catalogue_codes", []),
            "catalogue_rows": group.get("catalogue_rows", 0),
            "reference_status": "pending",
            "checklist_source": "tcgcollector-20261028",
            "cardmarket_status": "pending",
            "cardmarket_expansion_id": None,
        })
    return result


def initialize(run_dir: Path, audit: Path) -> None:
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    groups = json.loads(audit.read_text())
    registry = scope_from_audit(groups)
    run_dir.mkdir(parents=True)
    for name in ("source-pages", "images", "review"):
        (run_dir / name).mkdir()
    for name in (
        "printing-inventory.jsonl", "existing-matches.jsonl",
        "new-or-incomplete-printings.jsonl", "image-manifest.jsonl",
        "cardmarket-products.jsonl", "verified-mappings.jsonl", "held-mappings.jsonl",
    ):
        (run_dir / name).touch()
    (run_dir / "set-registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    (run_dir / "run.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope_groups": len(registry),
        "scope_rule": "coverage absent or partial_by_count from frozen 2026-10-28 audit",
        "execution_environment": "native Apple Silicon macOS",
        "staging_used_for_collection": False,
        "audit_path": str(audit),
        "audit_sha256": sha256(audit),
        "acquisition_complete": False,
        "vectors_started": False,
        "publication_state": "not_started",
    }, indent=2) + "\n")
    with sqlite3.connect(run_dir / "jobs.sqlite") as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE jobs (
              job_id TEXT PRIMARY KEY, group_id TEXT NOT NULL, priority INTEGER NOT NULL, kind TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
              lease_owner TEXT, lease_until TEXT, retry_after TEXT, source_key TEXT,
              result_path TEXT, last_error_code TEXT, updated_at TEXT NOT NULL,
              UNIQUE(group_id, kind)
            );
            CREATE INDEX jobs_state_kind ON jobs(state, kind);
            CREATE TABLE events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
              event TEXT NOT NULL, occurred_at TEXT NOT NULL, detail_json TEXT NOT NULL
            );
        """)
        now = datetime.now(timezone.utc).isoformat()
        for group in registry:
            gid = group["group_id"]
            for kind in ("checklist", "cardmarket_listing", "image_reconcile"):
                db.execute("INSERT INTO jobs(job_id,group_id,priority,kind,updated_at) VALUES(?,?,?,?,?)",
                           (f"{gid}:{kind}", gid, group["priority"], kind, now))
        db.commit()
    report(run_dir)


def report(run_dir: Path) -> None:
    registry = json.loads((run_dir / "set-registry.json").read_text())
    with sqlite3.connect(run_dir / "jobs.sqlite") as db:
        jobs = db.execute("SELECT kind,state,count(*) FROM jobs GROUP BY kind,state ORDER BY kind,state").fetchall()
    counts = {f"{kind}_{state}": count for kind, state, count in jobs}
    listing_path = run_dir / "listing-report.json"
    listing = json.loads(listing_path.read_text()) if listing_path.exists() else {}
    seeds_path = run_dir / "listing-seeds.json"
    seeded = len(json.loads(seeds_path.read_text())) if seeds_path.exists() else 0
    routing_path = run_dir / "seed-discovery-review.json"
    routing = json.loads(routing_path.read_text()).get("states", {}) if routing_path.exists() else {}
    summary = {
        "groups_enumerated": len(registry),
        "cardmarket_collection_routes": seeded,
        "cardmarket_groups_needing_route_review": len(registry) - seeded,
        "cardmarket_route_review_states": routing,
        "cardmarket_listing_groups": listing.get("groups_listed", 0),
        "cardmarket_listing_products": listing.get("products", 0),
        "groups_completed": sum(g.get("reference_status") == "complete" for g in registry),
        "groups_blocked": sum(g.get("reference_status") == "blocked" for g in registry),
        "distinct_new_printings": 0,
        "valid_images": 0,
        "verified_links": 0,
        "mapping_exceptions": 0,
        "eligible_vectors": 0,
        "reference_only_vectors": 0,
        "jobs": counts,
        "publication_state": "not_started",
    }
    (run_dir / "acquisition-report.json").write_text(json.dumps(summary, indent=2) + "\n")
    run_meta = json.loads((run_dir / "run.json").read_text())
    (run_dir / "STATUS.md").write_text(
        "# Japanese set recovery status\n\n"
        f"Initialized `{run_dir.name}` from audit SHA-256 `{run_meta['audit_sha256']}`.\n\n"
        f"- Groups enumerated/completed/blocked: {summary['groups_enumerated']}/0/0\n"
        "- Distinct new printings / valid images / verified links: 0 / 0 / 0\n"
        "- Mapping exceptions: 0; vectors started: no\n"
        "- Publication: not started\n\n"
        "- Collector: native Mac mode, localhost-only, dedicated visible Chrome profile.\n"
        f"- Observed collection routes: {seeded}; groups requiring route/card-level review: {len(registry) - seeded}. Unmapped does not mean unfindable.\n"
        "- Current plan: `docs/experiments/japanese-set-routing-update-20261029.md`.\n"
        "- Local regression command and latest live validation: see `api/scripts/ja_set_recovery/README.md`.\n"
        f"- Cardmarket listing traversal: {listing.get('groups_listed', 0)} groups, {listing.get('products', 0)} unique group/product records. Discovery and traversal are separate milestones.\n"
        "- Listing traversal is separate from checklist reconciliation, image acquisition and verified catalogue mappings.\n"
        "- Staging collection/deployment: not used. Production: untouched.\n\n"
        "Start: `.venv-scraper/bin/python api/scripts/ja_set_recovery/local_scraper.py`\n"
        "Report: `.venv-scraper/bin/python api/scripts/ja_set_recovery/recovery.py report`\n"
    )
    print(json.dumps(summary, indent=2))


def claim_job(run_dir: Path, kind: str, owner: str, lease_seconds: int) -> None:
    now = datetime.now(timezone.utc)
    until = now.timestamp() + lease_seconds
    lease_until = datetime.fromtimestamp(until, timezone.utc).isoformat()
    with sqlite3.connect(run_dir / "jobs.sqlite", timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT job_id,group_id,kind,attempts FROM jobs WHERE kind=? "
            "AND (state='pending' OR (state='running' AND lease_until<?)) "
            "AND (retry_after IS NULL OR retry_after<=?) ORDER BY priority LIMIT 1",
            (kind, now.isoformat(), now.isoformat()),
        ).fetchone()
        if row is None:
            db.rollback()
            print(json.dumps({"claimed": False, "kind": kind}))
            return
        db.execute(
            "UPDATE jobs SET state='running',attempts=attempts+1,lease_owner=?,lease_until=?,updated_at=? WHERE job_id=?",
            (owner, lease_until, now.isoformat(), row["job_id"]),
        )
        db.execute("INSERT INTO events(job_id,event,occurred_at,detail_json) VALUES(?,?,?,?)",
                   (row["job_id"], "claimed", now.isoformat(), json.dumps({"owner": owner})))
        db.commit()
        print(json.dumps({"claimed": True, "job_id": row["job_id"], "group_id": row["group_id"],
                          "kind": kind, "attempt": row["attempts"] + 1, "lease_until": lease_until}))


def finish_job(run_dir: Path, job_id: str, state: str, detail: str, *, quiet: bool = False) -> None:
    if state not in {"complete", "blocked", "waiting_for_owner", "pending"}:
        raise ValueError("state must be complete, blocked, waiting_for_owner, or pending")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(run_dir / "jobs.sqlite", timeout=30) as db:
        cursor = db.execute(
            "UPDATE jobs SET state=?,lease_owner=NULL,lease_until=NULL,last_error_code=?,updated_at=? WHERE job_id=?",
            (state, detail[:120] if state in {"blocked", "waiting_for_owner"} else None, now, job_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Unknown job id: {job_id}")
        db.execute("INSERT INTO events(job_id,event,occurred_at,detail_json) VALUES(?,?,?,?)",
                   (job_id, state, now, json.dumps({"detail": detail[:500]})))
        db.commit()
    if not quiet:
        print(json.dumps({"job_id": job_id, "state": state, "updated_at": now}))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--run-dir", type=Path, default=RUN)
    init.add_argument("--audit", type=Path, default=AUDIT)
    sub.add_parser("report")
    claim = sub.add_parser("claim")
    claim.add_argument("kind", choices=("checklist", "cardmarket_listing", "image_reconcile"))
    claim.add_argument("--owner", required=True)
    claim.add_argument("--lease-seconds", type=int, default=900)
    finish = sub.add_parser("finish")
    finish.add_argument("job_id")
    finish.add_argument("state", choices=("complete", "blocked", "waiting_for_owner", "pending"))
    finish.add_argument("--detail", default="")
    args = parser.parse_args()
    if args.command == "init":
        initialize(args.run_dir, args.audit)
    elif args.command == "report":
        report(RUN)
    elif args.command == "claim":
        claim_job(RUN, args.kind, args.owner, max(30, args.lease_seconds))
    else:
        finish_job(RUN, args.job_id, args.state, args.detail)


if __name__ == "__main__":
    main()
