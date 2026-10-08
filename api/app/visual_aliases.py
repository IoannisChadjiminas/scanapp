"""Verified image delivery aliases; never alter retrieval or printing decisions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote


def identity_sha256(row) -> str:
    fields = ("id", "provider_id", "name", "set_id", "set_name",
              "collector_number", "language", "category", "illustrator")
    payload = {key: row[key] for key in fields}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_visual_aliases(catalog, contract, *, indexed_ids, image_root: Path):
    """Validate the entire snapshot before returning an immutable owner map.

    Source bytes are checked once at startup. A visual alias conveys no finish,
    stamp, URL, artist correction or automatic printing-confirmation evidence.
    """
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("Unsupported visual image alias contract")
    records = contract.get("records")
    if not isinstance(records, list) or len(records) > 512:
        raise ValueError("Invalid visual image alias records")
    aliases = [r.get("alias_id") for r in records if isinstance(r, dict)]
    if len(aliases) != len(records) or len(set(aliases)) != len(aliases):
        raise ValueError("Duplicate or invalid visual image alias")
    owners = {}
    indexed = set(indexed_ids)
    root = image_root.resolve()
    for record in records:
        alias_id, owner_id = record["alias_id"], record.get("owner_id")
        if not isinstance(alias_id, str) or not isinstance(owner_id, str):
            raise ValueError("Invalid visual image alias identity")
        if owner_id in aliases or alias_id in indexed or owner_id not in indexed:
            raise ValueError("Visual image alias chain or invalid indexed owner")
        alias = catalog.execute("SELECT * FROM cards WHERE id=?", (alias_id,)).fetchone()
        owner = catalog.execute("SELECT * FROM cards WHERE id=?", (owner_id,)).fetchone()
        if alias is None or owner is None:
            raise ValueError("Visual image alias references missing card")
        if alias["has_image"] or alias["image_path"] or alias["remote_image_url"]:
            raise ValueError("Visual image alias would replace an existing image")
        if alias["language"] != owner["language"] or unquote(alias["collector_number"]) != unquote(owner["collector_number"]):
            raise ValueError("Visual image alias language or collector mismatch")
        if identity_sha256(alias) != record.get("alias_identity_sha256") or identity_sha256(owner) != record.get("owner_identity_sha256"):
            raise ValueError("Visual image alias identity checksum mismatch")
        path = Path(owner["image_path"] or "").resolve()
        if not owner["has_image"] or not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Visual image alias source missing or outside image root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("source_sha256"):
            raise ValueError("Visual image alias source checksum mismatch")
        owners[alias_id] = MappingProxyType(dict(owner))
    return MappingProxyType(owners)


def visual_image_owner(row, catalog=None):
    registry = getattr(catalog, "visual_image_aliases", {})
    return registry.get(str(row["id"]), row)
