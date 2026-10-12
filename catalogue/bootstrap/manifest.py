"""One SQLite row per catalogue-completion case."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bootstrap.checks import ImageFacts, hamming, judge, load_facts

STATES = (
    "needs_source",
    "source_ok",
    "features_built",
    "sample_passed",
    "in_release",
    "released",
    "held",
)
FORWARD = {
    "needs_source": 0,
    "source_ok": 1,
    "features_built": 2,
    "sample_passed": 3,
    "in_release": 4,
    "released": 5,
}

COHORT_CAUSE = {
    "hs-trainer-query": "trainer_kit_reprint",
    "dp-sm-exact-print-query": "trainer_kit_reprint",
    "my-first-battle-confusers": "my_first_battle_family_confuser",
    "mcd2015-quality": "mcdonalds_2015_photo_quality",
    "individual-source-scope-query": "individual_or_scope",
    "url-scope-version-hold": "url_or_scope",
}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cases (
          card_id TEXT PRIMARY KEY,
          language TEXT NOT NULL,
          set_id TEXT NOT NULL,
          collector_number TEXT,
          name TEXT NOT NULL,
          cohort TEXT,
          gap_type TEXT NOT NULL,
          root_cause TEXT NOT NULL,
          state TEXT NOT NULL,
          hold_reason TEXT,
          source_url TEXT,
          source_page TEXT,
          file_path TEXT,
          file_sha256 TEXT,
          primary_url TEXT,
          release_readiness TEXT,
          release_ready INTEGER NOT NULL DEFAULT 0,
          conditional_pass INTEGER NOT NULL DEFAULT 0,
          identity_approved INTEGER NOT NULL DEFAULT 0,
          pilot_status TEXT,
          pilot_json TEXT,
          evidence_json TEXT NOT NULL,
          check_result TEXT,
          check_reason TEXT,
          release_id TEXT,
          human_decision TEXT,
          imported_state TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
          path TEXT PRIMARY KEY,
          card_id TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          hash_ok INTEGER NOT NULL,
          role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts (
          card_id TEXT NOT NULL,
          step TEXT NOT NULL,
          input_sha TEXT NOT NULL,
          outcome TEXT NOT NULL,
          detail TEXT,
          at TEXT NOT NULL,
          PRIMARY KEY (card_id, step, input_sha)
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at TEXT NOT NULL,
          step TEXT NOT NULL,
          counts_json TEXT NOT NULL
        );
        """
    )
    return conn


def import_readiness(conn: sqlite3.Connection, document: dict, now: str | None = None) -> dict:
    """Load readiness evidence. Human decisions and later states are kept."""
    now = now or _now()
    url_ids = {row["id"] for row in document.get("url_rows_detail") or []}
    passed = set(document.get("conditional_pass_ids") or [])
    conn.execute("DELETE FROM files")
    for row in document["rows"]:
        _upsert_case(conn, row, url_ids, passed, now)
        _import_files(conn, row)
        _import_failed_attempts(conn, row, now)
    conn.commit()
    return counts(conn)


def run_checks(conn: sqlite3.Connection, now: str | None = None) -> int:
    """Check primary files whose bytes have not already been judged."""
    now = now or _now()
    rows = conn.execute(
        "SELECT * FROM cases WHERE file_path IS NOT NULL AND file_sha256 IS NOT NULL"
    ).fetchall()
    hashes: dict[str, int] = {}
    facts_by_id: dict[str, ImageFacts] = {}
    for row in rows:
        prior = conn.execute(
            """
            SELECT outcome FROM attempts
            WHERE card_id = ? AND step = 'checks' AND input_sha = ?
            """,
            (row["card_id"], row["file_sha256"]),
        ).fetchone()
        if prior:
            continue
        path = Path(row["file_path"])
        if not path.is_file() or _sha256(path) != row["file_sha256"]:
            _store_check(conn, row, "fail", "hash_mismatch", now)
            continue
        facts = load_facts(path, path.name)
        facts_by_id[row["card_id"]] = facts
        if facts.dhash is not None:
            hashes[row["card_id"]] = facts.dhash
    checked = 0
    for row in rows:
        facts = facts_by_id.get(row["card_id"])
        if facts is None:
            continue
        duplicate = _duplicate_of(row["card_id"], facts.dhash, hashes)
        evidence = json.loads(row["evidence_json"])
        source = evidence.get("new_native_source") or {}
        result, reason = judge(
            facts,
            language=row["language"],
            name=row["name"],
            collector=row["collector_number"],
            observed_name=source.get("name") if source.get("identity_approved") else None,
            observed_collector=source.get("visible_collector"),
            lines=_lines(evidence),
            duplicate_of=duplicate,
        )
        _store_check(conn, row, result, reason, now)
        checked += 1
    _advance_passed_sources(conn, now)
    conn.commit()
    return checked


