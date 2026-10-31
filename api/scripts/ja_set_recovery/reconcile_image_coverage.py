"""Reconcile Japanese set-recovery checklist rows against acquired image files."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
OUT_CSV = REVIEW / "image-coverage-reconciliation-20261030.csv"
OUT_JSON = REVIEW / "image-coverage-reconciliation-20261030.json"


def norm_number(value: str) -> str:
    return str(value or "").strip().upper()


def number_matches(checklist: str, official: str) -> bool:
    a, b = norm_number(checklist), norm_number(official)
    return a == b or bool(a and b and "/" not in a and "/" in b and b.split("/", 1)[0] == a)


def main() -> None:
    rows: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for path in REVIEW.glob("*-checklist*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (row.get("group_id", ""), (row.get("printed_number") or "").strip(), (row.get("card_name") or "").strip())
                if key[0] and (key[1] or key[2]):
                    rows.setdefault(key, []).append(row)

    local_files: dict[tuple[str, str, str], set[str]] = {}
    for key, variants in rows.items():
        for row in variants:
            rel = (row.get("source_image_file") or "").strip()
            if rel and (ROOT / rel).is_file():
                local_files.setdefault(key, set()).add(rel)

    linked_files: dict[tuple[str, str, str], set[str]] = {}
    linked_manifest_path = REVIEW / "source-linked-image-download-audit.json"
    if linked_manifest_path.exists():
        linked_manifest = json.loads(linked_manifest_path.read_text())
        for record in linked_manifest.get("records", []):
            if record.get("status") != "downloaded":
                continue
            for association, image_file in zip(record.get("associations", []), record.get("files", [])):
                key = (association.get("group_id", ""), association.get("printed_number", ""), association.get("card_name", ""))
                if key in rows and Path(image_file).is_file():
                    linked_files.setdefault(key, set()).add(image_file)

    tcgdex_files: dict[tuple[str, str, str], set[str]] = {}
    tcgdex_manifest_path = REVIEW / "tcgdex-high-image-acquisition-audit-20261030.json"
    if tcgdex_manifest_path.exists():
        tcgdex_manifest = json.loads(tcgdex_manifest_path.read_text())
        for record in tcgdex_manifest.get("records", []):
            if record.get("status") != "downloaded":
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("card_name", ""))
            if key in rows and Path(record.get("file", "")).is_file():
                tcgdex_files.setdefault(key, set()).add(record["file"])

    pooka_files: dict[tuple[str, str, str], set[str]] = {}
    pooka_manifest_paths = [
        REVIEW / "pooka-pcg-promos-image-acquisition-20261030.json",
        REVIEW / "pooka-vs-image-acquisition-20261030.json",
        REVIEW / "pooka-xy-promos-image-acquisition-20261030.json",
        REVIEW / "pooka-s-p-promos-image-acquisition-20261030.json",
        REVIEW / "pooka-misc-promos-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-1140-moonlit-pursuit-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-522-ultra-force-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-641-mmb-power-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-644-mmb-speed-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-881-moonlit-pursuit-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-165-tcg-classic-blastoise-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-168-tcg-classic-charizard-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-171-tcg-classic-venusaur-image-acquisition-20261030.json",
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            1044, 1046, 1063, 1065, 1083, 1148, 1150,
        )],
        REVIEW / "pooka-ja-ref-897-space-time-creation-image-acquisition-20261030.json",
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            519, 758, 671, 1108, 612, 647, 1042, 1071, 1086,
        )],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            772, 1070, 1081, 1084, 1116, 1118, 1120, 1122, 1152, 615, 659, 683, 1021, 674, 967,
        )],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            1099, 1102, 1105, 1156, 710, 1153,
        )],
        REVIEW / "pooka-ja-ref-712-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-703-recheck-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-430-recheck-image-acquisition-20261030.json",
        REVIEW / "pooka-ja-ref-435-number-only-image-acquisition-20261030.json",
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            957, 951, 953, 955, 959, 961, 941, 824, 826, 828, 812, 808, 1155,
        )],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (927, 1112)],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (626, 1139)],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (298, 557, 581, 804)],
        *[REVIEW / f"pooka-ja-ref-{group}-image-acquisition-20261030.json" for group in (
            894, 892, 896, 886, 830, 856, 864, 816, 818, 836,
            858, 872, 1007, 1005, 997, 1001, 987, 1015, 1018, 706, 790, 794,
        )],
    ]
    pooka_manifests = [json.loads(path.read_text()) for path in pooka_manifest_paths if path.exists()]
    for pooka_manifest in pooka_manifests:
        for record in pooka_manifest.get("records", []):
            if record.get("status") == "failed" or not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                pooka_files.setdefault(key, set()).add(record["image_file"])

    pokedatavault_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("pokedatavault-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                pokedatavault_files.setdefault(key, set()).add(record["image_file"])

    tcgstats_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("tcgstats-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                tcgstats_files.setdefault(key, set()).add(record["image_file"])

    pokemon_tcg_io_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("pokemon-tcg-io-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                pokemon_tcg_io_files.setdefault(key, set()).add(record["image_file"])

    binderboss_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("binderboss-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                binderboss_files.setdefault(key, set()).add(record["image_file"])

    supercartas_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("supercartas-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                supercartas_files.setdefault(key, set()).add(record["image_file"])

    tcgcollector_files: dict[tuple[str, str, str], set[str]] = {}
    for path in REVIEW.glob("tcgcollector-*-image-acquisition-20261030.json"):
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                tcgcollector_files.setdefault(key, set()).add(record["image_file"])

    alternate_source_files: dict[tuple[str, str, str], set[str]] = {}
    alternate_source_manifests = sorted(REVIEW.glob("alternate-source-*-image-acquisition-*.json"))
    for path in alternate_source_manifests:
        manifest = json.loads(path.read_text())
        for record in manifest.get("records", []):
            if not record.get("checklist_match"):
                continue
            key = (record.get("group_id", ""), record.get("printed_number", ""), record.get("checklist_card_name", ""))
            if key in rows and Path(record.get("image_file", "")).is_file():
                alternate_source_files.setdefault(key, set()).add(record["image_file"])

    official_files: dict[tuple[str, str, str], set[str]] = {}
    index_path = REVIEW / "official-image-source-audit-index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"audits": []}
    for summary in index.get("audits", []):
        audit_path = REVIEW / summary["file"]
        if not audit_path.is_file():
            continue
        audit = json.loads(audit_path.read_text())
        group_id = audit.get("group_id", summary.get("group_id", ""))
        for record in audit.get("records", []):
            if not record.get("checklist_match"):
                continue
            official_number = record.get("printed_number", "")
            card_name = record.get("checklist_card_name", "")
            for key in rows:
                if key[0] == group_id and key[2] == card_name and number_matches(key[1], official_number):
                    path = record.get("image_file", "")
                    if path and Path(path).is_file():
                        official_files.setdefault(key, set()).add(path)

    supplement_path = REVIEW / "official-image-number-match-supplement-20261030.json"
    if supplement_path.exists():
        supplement = json.loads(supplement_path.read_text())
        for record in supplement.get("records", []):
            if not record.get("checklist_match") or not record.get("image_file"):
                continue
            for match in record.get("checklist_matches", []):
                key = (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
                if key in rows and Path(record["image_file"]).is_file():
                    official_files.setdefault(key, set()).add(record["image_file"])

    promo_supplement_path = REVIEW / "official-image-number-match-promos-supplement-20261030.json"
    if promo_supplement_path.exists():
        promo_supplement = json.loads(promo_supplement_path.read_text())
        for group_audit in promo_supplement.get("groups", []):
            for record in group_audit.get("records", []):
                if not record.get("checklist_match") or not record.get("image_file"):
                    continue
                for match in record.get("checklist_matches", []):
                    key = (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
                    if key in rows and Path(record["image_file"]).is_file():
                        official_files.setdefault(key, set()).add(record["image_file"])

    legacy_supplement_path = REVIEW / "official-image-number-match-legacy-expansions-20261030.json"
    if legacy_supplement_path.exists():
        legacy_supplement = json.loads(legacy_supplement_path.read_text())
        for group_audit in legacy_supplement.get("groups", []):
            for record in group_audit.get("records", []):
                if not record.get("checklist_match") or not record.get("image_file"):
                    continue
                for match in record.get("checklist_matches", []):
                    key = (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
                    if key in rows and Path(record["image_file"]).is_file():
                        official_files.setdefault(key, set()).add(record["image_file"])

    wcp_supplement_path = REVIEW / "official-image-number-match-wcp-supplement-20261030.json"
    if wcp_supplement_path.exists():
        wcp_supplement = json.loads(wcp_supplement_path.read_text())
        for record in wcp_supplement.get("records", []):
            if not record.get("checklist_match") or not record.get("image_file"):
                continue
            for match in record.get("checklist_matches", []):
                key = (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
                if key in rows and Path(record["image_file"]).is_file():
                    official_files.setdefault(key, set()).add(record["image_file"])

    expansion_supplement_path = REVIEW / "official-image-number-match-expansion-supplement-20261030.json"
    if expansion_supplement_path.exists():
        expansion_supplement = json.loads(expansion_supplement_path.read_text())
        for group_audit in expansion_supplement.get("groups", []):
            for record in group_audit.get("records", []):
                if not record.get("checklist_match") or not record.get("image_file"):
                    continue
                for match in record.get("checklist_matches", []):
                    key = (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
                    if key in rows and Path(record["image_file"]).is_file():
                        official_files.setdefault(key, set()).add(record["image_file"])

    output_rows = []
    coverage_sources = Counter()
    for key in sorted(rows):
        variants = rows[key]
        local = sorted(local_files.get(key, set()))
        official = sorted(official_files.get(key, set()))
        linked = sorted(linked_files.get(key, set()))
        tcgdex = sorted(tcgdex_files.get(key, set()))
        pooka = sorted(pooka_files.get(key, set()))
        pokedatavault = sorted(pokedatavault_files.get(key, set()))
        sources = []
        if local:
            sources.append("existing_reference_scan")
        if official:
            sources.append("official_pokemon_card_site_number_match")
        if linked:
            sources.append("checklist_linked_source")
        if tcgdex:
            sources.append("tcgdex_high_resolution_asset")
        if pooka:
            sources.append("pooka_japanese_set_image_number_match")
        if pokedatavault:
            sources.append("pokedatavault_exact_set_number_name_match")
        tcgstats = sorted(tcgstats_files.get(key, set()))
        if tcgstats:
            sources.append("tcgstats_exact_set_number_name_match")
        pokemon_tcg_io = sorted(pokemon_tcg_io_files.get(key, set()))
        if pokemon_tcg_io:
            sources.append("pokemon_tcg_io_exact_set_number_name_match")
        binderboss = sorted(binderboss_files.get(key, set()))
        if binderboss:
            sources.append("binderboss_exact_japanese_set_unique_name_match")
        supercartas = sorted(supercartas_files.get(key, set()))
        if supercartas:
            sources.append("supercartas_exact_japanese_set_number_match")
        tcgcollector = sorted(tcgcollector_files.get(key, set()))
        if tcgcollector:
            sources.append("tcgcollector_exact_set_number_name_match")
        alternate_source = sorted(alternate_source_files.get(key, set()))
        if alternate_source:
            sources.append("alternate_source_exact_card_variant_match")
        state = "image_file_acquired" if sources else "missing_image_file"
        association_status = (
            "missing" if not sources else
            "review_multiple_official_candidates" if len(official) > 1 else
            "associated"
        )
        for source in sources:
            coverage_sources[source] += 1
        first = variants[0]
        output_rows.append({
            "group_id": key[0],
            "printed_number": key[1],
            "card_name": key[2],
            "japanese_name": first.get("japanese_name", ""),
            "image_status": state,
            "image_association_status": association_status,
            "image_sources": ";".join(sources),
            "local_reference_files": ";".join(local),
            "official_source_files": ";".join(official),
            "linked_source_files": ";".join(linked),
            "tcgdex_high_resolution_files": ";".join(tcgdex),
            "pooka_source_files": ";".join(pooka),
            "pokedatavault_source_files": ";".join(pokedatavault),
            "tcgstats_source_files": ";".join(tcgstats),
            "pokemon_tcg_io_source_files": ";".join(pokemon_tcg_io),
            "binderboss_source_files": ";".join(binderboss),
            "supercartas_source_files": ";".join(supercartas),
            "tcgcollector_source_files": ";".join(tcgcollector),
            "alternate_source_files": ";".join(alternate_source),
            "source_image_status": ";".join(sorted({(r.get("source_image_status") or "").strip() for r in variants if (r.get("source_image_status") or "").strip()})),
            "source_image_url": ";".join(sorted({(r.get("source_image_url") or "").strip() for r in variants if (r.get("source_image_url") or "").strip()})),
            "image_association_basis": ";".join(sorted({(r.get("image_association_basis") or "").strip() for r in variants if (r.get("image_association_basis") or "").strip()})),
            "candidate_status": ";".join(sorted({(r.get("candidate_status") or "").strip() for r in variants if (r.get("candidate_status") or "").strip()})),
            "cardmarket_candidate_count": ";".join(sorted({(r.get("cardmarket_candidate_count") or "").strip() for r in variants if (r.get("cardmarket_candidate_count") or "").strip()})),
            "cardmarket_candidate_names": ";".join(sorted({(r.get("cardmarket_candidate_names") or "").strip() for r in variants if (r.get("cardmarket_candidate_names") or "").strip()})),
            "cardmarket_candidate_urls": ";".join(sorted({(r.get("cardmarket_candidate_urls") or "").strip() for r in variants if (r.get("cardmarket_candidate_urls") or "").strip()})),
        })

    fields = list(output_rows[0]) if output_rows else []
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    missing = [row for row in output_rows if row["image_status"] == "missing_image_file"]
    missing_by_group = Counter(row["group_id"] for row in missing)
    linked = json.loads(linked_manifest_path.read_text()) if linked_manifest_path.exists() else {"records": []}
    tcgdex = json.loads(tcgdex_manifest_path.read_text()) if tcgdex_manifest_path.exists() else {"records": []}
    pooka = [json.loads(path.read_text()) for path in pooka_manifest_paths if path.exists()]
    pokedatavault = [json.loads(path.read_text()) for path in REVIEW.glob("pokedatavault-*-image-acquisition-20261030.json")]
    tcgstats = [json.loads(path.read_text()) for path in REVIEW.glob("tcgstats-*-image-acquisition-20261030.json")]
    pokemon_tcg_io = [json.loads(path.read_text()) for path in REVIEW.glob("pokemon-tcg-io-*-image-acquisition-20261030.json")]
    binderboss = [json.loads(path.read_text()) for path in REVIEW.glob("binderboss-*-image-acquisition-20261030.json")]
    supercartas = [json.loads(path.read_text()) for path in REVIEW.glob("supercartas-*-image-acquisition-20261030.json")]
    tcgcollector = [json.loads(path.read_text()) for path in REVIEW.glob("tcgcollector-*-image-acquisition-20261030.json")]
    alternate_sources = [json.loads(path.read_text()) for path in REVIEW.glob("alternate-source-*-image-acquisition-20261030.json")]
    promo_supplement = json.loads(promo_supplement_path.read_text()) if promo_supplement_path.exists() else {"groups": []}
    legacy_supplement = json.loads(legacy_supplement_path.read_text()) if legacy_supplement_path.exists() else {"groups": []}
    wcp_supplement = json.loads(wcp_supplement_path.read_text()) if wcp_supplement_path.exists() else {"records": []}
    expansion_supplement = json.loads(expansion_supplement_path.read_text()) if expansion_supplement_path.exists() else {"groups": []}
    promo_matched_targets = {
        (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
        for group_audit in promo_supplement.get("groups", [])
        for record in group_audit.get("records", []) if record.get("checklist_match")
        for match in record.get("checklist_matches", [])
    }
    summary = {
        "generated_at": "2026-10-30",
        "checklist_unique_rows": len(output_rows),
        "rows_with_acquired_image_file": len(output_rows) - len(missing),
        "rows_still_missing_image_file": len(missing),
        "groups_with_missing_image_files": len(missing_by_group),
        "coverage_counts_by_source_nonexclusive": dict(coverage_sources),
        "official_groups_audited": len(index.get("audits", [])),
        "official_image_files_downloaded": sum(item.get("asset_files_copied", 0) for item in index.get("audits", [])),
        "official_checklist_number_matches": sum(item.get("matched_checklist_rows", 0) for item in index.get("audits", [])),
        "official_supplement_files_downloaded": sum(bool(item.get("asset_copied")) for item in supplement.get("records", [])) if supplement_path.exists() else 0,
        "official_supplement_checklist_matches": sum(bool(item.get("checklist_match")) for item in supplement.get("records", [])) if supplement_path.exists() else 0,
        "official_promo_supplement_files_downloaded": sum(group.get("downloaded_images", 0) for group in promo_supplement.get("groups", [])),
        "official_promo_supplement_unique_checklist_rows_matched": len(promo_matched_targets),
        "official_legacy_supplement_unique_checklist_rows_matched": len({
            (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
            for group_audit in legacy_supplement.get("groups", [])
            for record in group_audit.get("records", []) if record.get("checklist_match")
            for match in record.get("checklist_matches", [])
        }),
        "official_wcp_supplement_images_downloaded": sum(bool(record.get("asset_copied")) for record in wcp_supplement.get("records", [])),
        "official_wcp_supplement_checklist_rows_matched": sum(bool(record.get("checklist_match")) for record in wcp_supplement.get("records", [])),
        "official_expansion_supplement_images_downloaded": sum(group.get("downloaded_images", 0) for group in expansion_supplement.get("groups", [])),
        "official_expansion_supplement_unique_checklist_rows_matched": len({
            (match.get("group_id", ""), match.get("printed_number", ""), match.get("card_name", ""))
            for group_audit in expansion_supplement.get("groups", [])
            for record in group_audit.get("records", []) if record.get("checklist_match")
            for match in record.get("checklist_matches", [])
        }),
        "rows_with_multiple_official_candidates": sum(row["image_association_status"] == "review_multiple_official_candidates" for row in output_rows),
        "linked_source_urls_downloaded": sum(item.get("status") == "downloaded" for item in linked.get("records", [])),
        "linked_source_urls_failed": sum(item.get("status") == "failed" for item in linked.get("records", [])),
        "linked_source_associations_downloaded": sum(item.get("association_count", 0) for item in linked.get("records", []) if item.get("status") == "downloaded"),
        "tcgdex_high_resolution_images_downloaded": sum(item.get("status") == "downloaded" for item in tcgdex.get("records", [])),
        "tcgdex_high_resolution_candidates_not_found": sum(item.get("status") == "not_found" for item in tcgdex.get("records", [])),
        "pooka_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in pooka for record in manifest.get("records", [])),
        "pokedatavault_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in pokedatavault for record in manifest.get("records", [])),
        "tcgstats_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in tcgstats for record in manifest.get("records", [])),
        "pokemon_tcg_io_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in pokemon_tcg_io for record in manifest.get("records", [])),
        "binderboss_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in binderboss for record in manifest.get("records", [])),
        "supercartas_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in supercartas for record in manifest.get("records", [])),
        "tcgcollector_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in tcgcollector for record in manifest.get("records", [])),
        "alternate_source_images_downloaded": sum(record.get("status") != "failed" and record.get("checklist_match") for manifest in alternate_sources for record in manifest.get("records", [])),
        "linked_source_failures_by_host_and_status": {
            f"{host} | {status}": count
            for (host, status), count in Counter(
                (item.get("source_url", "").split("/")[2], (item.get("error") or "").split(":", 1)[0])
                for item in linked.get("records", []) if item.get("status") == "failed"
            ).items()
        },
        "missing_by_group": dict(sorted(missing_by_group.items())),
        "detail": OUT_CSV.name,
        "notes": [
            "A checklist row is covered only when an image file exists and has a supported association from an existing reference scan, official audit, checklist-linked URL, TCGdex, Pooka, PokeDataVault, TCG Stats, or PokémonTCG.io exact-set source.",
            "This is image-file coverage; it does not certify final crop, vector quality, or production matching approval.",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("checklist_unique_rows", "rows_with_acquired_image_file", "rows_still_missing_image_file", "groups_with_missing_image_files", "official_image_files_downloaded", "official_checklist_number_matches", "linked_source_urls_downloaded", "linked_source_urls_failed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
