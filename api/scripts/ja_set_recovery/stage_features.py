"""Build reference features for the recovery's new cards inside the API image on staging.

The feature contract pins the OpenCV build, so this runs in a separate, resource-limited
container from the retained API image (never inside the live API container), as in
data/catalogue-gaps/tcgdex-empty-sets-20261017/build_features.py:

    docker run --rm --memory 1200m --memory-swap 1200m --cpus 1 \
      -v <data volume>:/data -v <work dir>:/work <api image> \
      python3 /work/stage_features.py PARENT_DIR_NAME NEW_DIR_NAME

/work holds feature-rows.json and signature-rows.json from the release. The new directory
is hard-linked from the parent (parent manifest unchanged), receives the new .npz files
and a merged manifest. New cards without an image get `available: false` records.
Resumable: the fragment under /work/feature-fragment is reused when complete.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from app.recognition.artifacts import sha256_file  # noqa: E402
from app.recognition.printing import ART_BOX  # noqa: E402
from app.recognition.reference_features import (  # noqa: E402
    build_reference_bundle, catalogue_signature, processing_contract)

DATA = Path("/data")
WORK = Path("/work")


def main(parent_name, new_name):
    parent = DATA / "reference-features" / parent_name
    dest = DATA / "reference-features" / new_name
    if dest.exists():
        raise SystemExit("feature destination already exists")
    rows = json.loads((WORK / "feature-rows.json").read_text())
    signature_rows = json.loads((WORK / "signature-rows.json").read_text())
    for row in rows:
        if not (DATA / row["image_path"].removeprefix("/data/")).is_file():
            raise SystemExit(f"missing image {row['image_path']}")
    parent_sha = sha256_file(parent / "manifest.json")
    fragment = WORK / "feature-fragment"
    if (fragment / "manifest.json").is_file():
        manifest = json.loads((fragment / "manifest.json").read_text())
    else:
        manifest = build_reference_bundle(rows, DATA, fragment, workers=1,
                                          progress=lambda n, t: n % 500 == 0 and print(json.dumps({"features": n, "of": t}), flush=True))
    if manifest["processing"] != processing_contract():
        raise SystemExit("fragment processing contract does not match this image")
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    if parent_manifest["processing"] != manifest["processing"]:
        raise SystemExit("parent processing contract differs")
    shutil.copytree(parent, dest.with_name(new_name + ".preparing"), copy_function=os.link)
    work = dest.with_name(new_name + ".preparing")
    (work / "manifest.json").unlink()
    if sha256_file(parent / "manifest.json") != parent_sha:
        raise SystemExit("parent feature manifest changed")
    for card_id, record in manifest["records"].items():
        if record["available"]:
            target = work / record["filename"]
            if target.exists():
                raise SystemExit(f"feature filename collision {record['filename']}")
            shutil.copyfile(fragment / record["filename"], target)
        parent_manifest["records"][card_id] = record
    known = set(parent_manifest["records"])
    for row in signature_rows:
        if row["id"] not in known:
            parent_manifest["records"][row["id"]] = {"art_box": list(ART_BOX), "available": False, "image_path": ""}
    parent_manifest["catalogue_sha256"] = catalogue_signature(signature_rows)
    parent_manifest["available"] = sum(r["available"] for r in parent_manifest["records"].values())
    parent_manifest["cards"] = len(parent_manifest["records"])
    if parent_manifest["cards"] != len(signature_rows):
        raise SystemExit("feature coverage does not match the signature rows")
    (work / "manifest.json").write_text(json.dumps(parent_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    work.rename(dest)
    print(json.dumps({
        "new_available": sum(r["available"] for r in manifest["records"].values()),
        "available": parent_manifest["available"], "cards": parent_manifest["cards"],
        "manifest_sha256": hashlib.sha256((dest / "manifest.json").read_bytes()).hexdigest(),
        "parent_sha256": sha256_file(parent / "manifest.json"),
    }), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
