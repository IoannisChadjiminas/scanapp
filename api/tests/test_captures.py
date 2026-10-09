from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.recognition.captures import apply_feedback, save_scan_capture


def test_save_and_label_capture(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, store_captures=True)
    image = Image.new("RGB", (80, 120), color=(20, 80, 180))
    record = save_scan_capture(
        settings=settings,
        scan_id="scan-1",
        session_id="session-a",
        created_at="2026-09-17T12:00:00Z",
        status="uncertain",
        message="Choose the print.",
        input_image=image,
        query_image=image,
        request={"language": "auto", "skip_detect": True},
        image_stats={"detected": False, "too_blurry": False, "too_small": False},
        ocr={"name_text": "Pikachu", "collector_text": "008/034", "failed": False},
        predicted=[
            {
                "card_id": "clc",
                "name": "Pikachu",
                "set_name": "Classic",
                "collector_number": "008/034",
                "language": "en",
                "visual_score": 0.91,
                "combined_score": 0.91,
            }
        ],
        visual=[],
        timings={"total_ms": 12.3},
        versions={"ranking": "rank-v3"},
    )
    assert record is not None
    root = tmp_path / "review"
    assert (root / "images" / "scan-1.query.jpg").is_file()
    assert (root / "images" / "scan-1.input.jpg").is_file()
    summary = (root / "SUMMARY.md").read_text()
    assert "needs attention: 1" in summary
    assert "scan-1" in summary
    labels = (root / "labels.jsonl").read_text().strip()
    assert labels == ""

    updated = apply_feedback(
        settings,
        "scan-1",
        action="confirm",
        confirmed_card_id="clc",
        rejected=False,
    )
    assert updated is not None
    assert updated["review"]["needs_attention"] is False
    label = json.loads((root / "labels.jsonl").read_text().splitlines()[0])
    assert label["card_id"] == "clc"
    assert label["file"] == "scan-1.query.jpg"
    assert label["group"] == "session-a"


def test_reject_becomes_unknown_label(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, store_captures=True)
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    save_scan_capture(
        settings=settings,
        scan_id="scan-2",
        session_id="session-b",
        created_at="2026-09-17T12:01:00Z",
        status="matched",
        message=None,
        input_image=image,
        query_image=image,
        request={},
        image_stats={},
        ocr={},
        predicted=[{"card_id": "wrong", "name": "Raichu", "collector_number": "26", "visual_score": 0.9}],
        visual=[],
        timings={},
        versions={},
    )
    apply_feedback(
        settings,
        "scan-2",
        action="reject",
        confirmed_card_id=None,
        rejected=True,
    )
    label = json.loads((tmp_path / "review" / "labels.jsonl").read_text().splitlines()[0])
    assert label["unknown"] is True
    case = json.loads((tmp_path / "review" / "cases" / "scan-2.json").read_text())
    assert case["review"]["reason"] == "rejected"


def test_store_captures_can_be_disabled(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, store_captures=False)
    image = Image.new("RGB", (32, 48), color=(1, 2, 3))
    assert (
        save_scan_capture(
            settings=settings,
            scan_id="scan-off",
            session_id="s",
            created_at="2026-09-17T12:02:00Z",
            status="matched",
            message=None,
            input_image=image,
            query_image=image,
            request={},
            image_stats={},
            ocr={},
            predicted=[],
            visual=[],
            timings={},
            versions={},
        )
        is None
    )
    assert not (tmp_path / "review").exists()


def _save(settings, scan_id: str, **extra):
    image = Image.new("RGB", (32, 48), color=(9, 9, 9))
    return save_scan_capture(
        settings=settings, scan_id=scan_id, session_id="s", created_at="2026-10-09T10:00:00Z",
        status="uncertain", message=None, input_image=image, query_image=image, request={},
        image_stats={}, ocr={}, predicted=[], visual=[], timings={}, versions={}, **extra)


def test_a_scan_does_not_reread_every_stored_case(tmp_path: Path, monkeypatch) -> None:
    from app.recognition import captures
    settings = Settings(data_dir=tmp_path, store_captures=True)
    _save(settings, "old-1")
    monkeypatch.setattr(captures, "INDEX_REFRESH_DELAY_S", 3600.0)
    reads = []
    real = captures.load_cases
    monkeypatch.setattr(captures, "load_cases", lambda root: reads.append(root) or real(root))
    record = _save(settings, "new-1", rebuild_index=False)
    assert record is not None and reads == []
    assert (tmp_path / "review" / "cases" / "new-1.json").is_file()
    root = tmp_path / "review"
    assert "new-1" not in (root / "review.jsonl").read_text()
    # The review routes rebuild on demand, once.
    assert captures.refresh_index_if_stale(root) is True
    assert "new-1" in (root / "review.jsonl").read_text()
    assert captures.refresh_index_if_stale(root) is False
    for timer in list(captures._index_timers.values()):
        timer.cancel()
    captures._index_timers.clear()


def test_scheduled_rebuild_runs_once_for_many_scans(tmp_path: Path, monkeypatch) -> None:
    import time
    from app.recognition import captures
    settings = Settings(data_dir=tmp_path, store_captures=True)
    builds = []
    real = captures.refresh_index
    monkeypatch.setattr(captures, "refresh_index", lambda root: builds.append(root) or real(root))
    monkeypatch.setattr(captures, "INDEX_REFRESH_DELAY_S", 0.05)
    for i in range(5):
        _save(settings, f"burst-{i}", rebuild_index=False)
    time.sleep(0.4)
    assert len(builds) == 1
    assert "burst-4" in (tmp_path / "review" / "review.jsonl").read_text()


def test_review_routes_rebuild_a_stale_index(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes.review import router
    from app.recognition import captures
    settings = Settings(data_dir=tmp_path, store_captures=True, review_token="tok")
    _save(settings, "late-1", rebuild_index=False)
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    body = TestClient(app).get("/review/summary", headers={"X-Review-Token": "tok"}).text
    assert "late-1" in body and "scans: 1" in body
    for timer in list(captures._index_timers.values()):
        timer.cancel()
    captures._index_timers.clear()
