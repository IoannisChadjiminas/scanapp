from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

REVIEW_MAX_SIDE = 1600


def review_dir(settings: Any) -> Path:
    return Path(getattr(settings, "review_dir"))


def case_path(root: Path, scan_id: str) -> Path:
    return root / "cases" / f"{scan_id}.json"


def _jpeg(image: Image.Image, max_side: int = REVIEW_MAX_SIDE) -> bytes:
    frame = image.convert("RGB")
    if max(frame.size) > max_side:
        frame = frame.copy()
        frame.thumbnail((max_side, max_side), Image.Resampling.BICUBIC)
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def compact_rows(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        compact.append(
            {
                "card_id": row.get("card_id"),
                "name": row.get("name"),
                "set_name": row.get("set_name"),
                "collector_number": row.get("collector_number"),
                "language": row.get("language") or "",
                "visual_score": round(float(row.get("visual_score") or 0.0), 4),
                "combined_score": round(float(row.get("combined_score") or 0.0), 4),
                "ocr_consistent": row.get("ocr_consistent"),
                "collector_conflict": row.get("collector_conflict"),
            }
        )
    return compact


def review_flags(record: dict[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or "")
    confirmed = record.get("confirmed_card_id")
    rejected = bool(record.get("rejected"))
    predicted = (record.get("predicted") or [{}])[0]
    predicted_id = predicted.get("card_id")
    if rejected:
        return {"needs_attention": True, "reason": "rejected"}
    if confirmed and predicted_id and confirmed != predicted_id:
        return {"needs_attention": True, "reason": "corrected"}
    if confirmed:
        return {"needs_attention": False, "reason": "confirmed"}
    if status in {"uncertain", "no_match", "retake", "failed"}:
        return {"needs_attention": True, "reason": status}
    if status == "matched":
        return {"needs_attention": True, "reason": "unconfirmed"}
    return {"needs_attention": True, "reason": status or "unknown"}


def save_scan_capture(
    *,
    settings: Any,
    scan_id: str,
    session_id: str,
    created_at: str,
    status: str,
    message: str | None,
    input_image: Image.Image,
    query_image: Image.Image,
    request: dict[str, Any],
    image_stats: dict[str, Any],
    ocr: dict[str, Any],
    predicted: list[dict[str, Any]],
    visual: list[dict[str, Any]],
    timings: dict[str, Any],
    versions: dict[str, Any],
) -> dict[str, Any] | None:
    if not bool(getattr(settings, "store_captures", True)):
        return None
    root = review_dir(settings)
    images = root / "images"
    input_name = f"{scan_id}.input.jpg"
    query_name = f"{scan_id}.query.jpg"
    _write_bytes(images / input_name, _jpeg(input_image))
    _write_bytes(images / query_name, _jpeg(query_image))
    record = {
        "scan_id": scan_id,
        "created_at": created_at,
        "session_id": session_id,
        "status": status,
        "message": message,
        "images": {"input": f"images/{input_name}", "query": f"images/{query_name}"},
        "request": request,
        "image_stats": image_stats,
        "ocr": ocr,
        "predicted": compact_rows(predicted, 4),
        "visual_top20": compact_rows(visual, 20),
        "timings_ms": {key: round(float(value), 2) for key, value in timings.items()},
        "versions": versions,
        "confirmed_card_id": None,
        "rejected": False,
        "feedback_action": None,
    }
    record["review"] = review_flags(record)
    _write_json(case_path(root, scan_id), record)
    refresh_index(root)
    return record


def apply_feedback(
    settings: Any,
    scan_id: str,
    *,
    action: str,
    confirmed_card_id: str | None,
    rejected: bool,
) -> dict[str, Any] | None:
    if not bool(getattr(settings, "store_captures", True)):
        return None
    root = review_dir(settings)
    path = case_path(root, scan_id)
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    record["confirmed_card_id"] = confirmed_card_id
    record["rejected"] = bool(rejected)
    record["feedback_action"] = action
    record["review"] = review_flags(record)
    _write_json(path, record)
    refresh_index(root)
    return record


def _tags(record: dict[str, Any]) -> list[str]:
    tags = [str(record.get("status") or "unknown")]
    stats = record.get("image_stats") or {}
    if stats.get("detected") is False:
        tags.append("no_detect")
    if stats.get("too_blurry"):
        tags.append("blur")
    if stats.get("too_small"):
        tags.append("small")
    language = ""
    predicted = record.get("predicted") or []
    if predicted:
        language = str(predicted[0].get("language") or "")
    ocr = record.get("ocr") or {}
    language = language or str(ocr.get("detected_language") or "")
    if language:
        tags.append(language)
    return tags


def _label_row(record: dict[str, Any]) -> dict[str, Any] | None:
    query = (record.get("images") or {}).get("query") or ""
    file_name = Path(query).name
    if not file_name:
        return None
    predicted = record.get("predicted") or [{}]
    language = str((predicted[0] or {}).get("language") or "") or None
    group = str(record.get("session_id") or record.get("scan_id") or "")
    if record.get("confirmed_card_id"):
        return {
            "file": file_name,
            "card_id": record["confirmed_card_id"],
            "language": language,
            "unknown": False,
            "scan_id": record.get("scan_id"),
            "group": group,
            "tags": _tags(record),
        }
    if record.get("rejected"):
        return {
            "file": file_name,
            "card_id": "",
            "language": language,
            "unknown": True,
            "scan_id": record.get("scan_id"),
            "group": group,
            "tags": [*_tags(record), "rejected"],
        }
    return None


def load_cases(root: Path) -> list[dict[str, Any]]:
    folder = root / "cases"
    if not folder.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in folder.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("scan_id"):
            records.append(payload)
    records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return records


def _line(record: dict[str, Any]) -> str:
    predicted = record.get("predicted") or [{}]
    top = predicted[0] if predicted else {}
    name = top.get("name") or "—"
    number = top.get("collector_number") or ""
    language = top.get("language") or ""
    query = (record.get("images") or {}).get("query") or ""
    reason = (record.get("review") or {}).get("reason") or record.get("status")
    confirmed = record.get("confirmed_card_id") or ""
    extra = f" confirmed={confirmed}" if confirmed else ""
    return (
        f"- `{record.get('scan_id')}` {reason}: {name} #{number} {language}{extra}  \n"
        f"  query: `{query}`  input: `{(record.get('images') or {}).get('input')}`"
    )


def image_file(root: Path, filename: str) -> Path | None:
    name = Path(filename).name
    if name != filename or name.startswith("."):
        return None
    folder = (root / "images").resolve()
    path = (folder / name).resolve()
    if folder not in path.parents and path != folder:
        return None
    if not path.is_file():
        return None
    return path


def with_api_image_urls(record: dict[str, Any]) -> dict[str, Any]:
    scan_id = str(record.get("scan_id") or "")
    payload = dict(record)
    payload["images"] = {
        "input": f"/api/v1/review/images/{scan_id}.input.jpg",
        "query": f"/api/v1/review/images/{scan_id}.query.jpg",
    }
    return payload


def list_records(
    root: Path,
    *,
    needs_attention: bool | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    records = load_cases(root)
    counts: dict[str, int] = {}
    attention_n = 0
    for record in records:
        key = str(record.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
        flags = record.get("review") or review_flags(record)
        if flags.get("needs_attention"):
            attention_n += 1
    filtered = records
    if needs_attention is True:
        filtered = [
            record
            for record in filtered
            if (record.get("review") or review_flags(record)).get("needs_attention")
        ]
    elif needs_attention is False:
        filtered = [
            record
            for record in filtered
            if not (record.get("review") or review_flags(record)).get("needs_attention")
        ]
    if status:
        filtered = [record for record in filtered if record.get("status") == status]
    sliced = filtered[max(0, offset) : max(0, offset) + max(1, min(limit, 200))]
    return {
        "n": len(records),
        "matched_filter": len(filtered),
        "needs_attention": attention_n,
        "status_counts": counts,
        "items": [
            {
                "scan_id": item.get("scan_id"),
                "created_at": item.get("created_at"),
                "status": item.get("status"),
                "message": item.get("message"),
                "review": item.get("review") or review_flags(item),
                "confirmed_card_id": item.get("confirmed_card_id"),
                "rejected": bool(item.get("rejected")),
                "ocr": {
                    "name_text": (item.get("ocr") or {}).get("name_text"),
                    "collector_text": (item.get("ocr") or {}).get("collector_text"),
                    "failed": (item.get("ocr") or {}).get("failed"),
                },
                "predicted": item.get("predicted") or [],
                "images": with_api_image_urls(item)["images"],
            }
            for item in sliced
        ],
    }


def refresh_index(root: Path) -> None:
    records = load_cases(root)
    counts: dict[str, int] = {}
    attention: list[dict[str, Any]] = []
    confirmed: list[dict[str, Any]] = []
    for record in records:
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        flags = record.get("review") or review_flags(record)
        if flags.get("needs_attention"):
            attention.append(record)
        elif record.get("confirmed_card_id"):
            confirmed.append(record)

    labels = [row for row in (_label_row(item) for item in records) if row]
    _write_text(
        root / "review.jsonl",
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
    )
    _write_text(
        root / "labels.jsonl",
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in labels),
    )
    attention_block = "\n".join(_line(item) for item in attention[:40]) or "- none"
    confirmed_block = "\n".join(_line(item) for item in confirmed[:20]) or "- none"
    summary = "\n".join(
        [
            "# Recognition review",
            "",
            "Start here. Photos and per-scan JSON live next to this file.",
            "Open `images/<scan_id>.query.jpg` to see what the model scored,",
            "and `images/<scan_id>.input.jpg` for the upload/crop before detect.",
            "",
            f"- scans: {len(records)}",
            f"- confirmed labels: {sum(1 for item in labels if not item.get('unknown'))}",
            f"- unknown/rejected labels: {sum(1 for item in labels if item.get('unknown'))}",
            f"- needs attention: {len(attention)}",
            f"- matched: {counts.get('matched', 0)}",
            f"- uncertain: {counts.get('uncertain', 0)}",
            f"- no_match: {counts.get('no_match', 0)}",
            f"- retake: {counts.get('retake', 0)}",
            "",
            "## Needs attention",
            attention_block,
            "",
            "## Confirmed",
            confirmed_block,
            "",
        ]
    )
    _write_text(root / "SUMMARY.md", summary + "\n")
    _write_json(
        root / "index.json",
        {
            "n": len(records),
            "needs_attention": len(attention),
            "status_counts": counts,
            "latest": [item.get("scan_id") for item in records[:20]],
        },
    )
