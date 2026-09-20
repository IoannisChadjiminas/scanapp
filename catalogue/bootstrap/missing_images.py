from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from app.db import connect, coverage, init_catalog
from bootstrap.download import download_file


def _row_item(row: Any) -> dict[str, str]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"] or ""),
        "set_id": str(row["set_id"] or ""),
        "set_name": str(row["set_name"] or ""),
        "collector_number": str(row["collector_number"] or ""),
        "language": str(row["language"] or ""),
        "remote_image_url": str(row["remote_image_url"] or ""),
        "cardmarket_url": str(row["cardmarket_url"] or ""),
    }


def unmatched_cardmarket_products(conn) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT url, name, expansion
        FROM cardmarket_expansion_products
        WHERE matched = 0 OR card_id IS NULL OR card_id = ''
        ORDER BY expansion, url
        """
    ).fetchall()
    by_expansion: Counter[str] = Counter()
    products: list[dict[str, str]] = []
    for row in rows:
        expansion = str(row["expansion"] or "")
        by_expansion[expansion] += 1
        products.append(
            {
                "url": str(row["url"] or ""),
                "name": str(row["name"] or ""),
                "expansion": expansion,
            }
        )
    return {
        "unmatched_cardmarket": len(products),
        "unmatched_cardmarket_by_expansion": [
            {"expansion": expansion, "unmatched": count}
            for expansion, count in by_expansion.most_common()
        ],
        "unmatched_cardmarket_products": products,
    }


def missing_image_report(conn, data_dir: Path) -> dict[str, Any]:
    cards_n, indexed_n, missing_n = coverage(conn)
    retryable: list[dict[str, str]] = []
    no_cdn: list[dict[str, str]] = []
    rows = conn.execute(
        """
        SELECT id, name, set_id, set_name, collector_number, language,
               image_path, has_image, remote_image_url, cardmarket_url
        FROM cards
        ORDER BY language, set_id, collector_number, id
        """
    ).fetchall()
    for row in rows:
        path_raw = str(row["image_path"] or "").strip()
        has_file = bool(path_raw) and Path(path_raw).is_file()
        if int(row["has_image"] or 0) == 1 and has_file:
            continue
        item = _row_item(row)
        remote = item["remote_image_url"]
        if remote.startswith("https://"):
            retryable.append(item)
        else:
            no_cdn.append(item)
    missing = retryable + no_cdn
    by_language: dict[str, dict[str, int]] = {}
    by_set: Counter[tuple[str, str, str]] = Counter()
    set_names: dict[tuple[str, str], str] = {}
    for item in missing:
        language = item["language"] or "?"
        bucket = by_language.setdefault(
            language, {"missing": 0, "retryable": 0, "no_cdn": 0}
        )
        bucket["missing"] += 1
        if item["remote_image_url"].startswith("https://"):
            bucket["retryable"] += 1
        else:
            bucket["no_cdn"] += 1
        key = (language, item["set_id"], item["set_name"])
        by_set[key] += 1
        set_names[(language, item["set_id"])] = item["set_name"]
    with_cm = sum(1 for item in missing if item["cardmarket_url"].startswith("https://"))
    payload = {
        "cards": cards_n,
        "with_image": indexed_n,
        "missing": len(missing),
        "coverage_missing": missing_n,
        "retryable": len(retryable),
        "no_cdn": len(no_cdn),
        "missing_with_cardmarket_url": with_cm,
        "missing_without_cardmarket_url": len(missing) - with_cm,
        "by_language": by_language,
        "by_set": [
            {
                "language": language,
                "set_id": set_id,
                "set_name": set_name,
                "missing": count,
            }
            for (language, set_id, set_name), count in by_set.most_common()
        ],
        "retryable_cards": retryable,
        "no_cdn_cards": no_cdn,
        "data_dir": str(data_dir),
    }
    payload.update(unmatched_cardmarket_products(conn))
    return payload


def retry_missing_images(
    conn,
    data_dir: Path,
    report: dict[str, Any],
    *,
    limit: int | None = None,
) -> dict[str, int]:
    images_dir = data_dir / "reference-images"
    fetched = 0
    failed = 0
    items = list(report.get("retryable_cards") or [])
    if limit is not None:
        items = items[: max(limit, 0)]
    for item in items:
        url = item["remote_image_url"]
        language = item["language"] or "en"
        card_id = item["id"]
        provider_id = card_id.split(":", 1)[-1]
        dest = images_dir / language / f"{provider_id}.webp"
        try:
            download_file(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip image {card_id}: {exc}")
            failed += 1
            continue
        conn.execute(
            """
            UPDATE cards
            SET image_path = ?, has_image = 1
            WHERE id = ?
            """,
            (str(dest), card_id),
        )
        fetched += 1
        print(f"  saved {card_id}")
    if fetched:
        conn.commit()
    return {"fetched": fetched, "failed": failed, "attempted": len(items)}


def _print_summary(report: dict[str, Any]) -> None:
    print(
        f"cards {report['cards']}, with_image {report['with_image']}, "
        f"missing {report['missing']} "
        f"(retryable {report['retryable']}, no CDN {report['no_cdn']})"
    )
    print("by language:")
    for language, bucket in sorted(report["by_language"].items()):
        print(
            f"  {language}: missing {bucket['missing']} "
            f"retryable {bucket['retryable']} no_cdn {bucket['no_cdn']}"
        )
    print("top missing sets:")
    for item in report["by_set"][:20]:
        print(
            f"  {item['language']}:{item['set_id']} {item['set_name']} "
            f"missing {item['missing']}"
        )
    print(
        f"missing images with Cardmarket URL {report.get('missing_with_cardmarket_url', 0)}, "
        f"without {report.get('missing_without_cardmarket_url', 0)}"
    )
    with_cm = [
        item
        for item in (report.get("retryable_cards") or []) + (report.get("no_cdn_cards") or [])
        if str(item.get("cardmarket_url") or "").startswith("https://")
    ]
    if with_cm:
        print("missing images that already have a Cardmarket URL:")
        for item in with_cm[:20]:
            print(f"  {item['id']} {item['cardmarket_url']}")
        if len(with_cm) > 20:
            print(f"  … {len(with_cm) - 20} more")
    print(f"unmatched Cardmarket products {report.get('unmatched_cardmarket', 0)}")
    for item in (report.get("unmatched_cardmarket_by_expansion") or [])[:15]:
        print(f"  {item['expansion'] or '(none)'}: {item['unmatched']}")
    unmatched = report.get("unmatched_cardmarket_products") or []
    if unmatched:
        print("unmatched Cardmarket URLs:")
        for item in unmatched[:20]:
            print(f"  {item['url']}")
        if len(unmatched) > 20:
            print(f"  … {len(unmatched) - 20} more")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "List catalogue cards with no downloaded reference image. "
            "Retryable rows still have a TCGdex URL; no-CDN rows never had one."
        )
    )
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument("--out", default="", help="Write JSON report here.")
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Download missing images that still have a TCGdex URL.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Retry at most N images.")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    out = Path(args.out) if args.out else data_dir / "missing-images.json"
    conn = connect(data_dir / "catalog.sqlite")
    init_catalog(conn)
    report = missing_image_report(conn, data_dir)
    _print_summary(report)
    if args.retry:
        limit = args.limit if args.limit > 0 else None
        stats = retry_missing_images(conn, data_dir, report, limit=limit)
        print(
            f"retry fetched {stats['fetched']}, failed {stats['failed']}, "
            f"attempted {stats['attempted']}"
        )
        report = missing_image_report(conn, data_dir)
        report["retry"] = stats
        print("after retry:")
        _print_summary(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    urls_path = out.with_name("missing-cardmarket-urls.txt")
    urls_path.write_text(
        "".join(
            f"{item['url']}\n"
            for item in report.get("unmatched_cardmarket_products") or []
            if item.get("url")
        )
    )
    print(f"wrote {out}")
    print(f"wrote {urls_path}")
    conn.close()


if __name__ == "__main__":
    main()
