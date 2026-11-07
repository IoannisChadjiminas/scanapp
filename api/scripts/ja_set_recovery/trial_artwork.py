"""Write an artwork bundle without some cards, for a replay trial. Local files only.

    python3 trial_artwork.py SOURCE_ARTWORK_DIR EXCLUDE_IDS_JSON OUTPUT_DIR
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def main(source, exclude_file, output):
    source, output = Path(source), Path(output)
    drop = set(json.loads(Path(exclude_file).read_text()))
    records = json.loads((source / "records.json").read_text())
    vectors = np.load(source / "embeddings.npy")
    keep = [i for i, r in enumerate(records) if r["card_id"] not in drop]
    output.mkdir(parents=True, exist_ok=False)
    np.save(output / "embeddings.npy", vectors[keep])
    kept = [records[i] for i in keep]
    (output / "records.json").write_text(json.dumps(kept, ensure_ascii=False, separators=(",", ":")))
    manifest = json.loads((source / "manifest.json").read_text())
    manifest.update(
        embeddings_sha256=hashlib.sha256((output / "embeddings.npy").read_bytes()).hexdigest(),
        records_sha256=hashlib.sha256((output / "records.json").read_bytes()).hexdigest(),
        indexed_regions=len(kept), indexed_cards=len({r["card_id"] for r in kept}))
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"regions": len(kept), "removed": len(records) - len(kept)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
