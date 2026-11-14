"""Make the reference-feature bundle of a clean-up release: the parent bundle without the deleted rows.

    python3 cleanup_features.py PARENT_DIR NEW_DIR SIGNATURE_ROWS_JSON DELETED_JSON

No feature is computed: NEW_DIR is a hard-linked copy of PARENT_DIR without the deleted rows' .npz
files, and its manifest drops their records and is re-signed over the remaining catalogue rows
(app.recognition.reference_features.catalogue_signature). Prints the new manifest's sha256, which
prepare_sql_cleanup.py stores in the import manifest. Runs on this Mac (local replay data) and on the
staging host (python3 -I, standard library only); both must print the same sha256.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


def catalogue_signature(rows):
    # Same as app.recognition.reference_features.catalogue_signature.
    values = sorted((str(r["id"]), str(r.get("image_path") or ""), str(r.get("rarity") or "").casefold()) for r in rows)
    return hashlib.sha256(json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def new_manifest(parent_manifest, signature_rows, deleted):
    manifest = json.loads(json.dumps(parent_manifest))
    records = manifest["records"]
    assert set(deleted) <= set(records)
    for card_id in deleted:
        del records[card_id]
    assert set(records) == {str(r["id"]) for r in signature_rows}
    manifest["catalogue_sha256"] = catalogue_signature(signature_rows)
    manifest["cards"] = len(records)
    manifest["available"] = sum(bool(r["available"]) for r in records.values())
    return manifest


def main(parent_dir, new_dir, signature_path, deleted_path):
    parent, new = Path(parent_dir), Path(new_dir)
    if new.exists():
        raise SystemExit("destination exists")
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    deleted = json.loads(Path(deleted_path).read_text())
    gone = {parent_manifest["records"][c]["filename"] for c in deleted if parent_manifest["records"][c].get("available")}
    manifest = new_manifest(parent_manifest, json.loads(Path(signature_path).read_text()), deleted)
    work = new.with_name(new.name + ".preparing")
    shutil.copytree(parent, work, copy_function=os.link, ignore=lambda d, names: [n for n in names if n in gone])
    (work / "manifest.json").unlink()
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    work.rename(new)
    sha = hashlib.sha256((new / "manifest.json").read_bytes()).hexdigest()
    print(json.dumps({"cards": manifest["cards"], "available": manifest["available"], "removed_files": len(gone),
                      "manifest_sha256": sha}))


if __name__ == "__main__":
    main(*sys.argv[1:5])
