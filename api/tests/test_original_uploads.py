"""STORE_ORIGINAL_UPLOADS: the exact upload bytes are kept only when STORE_CAPTURES is on too."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.recognition.captures import image_file, save_scan_capture


def _jpeg_upload() -> bytes:
    # A deliberately non-re-encodable payload: the bytes must come back unchanged.
    frame = Image.new("RGB", (1363, 1904), color=(30, 90, 160))
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _png_upload() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 90), color=(200, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def _save(settings: Settings, scan_id: str, upload_bytes: bytes | None) -> dict | None:
    image = Image.new("RGB", (80, 120), color=(20, 80, 180))
    return save_scan_capture(
        settings=settings,
        scan_id=scan_id,
        session_id="session-a",
        created_at="2026-10-27T12:00:00Z",
        status="uncertain",
        message=None,
        input_image=image,
        query_image=image,
        request={"language": "auto", "skip_detect": False},
        image_stats={"detected": True, "too_blurry": False, "too_small": False},
        ocr={"name_text": "Pikachu", "collector_text": "008/034", "failed": False},
        predicted=[],
        visual=[],
        timings={"total_ms": 12.3},
        versions={"ranking": "rank-v3"},
        rebuild_index=False,
        upload_bytes=upload_bytes,
    )


def _scan_files(root: Path, scan_id: str) -> set[str]:
    return {path.name for path in (root / "images").glob(f"{scan_id}.*")}


def test_off_off_writes_nothing_and_adds_no_record_field(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=False,
                        store_original_uploads=False)
    assert _save(settings, "scan-off", _jpeg_upload()) is None
    assert not (tmp_path / "review").exists()


def test_on_off_keeps_the_review_copies_exactly_as_before(tmp_path: Path) -> None:
    upload = _jpeg_upload()
    with_upload = tmp_path / "with-upload"
    without_upload = tmp_path / "without-upload"
    settings_a = Settings(_env_file=None, data_dir=with_upload, store_captures=True,
                          store_original_uploads=False)
    settings_b = Settings(_env_file=None, data_dir=without_upload, store_captures=True,
                          store_original_uploads=False)
    record_a = _save(settings_a, "scan-1", upload)
    record_b = _save(settings_b, "scan-1", None)
    assert record_a is not None and record_b is not None
    assert "original_upload" not in record_a
    assert record_a == record_b
    assert _scan_files(with_upload / "review", "scan-1") == {"scan-1.input.jpg", "scan-1.query.jpg"}
    stored = (with_upload / "review" / "cases" / "scan-1.json").read_text()
    assert "original_upload" not in stored
    assert "original" not in stored


def test_on_on_stores_the_exact_upload_bytes_next_to_the_copies(tmp_path: Path) -> None:
    upload = _jpeg_upload()
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=True,
                        store_original_uploads=True)
    record = _save(settings, "scan-2", upload)
    assert record is not None
    root = tmp_path / "review"
    original = root / "images" / "scan-2.original.jpg"
    assert original.read_bytes() == upload
    assert record["original_upload"] == {
        "file": "images/scan-2.original.jpg",
        "bytes": len(upload),
        "sha256": hashlib.sha256(upload).hexdigest(),
    }
    assert _scan_files(root, "scan-2") == {
        "scan-2.input.jpg", "scan-2.query.jpg", "scan-2.original.jpg"}
    saved = json.loads((root / "cases" / "scan-2.json").read_text())
    assert saved["original_upload"] == record["original_upload"]


def test_png_upload_keeps_its_own_extension(tmp_path: Path) -> None:
    upload = _png_upload()
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=True,
                        store_original_uploads=True)
    record = _save(settings, "scan-png", upload)
    assert record is not None
    assert record["original_upload"]["file"] == "images/scan-png.original.png"
    assert (tmp_path / "review" / "images" / "scan-png.original.png").read_bytes() == upload


def test_on_off_capture_off_flag_on_writes_no_original(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=False,
                        store_original_uploads=True)
    assert _save(settings, "scan-nocap", _jpeg_upload()) is None
    assert not (tmp_path / "review").exists()


def test_no_upload_bytes_means_no_original_and_no_field(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=True,
                        store_original_uploads=True)
    record = _save(settings, "scan-none", None)
    assert record is not None
    assert "original_upload" not in record
    assert _scan_files(tmp_path / "review", "scan-none") == {
        "scan-none.input.jpg", "scan-none.query.jpg"}


def test_original_is_covered_by_the_same_scan_prefix_as_the_captures(tmp_path: Path) -> None:
    """Retention and deletion work per scan: one `<scan_id>.*` sweep removes every photo of it."""
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=True,
                        store_original_uploads=True)
    _save(settings, "scan-keep", _jpeg_upload())
    _save(settings, "scan-other", _jpeg_upload())
    root = tmp_path / "review"
    assert image_file(root, "scan-keep.original.jpg") is not None
    for path in (root / "images").glob("scan-keep.*"):
        path.unlink()
    assert _scan_files(root, "scan-keep") == set()
    assert _scan_files(root, "scan-other") == {
        "scan-other.input.jpg", "scan-other.query.jpg", "scan-other.original.jpg"}


def test_deleting_the_review_folder_removes_the_original_too(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=True,
                        store_original_uploads=True)
    _save(settings, "scan-del", _jpeg_upload())
    assert (tmp_path / "review" / "images" / "scan-del.original.jpg").is_file()
    shutil.rmtree(tmp_path / "review")
    assert not (tmp_path / "review").exists()
