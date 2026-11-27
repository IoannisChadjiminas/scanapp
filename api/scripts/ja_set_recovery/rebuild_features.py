"""Rebuild reference features for cards whose rarity changed, on top of a served feature bundle.

Runs inside the API image (the feature contract pins the OpenCV build):

    python3 /work/rebuild_features.py PARENT_DIR_NAME NEW_DIR_NAME

/work holds feature-rows.json ({id, image_path, rarity} of the cards to rebuild; the rarity picks
the art box) and signature-rows.json (every catalogue row, with the new rarities). Unlike
stage_features.py, the rebuilt cards already have records, and their filenames (sha256 of the
card id) are the parent's: the new directory is hard-linked from the parent, and each rebuilt
file's link is removed before the new file is written, so the parent's files are never touched.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from app.recognition.artifacts import sha256_file  # noqa: E402
from app.recognition.reference_features import (  # noqa: E402
    build_reference_bundle, catalogue_signature, processing_contract)

DATA = Path("/data")
WORK = Path("/work")


def main(parent_name, new_name):
    parent = DATA / "reference-features" / parent_name
    dest = DATA / "reference-features" / new_name
    if dest.exists() or dest.with_name(new_name + ".preparing").exists():
        raise SystemExit("feature destination already exists")
    rows = json.loads((WORK / "feature-rows.json").read_text())
    signature_rows = json.loads((WORK / "signature-rows.json").read_text())
    parent_sha = sha256_file(parent / "manifest.json")
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    if parent_manifest["processing"] != processing_contract():
        raise SystemExit("parent processing contract differs from this image")
    for row in rows:
        old = parent_manifest["records"].get(row["id"])
        if not old or not old["available"] or old["image_path"] != row["image_path"]:
            raise SystemExit(f"{row['id']} has no matching parent record")
    fragment = WORK / "feature-fragment"
    if (fragment / "manifest.json").is_file():
        manifest = json.loads((fragment / "manifest.json").read_text())
    else:
        manifest = build_reference_bundle(rows, DATA, fragment, workers=1)
    if manifest["processing"] != parent_manifest["processing"]:
        raise SystemExit("fragment processing contract differs")
    if set(manifest["records"]) != {r["id"] for r in rows} or not all(r["available"] for r in manifest["records"].values()):
        raise SystemExit("fragment does not cover every rebuilt card")
    work = dest.with_name(new_name + ".preparing")
    shutil.copytree(parent, work, copy_function=os.link)
    (work / "manifest.json").unlink()
    for card_id, record in manifest["records"].items():
        target = work / record["filename"]
        if record["filename"] != parent_manifest["records"][card_id]["filename"]:
            raise SystemExit(f"unexpected filename for {card_id}")
        target.unlink()  # drop the hard link to the parent's file, then write a new file
        shutil.copyfile(fragment / record["filename"], target)
        parent_manifest["records"][card_id] = record
    if sha256_file(parent / "manifest.json") != parent_sha:
        raise SystemExit("parent feature manifest changed")
    for card_id, record in manifest["records"].items():
        if sha256_file(parent / record["filename"]) == record["sha256"]:
            raise SystemExit(f"{card_id}: rebuilt file equals the parent's; nothing changed")
    if set(parent_manifest["records"]) != {r["id"] for r in signature_rows}:
        raise SystemExit("feature coverage does not match the signature rows")
    parent_manifest["catalogue_sha256"] = catalogue_signature(signature_rows)
    (work / "manifest.json").write_text(json.dumps(parent_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    work.rename(dest)
    print(json.dumps({
        "rebuilt": len(manifest["records"]),
        "available": sum(r["available"] for r in parent_manifest["records"].values()),
        "cards": len(parent_manifest["records"]),
        "catalogue_sha256": parent_manifest["catalogue_sha256"],
        "manifest_sha256": hashlib.sha256((dest / "manifest.json").read_bytes()).hexdigest(),
        "parent_sha256": parent_sha,
    }), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