def write_sample_plan(conn: sqlite3.Connection, path: Path, now: str | None = None) -> dict:
    """List features_built cases. This does not run inference or change state."""
    now = now or _now()
    ids = [
        row["card_id"]
        for row in conn.execute(
            "SELECT card_id FROM cases WHERE state = 'features_built' ORDER BY card_id"
        )
    ]
    plan = {
        "at": now,
        "executed": False,
        "card_ids": ids,
        "case_count": len(ids),
        "reason": (
            "Batch sample execution is release E1. "
            "The plan lists features_built cases and does not start inference."
        ),
        "runner": "pinned offline builder and native query pilot",
    }
    path.write_text(json.dumps(plan, indent=2) + "\n")
    checkpoint(conn, "sample", counts(conn), now)
    conn.commit()
    return plan


def apply_decision(
    conn: sqlite3.Connection,
    card_id: str,
    decision: str,
    reason: str = "",
    now: str | None = None,
) -> dict:
    now = now or _now()
    row = conn.execute("SELECT * FROM cases WHERE card_id = ?", (card_id,)).fetchone()
    if row is None:
        raise KeyError(card_id)
    if decision not in {"accept", "reject"}:
        raise ValueError("decision must be accept or reject")
    if row["state"] in {"in_release", "released"}:
        raise ValueError("released cases are not in the review queue")
    if decision == "reject" and not reason.strip():
        raise ValueError("reject requires a reason")
    if decision == "accept":
        if row["state"] == "held":
            raise ValueError("held cases stay held until new evidence changes the input")
        state = "source_ok" if row["state"] == "needs_source" and row["file_sha256"] else row["state"]
        conn.execute(
            """
            UPDATE cases
            SET state = ?, check_result = 'pass', check_reason = 'manual_accept',
                human_decision = 'accept', updated_at = ?
            WHERE card_id = ?
            """,
            (state, now, card_id),
        )
    else:
        conn.execute(
            """
            UPDATE cases
            SET state = 'held', hold_reason = ?, check_result = 'fail',
                check_reason = ?, human_decision = 'reject', updated_at = ?
            WHERE card_id = ?
            """,
            (reason.strip(), reason.strip(), now, card_id),
        )
    conn.commit()
    saved = conn.execute("SELECT * FROM cases WHERE card_id = ?", (card_id,)).fetchone()
    return dict(saved)


def review_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM cases
        WHERE check_result = 'review'
           OR (check_result = 'fail' AND state != 'held')
        ORDER BY set_id, card_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def counts(conn: sqlite3.Connection) -> dict:
    unique = conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
    passes = conn.execute(
        "SELECT COUNT(*) AS n FROM cases WHERE conditional_pass = 1"
    ).fetchone()["n"]
    ready = conn.execute(
        "SELECT COUNT(*) AS n FROM cases WHERE release_ready = 1"
    ).fetchone()["n"]
    hashed = conn.execute(
        "SELECT COUNT(*) AS n FROM files WHERE hash_ok = 1"
    ).fetchone()["n"]
    cohorts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT cohort, COUNT(*) AS n FROM cases GROUP BY cohort"
    ):
        cohorts[row["cohort"]] = row["n"]
    states: dict[str, int] = {}
    for row in conn.execute("SELECT state, COUNT(*) AS n FROM cases GROUP BY state"):
        states[row["state"]] = row["n"]
    return {
        "unique_cases": unique,
        "conditional_passes": passes,
        "hash_checked": hashed,
        "release_ready": ready,
        "cohort_counts": cohorts,
        "states": states,
    }


