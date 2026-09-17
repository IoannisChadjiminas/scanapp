from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from app.config import Settings
from app.recognition.captures import save_scan_capture


def test_review_api_lists_cases_and_images(tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.review import router

    settings = Settings(data_dir=tmp_path, store_captures=True, review_token="secret")
    image = Image.new("RGB", (48, 64), color=(10, 20, 30))
    save_scan_capture(
        settings=settings,
        scan_id="scan-api",
        session_id="session-api",
        created_at="2026-09-17T16:00:00Z",
        status="uncertain",
        message="Choose the print.",
        input_image=image,
        query_image=image,
        request={},
        image_stats={"detected": False},
        ocr={"name_text": "Pikachu", "collector_text": "25", "failed": False},
        predicted=[
            {
                "card_id": "pika",
                "name": "Pikachu",
                "set_name": "Base",
                "collector_number": "25",
                "language": "en",
                "visual_score": 0.9,
            }
        ],
        visual=[],
        timings={},
        versions={},
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.settings = settings
    app.state.dbs = SimpleNamespace(catalog=None)
    client = TestClient(app)

    denied = client.get("/api/v1/review")
    assert denied.status_code == 401

    headers = {"Authorization": "Bearer secret"}
    listing = client.get("/api/v1/review", headers=headers, params={"needs_attention": True})
    assert listing.status_code == 200
    body = listing.json()
    assert body["n"] == 1
    assert body["items"][0]["scan_id"] == "scan-api"
    assert body["items"][0]["images"]["query"].endswith("scan-api.query.jpg")

    case = client.get("/api/v1/review/cases/scan-api", headers=headers)
    assert case.status_code == 200
    assert case.json()["ocr"]["collector_text"] == "25"

    image_resp = client.get("/api/v1/review/images/scan-api.query.jpg", headers=headers)
    assert image_resp.status_code == 200
    assert image_resp.headers["content-type"].startswith("image/jpeg")

    traversal = client.get("/api/v1/review/images/../catalog.sqlite", headers=headers)
    assert traversal.status_code == 404

    summary = client.get("/api/v1/review/summary", headers=headers)
    assert summary.status_code == 200
    assert "scan-api" in summary.text
