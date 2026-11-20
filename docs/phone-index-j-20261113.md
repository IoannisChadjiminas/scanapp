# Phone index for catalogue J, published on staging (2026-11-13)

| Item | Value |
|---|---|
| Catalogue | `PS-CATALOGUE-EN-JA-REC42-J-20261113` (62,784 cards, 51,817 indexed vectors) |
| Phone index version | `26483c87a9d5586705378053d4488d36cff545374b69481d1adc05d8637863ca` (float16, 39.8 MB + ids, meta, version: 41 MB) |
| Previous version (rollback) | `63a3707111add1d751949858766dd479d60d7f248367a389173f110d3842bbdf` (JAREC15), kept in `/data/phone-index/` |
| Rollback record | `/etc/scanapp-staging/catalogue-rollback/phone-index-j-20261113/ACTIVE.before` |
| Published | `/data/phone-index/<version>/`, then `ACTIVE.next` renamed to `ACTIVE` |
| Check after publish | manifest 200 inside the container and from outside; all four files download with the manifest's size and sha256 |

Built as `api/scripts/on_phone_index/README.md` says: `export_cloud_snapshot.py` in a separate, memory-capped container of the
API image on staging (scratch data folder, data volume read-only), then `export_index.py` against that export, the operational
`catalog.sqlite` for set totals and `dinov2_small.onnx` (`2ddf6ec79e37…`). The same files serve Android and iPhone.

Between the J switch and this publish the manifest answered 503 (the JAREC15 index no longer matched the catalogue), so phones
kept the JAREC15 index and had none of the second-batch cards.

## Parity check (`check_compressed_index.py`)

Only the frozen A55 panel half could be run (114 photos with a gallery crop): the stored Android uploads it also needs are no longer
on this Mac or on staging. The same check was run on the JAREC15 index for comparison.

| Index | Same vector decision | Same first answer | New wrong passes (of 570) | Top-20 exact order | Top-20 same cards |
|---|---|---|---|---|---|
| JAREC15 (on phones before) | 114/114 | 114/114 | 0 | 83.3% | 111/114 (one card at the edge) |
| J (published) | 114/114 | 114/114 | 0 | 84.2% | 112/114 (one card at the edge) |

The script's gate (top-20 identical order on 99% of photos) is **not met** by either index: float16 rounding reorders near-equal
cards lower in the list. The phone's provisional rule uses the top 20 as a set (name and number must name exactly one card in it);
as a set it differs on 2 photos, by one card at position 20, and the right card is never lost. Published on the owner's decision
(2026-11-13) on that basis, as the same behaviour as the index phones already had.

## Not verified
The device round of the shipping plan (A55 and iPhone 15: download, checksum, swap, one 16-photo round each). The Android-upload
half of the parity check. Production (its compose keeps `CARD_INDEX_PUBLISH` off).

## Going back
On the staging host: write `63a3707111add1d751949858766dd479d60d7f248367a389173f110d3842bbdf` to `/data/phone-index/ACTIVE.next`
and rename it to `ACTIVE`. Note that the JAREC15 index does not match catalogue J, so the manifest would answer 503 again.