def checkpoint(conn: sqlite3.Connection, step: str, payload: dict, now: str | None = None) -> None:
    conn.execute(
        "INSERT INTO checkpoints (at, step, counts_json) VALUES (?, ?, ?)",
        (now or _now(), step, json.dumps(payload)),
    )


def _upsert_case(
    conn: sqlite3.Connection,
    row: dict,
    url_ids: set[str],
    passed: set[str],
    now: str,
) -> None:
    language, set_id, number = _split_id(row["id"])
    source = row.get("new_native_source") or {}
    if source.get("set_id"):
        set_id = source["set_id"]
    if source.get("collector_number"):
        number = source["collector_number"]
    holds = list(row.get("recorded_holds") or [])
    image_gap = "image_and_reference_completion_pending" in holds or row["id"] not in url_ids
    if row["id"] in url_ids and image_gap:
        gap = "both"
    elif row["id"] in url_ids:
        gap = "url"
    else:
        gap = "image"
    state, hold = _derive_state(row)
    if state == "held" and not hold:
        raise ValueError(f"{row['id']} is held without a reason")
    gate = row.get("new_query_gate") or {}
    existing = conn.execute(
        "SELECT * FROM cases WHERE card_id = ?", (row["id"],)
    ).fetchone()
    keep_progress = existing is not None and (
        existing["human_decision"]
        or existing["state"] != existing["imported_state"]
    )
    saved_state = existing["state"] if keep_progress else state
    saved_hold = existing["hold_reason"] if keep_progress else hold
    if saved_state == "held" and not saved_hold:
        raise ValueError(f"{row['id']} is held without a reason")
    fields = {
        "card_id": row["id"],
        "language": language,
        "set_id": set_id,
        "collector_number": number,
        "name": row.get("name") or "",
        "cohort": row.get("cohort"),
        "gap_type": gap,
        "root_cause": _root_cause(row, holds),
        "state": saved_state,
        "hold_reason": saved_hold,
        "source_url": source.get("image_url"),
        "source_page": source.get("source_page"),
        "file_path": source.get("source_file"),
        "file_sha256": source.get("sha256"),
        "primary_url": row.get("primary_url"),
        "release_readiness": row.get("release_readiness"),
        "release_ready": 1 if row.get("release_ready") else 0,
        "conditional_pass": 1 if row["id"] in passed else 0,
        "identity_approved": 1 if source.get("identity_approved") else 0,
        "pilot_status": gate.get("status"),
        "pilot_json": json.dumps(gate) if gate else None,
        "evidence_json": json.dumps(row),
        "imported_state": state,
        "updated_at": now,
    }
    if existing is None:
        fields["check_result"] = None
        fields["check_reason"] = None
        fields["release_id"] = None
        fields["human_decision"] = None
        columns = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO cases ({columns}) VALUES ({marks})",
            tuple(fields.values()),
        )
        return
    assignments = ", ".join(f"{key} = ?" for key in fields if key != "card_id")
    conn.execute(
        f"UPDATE cases SET {assignments} WHERE card_id = ?",
        tuple(value for key, value in fields.items() if key != "card_id") + (row["id"],),
    )


def _import_files(conn: sqlite3.Connection, row: dict) -> None:
    sources = [row.get("new_native_source") or {}] + list(row.get("additional_native_leads") or [])
    for source in sources:
        path = source.get("source_file") or source.get("path")
        expected = source.get("sha256")
        if not path or not expected:
            continue
        file = Path(path)
        actual = _sha256(file) if file.is_file() else ""
        role = source.get("status") or source.get("source_kind") or "source"
        conn.execute(
            """
            INSERT INTO files (path, card_id, sha256, hash_ok, role)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              card_id = excluded.card_id,
              sha256 = excluded.sha256,
              hash_ok = excluded.hash_ok,
              role = excluded.role
            """,
            (path, row["id"], expected, int(actual == expected), role),
        )


