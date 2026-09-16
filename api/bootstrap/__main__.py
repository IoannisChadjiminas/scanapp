from __future__ import annotations

import os
from pathlib import Path

from bootstrap.catalogue import import_catalogue
from bootstrap.dinov2_export import export_dinov2
from bootstrap.download import download_rapidocr
from bootstrap.embeddings import build_embeddings


def main() -> None:
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    models_dir = data_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    print("== models")
    download_rapidocr(models_dir)
    dinov2 = export_dinov2(models_dir)
    print("== catalogue")
    import_catalogue(data_dir)
    print("== embeddings")
    for preprocess in ("pad", "square"):
        build_embeddings(data_dir, preprocess, str(dinov2["revision"]))
    print("bootstrap complete")


if __name__ == "__main__":
    main()
