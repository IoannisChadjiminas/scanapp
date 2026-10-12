import hashlib
import json
from pathlib import Path

import pytest

from bootstrap.checks import ImageFacts, judge
from bootstrap.complete import main
from bootstrap.manifest import (
    apply_decision,
    connect,
    counts,
    import_readiness,
    review_rows,
    run_checks,
)


def _row(card_id, readiness, **extra):
    row = {
        "id": card_id,
        "name": extra.pop("name", "Pikachu"),
        "cohort": extra.pop("cohort", "hs-trainer-query"),
        "recorded_holds": extra.pop("holds", ["image_and_reference_completion_pending"]),
        "release_readiness": readiness,
        "release_ready": False,
        "primary_url": extra.pop("primary_url", "https://www.cardmarket.com/en/Pokemon/example"),
        "primary_url_missing": False,
    }
    row.update(extra)
    return row


def _document(rows, passes):
    return {
        "rows": rows,
        "conditional_pass_ids": passes,
        "url_rows_detail": [],
        "cohort_counts": {},
    }


def test_judge_fails_small_back_and_wrong_script():
    facts = ImageFacts(100, 120, blur=80, dhash=1, back_only=True)
    result, reason = judge(
        facts,
        language="en",
        name="Pikachu",
        collector="2",
        observed_name="Pikachu",
        observed_collector="2/30",
        lines=["たね", "ピカチュウ"],
        duplicate_of=None,
    )
    assert result == "fail"
    assert "back_only" in reason
    assert "too_small" in reason
    assert "wrong_script:ja" in reason


def test_judge_reviews_when_identity_was_not_read():
    facts = ImageFacts(800, 1100, blur=80, dhash=1, back_only=False)
    result, reason = judge(
        facts,
        language="en",
        name="Pikachu",
        collector="2",
        observed_name=None,
        observed_collector=None,
        lines=[],
        duplicate_of=None,
    )
    assert result == "review"
    assert reason == "identity_not_read"


def test_import_reproduces_readiness_counts(tmp_path: Path):
    passed = _row(
        "en:tk-hs-r-2",
        "independent_query_passed_final_combined_regression_pending",
        new_native_source={"identity_approved": True, "sha256": "abc", "source_file": "/missing"},
    )
    waiting = _row(
        "en:tk-hs-r-3",
        "held_pending_source_quality_and_independent_exact_identity_evidence",
    )
    failed = _row(
        "en:tk-hs-r-12",
        "query_failed_new_evidence_needed",
        query_gate_history=[{"query_sha256": "deadbeef", "correct_identity_and_existing_url": False}],
    )
    conn = connect(tmp_path / "cases.sqlite")
    payload = import_readiness(conn, _document([passed, waiting, failed], ["en:tk-hs-r-2"]))
    assert payload["unique_cases"] == 3
    assert payload["conditional_passes"] == 1
    assert payload["release_ready"] == 0
    states = {row["card_id"]: row["state"] for row in conn.execute("SELECT card_id, state FROM cases")}
    assert states == {
        "en:tk-hs-r-2": "features_built",
        "en:tk-hs-r-3": "needs_source",
        "en:tk-hs-r-12": "held",
    }
    attempt = conn.execute(
        "SELECT outcome FROM attempts WHERE card_id = 'en:tk-hs-r-12' AND input_sha = 'deadbeef'"
    ).fetchone()
    assert attempt["outcome"] == "failed"
    again = import_readiness(conn, _document([passed, waiting, failed], ["en:tk-hs-r-2"]))
    assert again == payload
    assert conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 1


def test_reject_requires_a_reason_and_accept_does_not_release_a_hold(tmp_path: Path):
    image = tmp_path / "front.png"
    _write_sharp(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    source = {
        "identity_approved": True,
        "sha256": digest,
        "source_file": str(image),
        "name": "Pikachu",
        "visible_collector": "2/30",
        "visible_copyright": "2010 Pokemon",
    }
    ready = _row(
        "en:tk-hs-r-2",
        "held_pending_source_quality_and_independent_exact_identity_evidence",
        new_native_source=source,
    )
    held = _row("en:bwp-BW77", None, holds=["Cancelled physical promo"], primary_url=None)
    conn = connect(tmp_path / "cases.sqlite")
    import_readiness(conn, _document([ready, held], []))
    run_checks(conn)
    checked = conn.execute("SELECT state, check_result FROM cases WHERE card_id = 'en:tk-hs-r-2'").fetchone()
    assert checked["state"] == "source_ok"
    assert checked["check_result"] == "pass"
    with pytest.raises(ValueError, match="reason"):
        apply_decision(conn, "en:tk-hs-r-2", "reject")
    with pytest.raises(ValueError, match="held"):
        apply_decision(conn, "en:bwp-BW77", "accept")
    apply_decision(conn, "en:tk-hs-r-2", "reject", "soft footer")
    assert review_rows(conn) == []
    import_readiness(conn, _document([ready, held], []))
    kept = conn.execute("SELECT state, hold_reason FROM cases WHERE card_id = 'en:tk-hs-r-2'").fetchone()
    assert kept["state"] == "held"
    assert kept["hold_reason"] == "soft footer"


def test_dry_run_command_reproduces_a_fixture(tmp_path: Path, monkeypatch):
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            _document(
                [_row("en:tk-hs-r-1", "held_pending_source_quality_and_independent_exact_identity_evidence")],
                [],
            )
        )
    )
    manifest = tmp_path / "cases.sqlite"
    monkeypatch.setattr(
        "sys.argv",
        [
            "bootstrap.complete",
            "--step",
            "dry-run",
            "--readiness",
            str(readiness),
            "--manifest",
            str(manifest),
            "--expect",
            "1,0,0,0",
        ],
    )
    main()
    assert counts(connect(manifest))["unique_cases"] == 1


def _write_sharp(path: Path) -> None:
    from PIL import Image

    image = Image.new("RGB", (400, 560))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 13) % 255, (y * 7) % 255, (x + y) % 255)
    image.save(path)
