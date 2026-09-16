from __future__ import annotations

import json
import os
from pathlib import Path

from bootstrap.catalogue import import_catalogue
from bootstrap.dinov2_export import export_dinov2
from bootstrap.download import download_rapidocr
from bootstrap.embeddings import build_embeddings
from bootstrap.extra import import_extra_cards


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _existing_revision(data_dir: Path) -> str:
    manifest = data_dir / "vectors" / "pad" / "manifest.json"
    if not manifest.is_file():
        raise SystemExit("No existing pad snapshot. Run a full bootstrap first.")
    return str(json.loads(manifest.read_text())["model_revision"])


def main() -> None:
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    models_dir = data_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    extras_only = _truthy("BOOTSTRAP_EXTRAS_ONLY")

    if extras_only:
        print("== extra cards only")
        import_extra_cards(data_dir)
        revision = _existing_revision(data_dir)
    else:
        print("== models")
        download_rapidocr(models_dir)
        dinov2 = export_dinov2(models_dir)
        revision = str(dinov2["revision"])
        print("== catalogue")
        import_catalogue(data_dir)
        print("== extra cards")
        import_extra_cards(data_dir)

    print("== embeddings")
    for preprocess in ("pad", "square"):
        build_embeddings(data_dir, preprocess, revision)
    print("bootstrap complete")


if __name__ == "__main__":
    main()