def _import_failed_attempts(conn: sqlite3.Connection, row: dict, now: str) -> None:
    for gate in row.get("query_gate_history") or []:
        if gate.get("correct_identity_and_existing_url") and gate.get(
            "physical_independence_verified"
        ):
            continue
        sha = gate.get("query_sha256")
        if not sha:
            continue
        conn.execute(
            """
            INSERT INTO attempts (card_id, step, input_sha, outcome, detail, at)
            VALUES (?, 'query', ?, 'failed', ?, ?)
            ON CONFLICT(card_id, step, input_sha) DO NOTHING
            """,
            (row["id"], sha, gate.get("status"), now),
        )


def _store_check(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    result: str,
    reason: str,
    now: str,
) -> None:
    if row["human_decision"]:
        return
    conn.execute(
        """
        UPDATE cases SET check_result = ?, check_reason = ?, updated_at = ?
        WHERE card_id = ?
        """,
        (result, reason, now, row["card_id"]),
    )
    conn.execute(
        """
        INSERT INTO attempts (card_id, step, input_sha, outcome, detail, at)
        VALUES (?, 'checks', ?, ?, ?, ?)
        ON CONFLICT(card_id, step, input_sha) DO UPDATE SET
          outcome = excluded.outcome, detail = excluded.detail, at = excluded.at
        """,
        (row["card_id"], row["file_sha256"], result, reason, now),
    )


def _advance_passed_sources(conn: sqlite3.Connection, now: str) -> None:
    rows = conn.execute(
        """
        SELECT card_id, file_sha256 FROM cases
        WHERE state = 'needs_source' AND check_result = 'pass'
          AND identity_approved = 1 AND file_sha256 IS NOT NULL
          AND human_decision IS NULL
        """
    ).fetchall()
    for row in rows:
        failed = conn.execute(
            """
            SELECT 1 FROM attempts
            WHERE card_id = ? AND step = 'query' AND input_sha = ? AND outcome = 'failed'
            """,
            (row["card_id"], row["file_sha256"]),
        ).fetchone()
        if failed:
            continue
        conn.execute(
            """
            UPDATE cases SET state = 'source_ok', updated_at = ? WHERE card_id = ?
            """,
            (now, row["card_id"]),
        )


def _duplicate_of(card_id: str, digest: int | None, hashes: dict[str, int]) -> str | None:
    if digest is None:
        return None
    for other, value in hashes.items():
        if other != card_id and hamming(digest, value) == 0:
            return other
    return None


def _lines(evidence: dict) -> list[str]:
    source = evidence.get("new_native_source") or {}
    lines = []
    for key in ("visible_collector", "visible_copyright", "visible_illustrator"):
        if source.get(key):
            lines.append(str(source[key]))
    return lines


def _derive_state(row: dict) -> tuple[str, str | None]:
    readiness = row.get("release_readiness")
    if readiness == "independent_query_passed_final_combined_regression_pending":
        return "features_built", None
    if readiness == "held_pending_source_quality_and_independent_exact_identity_evidence":
        return "needs_source", None
    if readiness == "identity_and_url_correct_physical_independence_unproven":
        return "held", "physical_independence_unproven"
    if readiness == "query_failed_new_evidence_needed":
        return "held", "query_failed_new_evidence_needed"
    if readiness == "existing_originals_exist_family_confuser_gate_failed_or_unresolved":
        return "held", "my_first_battle_family_confuser_gate_unresolved"
    if readiness == "one_creased_native_front_only_second_gallery_contains_back_photos":
        return "held", "one_creased_native_front_only"
    if readiness is None:
        holds = [str(item) for item in row.get("recorded_holds") or [] if item]
        action = row.get("source_or_query_research_action")
        return "held", action or (holds[-1] if holds else "url_or_scope_unresolved")
    return "held", f"unmapped_readiness:{readiness}"


def _root_cause(row: dict, holds: list) -> str:
    for hold in holds:
        text = str(hold)
        if text not in {"image_and_reference_completion_pending", "kit_position_print_identity"}:
            return text
    return COHORT_CAUSE.get(row.get("cohort") or "", row.get("cohort") or "unclassified")


def _split_id(card_id: str) -> tuple[str, str, str]:
    language, rest = card_id.split(":", 1)
    if "-" not in rest:
        return language, rest, ""
    set_id, number = rest.rsplit("-", 1)
    return language, set_id, number


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
