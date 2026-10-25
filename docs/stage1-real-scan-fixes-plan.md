# Plan: stage 1 fixes from the first real iPhone scans (build 1.0.0+151)

**Repo:** ScanApp (`~/WebstormProjects/scanapp`). Start a new branch from latest `origin/main`.
**Rules:**
- **Every behaviour change goes behind a flag that's off in code** and on in staging only (`compose.dokploy.yaml`). Don't change production.
- **The full API suite must pass.**
- **Replay the 157-photo panel with the simulated stage 0 fields** (PR #65 kit). Stage 1/1b must stay at **0 wrong**, with every other answer unchanged.
- **Open a PR, don't merge it.**
- **Staging is read-only** for this work. Never copy credentials or container environments.

## What happened on staging

Build **1.0.0+151** works end to end: the Core ML model downloaded (`embedding.model requested → downloading → ready`) and **6 of 7 scans sent `client_embedding`** (`embedding.sent bytes=768`). Stage 1 / 1b answered **none**. The scans are on staging: results.sqlite, `stage0` and `scan_summary` log lines, all from 2026-10-22.

| Scan | Phone read | Full pipeline answer | Stage 1 reason | Root cause |
|---|---|---|---|---|
| c5687ed0 | Ancient Booster Energy 159/182 | en:sv04-159 | ambiguous_text (margin 0.0022) | Also matches **Prize Pack reprint** `en:PPS5-PAR-159` (`printed_collector_number` 159/182, same artwork) |
| 70585dbe | Pikachu 35/108 | en:xy12-35 | ambiguous_text (0.0024) | 3 cards: `en:xy12-35` (Evolutions), `en:30th-035`, `en:np-35`. **None has `printed_collector_number`**, so `/108` can't decide |
| b438c6f1 | Charmeleon 24/102 | en:base1-24 | ambiguous_text (0.0225) | `base1-24` **and** `en:base1-24` (duplicate ID, not collapsed) **plus** `en:swsh4-24`. No printed totals |
| 982a6a0d | Comfey 077/128 | en:30th-077 | visual_contradiction (0.0641) | The text named exactly `en:30th-077`, but the phone vector's top was another card ahead by ≥ 0.05. **Which card isn't logged** |
| b3ac26f2 | Toxel 078 | en:mep-078 | no_unique_text | A promo number **without a total** isn't looked up. `en:mep-078` is unique for Toxel + 078 |
| df96aa6a | "Ancient", "0" | zh-tw:SV8a-099 | no_unique_text | A bad phone read (no fix here) |
| a19b066e | manual shutter | en:sv04-123 | no_embedding | Manual-photo detection found no corners (an app issue, out of scope here) |

## Fixes

### 1. Use the set's printed total when a card has none

Many catalogue cards have an empty `printed_collector_number` (e.g. `en:xy12-35`, `en:sv04-159`, `en:base1-24`). The server already stores each set's printed total from TCGdex (`api/app/set_totals.py`; `rank.py` reads `item["set_total"]`).
- In the stage 1 gate's catalogue load (`api/app/recognition/stage1_gate.py` `load_catalogue`), **attach `set_total` per card** from that table.
- Make `number_ok` / `lookup` compare the phone's denominator with `printed_collector_number`, **or else** with the set total. A known, different total means **no match** (`35/108` must not match `en:30th-035` if 30th's total isn't 108).
- **Expected:** Pikachu 35/108 → only `en:xy12-35`. Charmeleon 24/102 → only Base Set (after fix 2).

### 2. Collapse duplicate IDs reliably

`base1-24` and `en:base1-24` weren't collapsed, because `collapse_hits` requires **every** listed field to match, and one differs, likely `printed_collector_number` or `set_id` formatting.
- **Collapse** `X` / `en:X` when name, set ID (normalised), collector number (leading zeros removed) and language match. **Prefer `en:X`.**
- **Report** which field differed for `base1-24`, and how many of the 561 pairs (`docs/experiments/stage0-duplicate-pairs-20261021.csv`) the old rule missed.

### 3. Same-artwork reprints (Prize Pack, stamped, promo reprints)

When the text matches a **base card and its reprint** with the same name and number, and either their reference vectors are near-identical (cosine ≥ about 0.95; report the value seen for `en:sv04-159` vs `en:PPS5-PAR-159`) or the catalogue marks one as a reprint of the other:
- treat them as **one card with a printing choice**
- answer the **base set card** (non-promo, non-Prize Pack) at stage 1/1b, with the printing marked **"choose printing"** (like `printing_ambiguous`), so the user confirms which one
- **never** pick the reprint automatically

Report how many panel photos this affects.

### 4. Promo numbers without a total

A phone number like `078` (no `/total`), or a promo code (`SWSH020`, `SVP 053`, `SM35`…), plus a name: look it up **within promo sets** (black star promo, MEP, prize pack) by name and collector number (leading zeros removed). Accept only if exactly one card matches (after fixes 2–3).
- **Expected:** Toxel 078 → `en:mep-078`.

### 5. Log what the gate saw (no answer change)

Extend the `stage0` line (`api/app/stage0.py`) with:
- `vector_top` (card ID) and `vector_top_score`
- `text_candidates` (up to 5 card IDs, after the fixes) and their count
- for `visual_contradiction`: the leading card's ID and the gap

So for a scan like Comfey (982a6a0d) we can see whether the phone's vector is wrong or the catalogue has a look-alike. **Investigate Comfey now if possible:** replay that scan's recorded fields if they exist, or explain why the vector disagreed.

### 6. Replay and staging check

- **Unit tests** for fixes 1–4, using the exact catalogue rows above as fixtures.
- **Panel replay** (157 photos, simulated stage 0 fields): stage 1/1b still **0 wrong**. Report the new answer count against 53.
- **A small "real scans" fixture** from these 7 staging scans (their recorded phone text, corners, and the embedding if it can be recovered from logs; otherwise skip the vector cases). Show which of them now answer at stage 1/1b and with which card. **Expected:** c5687ed0 (base card plus a printing choice), 70585dbe, b438c6f1 and b3ac26f2 answer, with the correct cards from the table.
- Turn on any new flags in `compose.dokploy.yaml` only.

## Done when

- PR open (not merged), with flags off in code and on in staging.
- Tests pass, the panel replay is at 0 wrong, and the real-scan fixture results are in the PR description.
- A short note in `docs/experiments/` (`stage1-real-scans-<date>.md`) with the table above, before and after.
