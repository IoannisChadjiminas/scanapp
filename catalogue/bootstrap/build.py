from __future__ import annotations

import argparse
import os
from pathlib import Path

from bootstrap.catalogue import import_catalogue
from bootstrap.dinov2_export import export_dinov2
from bootstrap.download import download_rapidocr
from bootstrap.embeddings import build_embeddings, read_model_revision
from bootstrap.extra import import_extra_cards


def _sets(raw: str) -> set[str] | None:
    items = {item.strip() for item in raw.split(",") if item.strip()}
    if not items:
        return set()
    if any(item.lower() == "all" for item in items):
        return None
    return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download TCGdex scans, build DINOv2 vectors, and store CDN image URLs. "
            "Images stay on this machine for embedding; the UI uses assets.tcgdex.net."
        )
    )
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument(
        "--sets",
        default=os.environ.get("BOOTSTRAP_ADD_SETS") or os.environ.get("CATALOGUE_SETS", ""),
        help="Comma-separated TCGdex set ids, or 'all'. Default: BOOTSTRAP_ADD_SETS / CATALOGUE_SETS.",
    )
    parser.add_argument(
        "--languages",
        default=os.environ.get("TCGDEX_LANGUAGES") or os.environ.get("TCGDEX_LANGUAGE", "en"),
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Wipe the catalogue first (does not keep extras unless you re-import them).",
    )
    parser.add_argument(
        "--extras",
        action="store_true",
        help="Also copy extra-cards into the catalogue after the TCGdex import.",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="Reuse DINOv2 / OCR already in DATA_DIR (needed for add-set builds).",
    )
    args = parser.parse_args()
    os.environ["TCGDEX_LANGUAGES"] = args.languages
    data_dir = Path(args.data_dir)
    models_dir = data_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    allowed = _sets(args.sets)
    if allowed == set() and not args.replace:
        raise SystemExit("Pass --sets sv03.5 (or --sets all) so the builder knows what to fetch.")

    if args.replace and not args.skip_models:
        print("== models")
        download_rapidocr(models_dir)
        dinov2 = export_dinov2(models_dir)
        revision = str(dinov2["revision"])
    else:
        revision = read_model_revision(data_dir)

    print("== catalogue")
    import_catalogue(
        data_dir,
        replace=args.replace,
        sets=None if allowed is None else allowed,
    )
    if args.extras or args.replace:
        print("== extra cards")
        import_extra_cards(data_dir)

    print("== embeddings")
    for preprocess in ("pad", "square"):
        build_embeddings(data_dir, preprocess, revision)
    print("build complete")


if __name__ == "__main__":
    main()
