from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from app.cardmarket import apply_cardmarket_links, helper_maps_path
from app.db import connect, coverage, init_catalog
from bootstrap.catalogue import upsert_card

CARD_FIELDS = (
    "id",
    "provider_id",
    "name",
    "set_id",
    "set_name",
    "collector_number",
    "language",
    "category",
    "rarity",
    "illustrator",
    "variants_json",
    "has_image",
    "cardmarket_id",
    "cardmarket_url",
    "cardmarket_verified",
    "cardmarket_provenance",
    "cardmarket_verified_at",
    "remote_image_url",
)


def _active_bundle(root: Path) -> Path | None:
    pointer = root / "ACTIVE"
    if pointer.is_file():
        bundle = root / pointer.read_text().strip()
        if bundle.is_dir():
            return bundle
    if (root / "embeddings.npy").is_file():
        return root
    return None


def _row_payload(row: Any, *, extra_file: str | None = None) -> dict[str, Any]:
    payload = {}
    for field in CARD_FIELDS:
        if field not in row.keys():
            continue
        payload[field] = row[field]
    payload["image_path"] = None
    if extra_file:
        payload["_extra_file"] = extra_file
    return payload


def _pack_extra_image(row: Any, extras_dir: Path) -> str | None:
    card_id = str(row["id"] or "")
    path = Path(str(row["image_path"] or ""))
    if not card_id.startswith("extra-") or not path.is_file():
        return None
    extras_dir.mkdir(parents=True, exist_ok=True)
    name = f"{card_id}{path.suffix.lower()}"
    shutil.copy2(path, extras_dir / name)
    return name


def export_bundle(data_dir: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    catalog = connect(data_dir / "catalog.sqlite")
    init_catalog(catalog)
    staging = Path(tempfile.mkdtemp(prefix="scanapp-offload-"))
    extras_dir = staging / "extras"
    try:
        cards = []
        for row in catalog.execute("SELECT * FROM cards ORDER BY id"):
            extra_file = _pack_extra_image(row, extras_dir)
            cards.append(_row_payload(row, extra_file=extra_file))
        expansions = [
            {key: row[key] for key in row.keys()}
            for row in catalog.execute(
                "SELECT * FROM cardmarket_expansion_products ORDER BY url"
            )
        ]
        catalog.close()
        (staging / "cards.jsonl").write_text(
            "".join(json.dumps(card, ensure_ascii=False) + "\n" for card in cards)
        )
        (staging / "expansion-products.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in expansions)
        )
        version_path = data_dir / "catalogue-version.json"
        version = json.loads(version_path.read_text()) if version_path.is_file() else {}
        (staging / "catalogue-version.json").write_text(json.dumps(version, indent=2) + "\n")
        maps = helper_maps_path(data_dir)
        if maps.is_file():
            shutil.copy2(maps, staging / "cardmarket-maps.json")
        dump_dir = data_dir / "expansion-imports"
        dump_count = 0
        if dump_dir.is_dir():
            target = staging / "expansion-imports"
            target.mkdir()
            for path in dump_dir.glob("*.json"):
                shutil.copy2(path, target / path.name)
                dump_count += 1
        bundles = {}
        for preprocess in ("pad", "square"):
            bundle = _active_bundle(data_dir / "vectors" / preprocess)
            if bundle is None:
                continue
            target = staging / "vectors" / preprocess / bundle.name
            shutil.copytree(bundle, target)
            (staging / "vectors" / preprocess / "ACTIVE").write_text(bundle.name + "\n")
            bundles[preprocess] = bundle.name
        manifest = {
            "kind": "scanapp-index",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cards": len(cards),
            "expansion_products": len(expansions),
            "expansion_dumps": dump_count,
            "extras": sum(1 for card in cards if card.get("_extra_file")),
            "with_remote_image_url": sum(
                1
                for card in cards
                if str(card.get("remote_image_url") or "").startswith("https://")
            ),
            "includes_official_images": False,
            "vector_bundles": bundles,
            "catalogue_version": version.get("catalogue_version"),
        }
        (staging / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        dest = dest if dest.suffix == ".tar" else dest.with_suffix(".tar")
        with tarfile.open(dest, "w") as archive:
            for path in staging.iterdir():
                archive.add(path, arcname=path.name)
        print(
            f"offload wrote {dest} ({len(cards)} cards, {len(expansions)} set URLs, "
            f"{dump_count} Cardmarket dumps, no official scans)"
        )
        return dest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _copy_vectors(extracted: Path, data_dir: Path) -> None:
    source_root = extracted / "vectors"
    if not source_root.is_dir():
        raise SystemExit("Bundle has no vectors/")
    for preprocess in ("pad", "square"):
        src = source_root / preprocess
        if not src.is_dir():
            continue
        active = (src / "ACTIVE").read_text().strip() if (src / "ACTIVE").is_file() else ""
        bundle = src / active if active else src
        if not (bundle / "embeddings.npy").is_file():
            raise SystemExit(f"Bundle missing embeddings for {preprocess}")
        dest_root = data_dir / "vectors" / preprocess
        dest = dest_root / bundle.name
        dest_root.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(bundle, dest)
        (dest_root / "ACTIVE").write_text(dest.name + "\n")
        print(f"  vectors {preprocess} -> {dest.name}")


def _apply_expansions(conn: Any, path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        conn.execute(
            """
            INSERT INTO cardmarket_expansion_products (
                url, expansion, name, source, page_url, card_id, matched, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                expansion = excluded.expansion,
                name = COALESCE(excluded.name, cardmarket_expansion_products.name),
                source = excluded.source,
                page_url = excluded.page_url,
                card_id = COALESCE(excluded.card_id, cardmarket_expansion_products.card_id),
                matched = CASE
                    WHEN excluded.matched > cardmarket_expansion_products.matched
                    THEN excluded.matched
                    ELSE cardmarket_expansion_products.matched
                END,
                imported_at = excluded.imported_at
            """,
            (
                item.get("url"),
                item.get("expansion"),
                item.get("name"),
                item.get("source") or "page",
                item.get("page_url"),
                item.get("card_id"),
                int(item.get("matched") or 0),
                item.get("imported_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
        )
        n += 1
    return n


def _merge_helper_maps(extracted: Path, data_dir: Path) -> None:
    incoming = extracted / "cardmarket-maps.json"
    if not incoming.is_file():
        return
    dest = helper_maps_path(data_dir)
    merged: dict[str, Any] = {"cards": {}}
    if dest.is_file():
        try:
            loaded = json.loads(dest.read_text())
            if isinstance(loaded, dict) and isinstance(loaded.get("cards"), dict):
                merged["cards"] = loaded["cards"]
        except json.JSONDecodeError:
            merged = {"cards": {}}
    payload = json.loads(incoming.read_text())
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if isinstance(cards, dict):
        merged["cards"].update(cards)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(merged, indent=2) + "\n")


def apply_bundle(archive: Path, data_dir: Path) -> dict[str, Any]:
    if not archive.is_file():
        raise SystemExit(f"Missing bundle {archive}")
    staging = Path(tempfile.mkdtemp(prefix="scanapp-apply-"))
    try:
        with tarfile.open(archive, "r") as tar:
            try:
                tar.extractall(staging, filter="data")
            except TypeError:
                tar.extractall(staging)
        root = staging
        if not (root / "cards.jsonl").is_file():
            children = [path for path in root.iterdir() if path.is_dir()]
            if len(children) == 1:
                root = children[0]
        cards_path = root / "cards.jsonl"
        if not cards_path.is_file():
            raise SystemExit("Bundle is missing cards.jsonl")
        catalog_path = data_dir / "catalog.sqlite"
        conn = connect(catalog_path)
        init_catalog(conn)
        imported = 0
        for line in cards_path.read_text().splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            image_path = None
            extra_file = payload.get("_extra_file")
            if extra_file:
                src = root / "extras" / str(extra_file)
                if src.is_file():
                    dest = data_dir / "reference-images" / Path(str(extra_file)).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    image_path = str(dest)
            upsert_card(
                conn,
                card_id=str(payload["id"]),
                provider_id=str(payload.get("provider_id") or payload["id"]),
                name=str(payload.get("name") or "Unknown"),
                set_id=str(payload.get("set_id") or ""),
                set_name=str(payload.get("set_name") or ""),
                collector_number=str(payload.get("collector_number") or ""),
                language=str(payload.get("language") or "en"),
                category=payload.get("category"),
                rarity=payload.get("rarity"),
                illustrator=payload.get("illustrator"),
                variants_json=str(payload.get("variants_json") or "{}"),
                image_path=image_path,
                has_image=int(payload.get("has_image") or 0) or int(bool(image_path)),
                cardmarket_id=payload.get("cardmarket_id"),
                cardmarket_url=payload.get("cardmarket_url"),
                cardmarket_verified=int(payload.get("cardmarket_verified") or 0),
                cardmarket_provenance=payload.get("cardmarket_provenance"),
                cardmarket_verified_at=payload.get("cardmarket_verified_at"),
                remote_image_url=payload.get("remote_image_url"),
            )
            imported += 1
        expansions = _apply_expansions(conn, root / "expansion-products.jsonl")
        incoming_dumps = root / "expansion-imports"
        if incoming_dumps.is_dir():
            dest_dumps = data_dir / "expansion-imports"
            dest_dumps.mkdir(parents=True, exist_ok=True)
            for path in incoming_dumps.glob("*.json"):
                shutil.copy2(path, dest_dumps / path.name)
        conn.commit()
        _merge_helper_maps(root, data_dir)
        stats = apply_cardmarket_links(conn, data_dir)
        _copy_vectors(root, data_dir)
        version_src = root / "catalogue-version.json"
        if version_src.is_file():
            shutil.copy2(version_src, data_dir / "catalogue-version.json")
        cards_n, indexed, missing = coverage(conn)
        conn.close()
        print(
            f"apply upserted {imported} cards, {expansions} set URLs "
            f"(catalogue now {cards_n}, indexed {indexed}, missing {missing}; "
            f"cardmarket linked {stats['expansion_linked']})"
        )
        print("restart the API so it loads the new ACTIVE snapshot")
        return {"imported": imported, "cards": cards_n, "indexed": indexed, "expansions": expansions}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def default_export_path(data_dir: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if Path("/exports").is_dir():
        return Path("/exports") / "scanapp-index.tar"
    return data_dir / "exports" / f"scanapp-index-{stamp}.tar"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pack or load a portable local index for staging (vectors, URLs, extras, Cardmarket maps)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    export_cmd = sub.add_parser("export", help="Write a .tar from local DATA_DIR")
    export_cmd.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    export_cmd.add_argument("-o", "--output", default="")
    apply_cmd = sub.add_parser("apply", help="Merge a .tar into DATA_DIR (staging)")
    apply_cmd.add_argument("archive")
    apply_cmd.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    args = parser.parse_args()
    if args.command == "export":
        data_dir = Path(args.data_dir)
        dest = Path(args.output) if args.output else default_export_path(data_dir)
        export_bundle(data_dir, dest)
        return
    apply_bundle(Path(args.archive), Path(args.data_dir))


if __name__ == "__main__":
    main()
