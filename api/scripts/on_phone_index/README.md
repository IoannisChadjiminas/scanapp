# Offline phone index candidate

This exporter is an offline first step, not a publishing or deployment mechanism.
For a cloud-backed server, first run `api/scripts/export_cloud_snapshot.py` in the
server environment to produce the validated snapshot and its matching catalogue.
Use the corresponding server's operational SQLite database for `set_totals`;
the cloud catalogue export does not include those totals. Keep all inputs and
outputs outside Git. A catalogue version does not by itself prove that an
arbitrary SQLite file belongs to the snapshot: the operator must obtain the
paired files together.

Run `export_index.py --snapshot-dir <export>/vectors/pad --catalogue
<export>/catalog.sqlite --totals-db <server-operational-sqlite> --model
<server-dinov2-small.onnx> --out <candidate-root>`. It verifies the snapshot
file hashes and phone model, writes a temporary candidate, then renames it to a
content-derived version directory. The version file hashes the other three
files; a future publication manifest must hash all four, including the version
file itself.

The meta file has eight columns: the six the app reads (`id, name, number,
printed_number, set_total, language`) plus `promo_code` and `row_kind`. A fraction
printed on the card sets `set_total`; Japanese promo rows carry their code
(`SV-P`) and no total. The build fails on rows the checks cannot account for:
pass `--allow-exceptions export_exceptions.json` (the known rows of catalogue K)
and `--report <file>` to see the counts. `--exclude digital,language,duplicate`
cuts a subset index (`app/phone_index_subset.py`) for offline checks only: the server's
manifest route does not serve one (rows must equal the snapshot, or extend a published index). See `docs/phone-index-review-20261114.md`.

Run `check_compressed_index.py` against the *same* exported vectors, catalogue,
and model using `--index-dir`, `--catalog`, `--model`, and `--phone-index`, along
with the required scan corpus arguments. The comparison verifies that the
stored float16 candidate is the conversion of those vectors and compares ordered
top-20 results and the existing stage-1 approximation. The script's result is
an offline research check, not proof of a full production gate: it does not
replay all live retrieval filters, stage-1 components, or actual phone searches.
Complete the plan's live-snapshot and device gates before enabling shipping.

## Read-only route (default off)

`CARD_INDEX_PUBLISH=true` exposes `/api/v1/card-index/manifest` and immutable
versioned file URLs from `CARD_INDEX_PUBLISH_DIR` (default `/data/phone-index`).
The operator must place a vetted version directory there and put its 64-character
version in `ACTIVE`. The manifest returns 503 unless that candidate matches the
loaded recognition snapshot's catalogue, model, vector and id hashes, row count,
and dimension. It also checks the candidate's file sizes and hashes. File routes
support byte ranges, ETags, and immutable caching. Previously published version
directories must remain present for clients completing an older download.

An index may also extend a published one: its version file has `extends` with the base
`version` and `rows`. The manifest serves it only if the base version is still in the publish
directory and matches the loaded snapshot as above, and the index's ids and float16 files begin
with the base's files byte for byte, followed by the added rows. The manifest's `rows` is the
index's own row count (the float16 file is `rows * dims * 2` bytes). An index may carry a fifth
file, `card_index.prints.tsv` (printings with the same picture as an index row, without a
vector), listed in its version file; the manifest then lists it after the four files at
`card-index/files/<version>/card_index.prints.tsv`. A version without it has exactly the four
files, as before. Keep the base version's directory while an extension of it is active.

### Another picture model's index (20 November 2026)

Apps on run 4, the card-tuned picture model (model ID `38ce95cc1928`), ask
for `/api/v1/card-index/manifest?model=38ce95cc1928`. A request without
`model`, or with the snapshot's own model, is served as before. Another
model's index is served from `ACTIVE.<model>` (the version, as in
`ACTIVE`) when its version file has that `model_id`, a `variant_of` naming
the version in `ACTIVE`, and the same catalogue, rows and dimensions. All
its files except the vectors and the version file must be byte for byte
the active index's. A model with no `ACTIVE.<model>` gets 404 (no index
for it). A mismatch gets 503, and phones keep the index they have.

When `ACTIVE` moves to a new catalogue, run 4's index stops being served
until it is rebuilt for the new rows: run 4's vectors for every row, in
the new index's order, from the run 4 ONNX model (`dinov2_small_r4.onnx`,
sha256 `38ce95cc…`), then the four other files copied from the new
active index.

This route does **not** automatically export or promote snapshots. The offline
research check and physical-device gates remain required before enabling it.

### Operator sequence for each catalogue release

1. Obtain the current server's validated cloud snapshot export, paired catalogue,
   operational set totals and model. Run the exporter above into a scratch folder.
2. Run the parity comparison against the exact exported candidate and review the
   gate report. Do not select a candidate with a failing or missing gate.
3. Copy the entire vetted `<version>/` directory to the API data volume at
   `/data/phone-index/<version>/` (or `CARD_INDEX_PUBLISH_DIR`). Copy to a temporary
   directory first, then rename it after the copy is complete. Published version
   directories are immutable: never overwrite their files.
4. Write the 64-character version to `ACTIVE.next`, flush it, then rename
   `ACTIVE.next` to `ACTIVE` in that same directory. The manifest validates it
   against the loaded recognition snapshot. Keep older published directories for
   phones still finishing downloads; changing ACTIVE does not invalidate their URLs.
5. Staging defaults `CARD_INDEX_PUBLISH` to true (`compose.dokploy.yaml`), so a
   staging redeploy with the merged code exposes the routes; they return 503 until
   a candidate is active. Production (`compose.dokploy.production.yaml` and
   `compose.prod.yaml`) keeps `CARD_INDEX_PUBLISH` false. Changing production is a
   separate owner decision. `CARD_INDEX_PUBLISH_DIR` defaults to `/data/phone-index`.
6. Check the manifest and a ranged file request, then run the shipping plan's
   physical-device download, replacement and 16-photo gates with
   `CARD_INDEX_DOWNLOAD=true`. Both platforms must pass before rollout.

A new catalogue deliberately makes the manifest return 503 until a new vetted
candidate is selected. Phones retain their compatible index and retry failed
manifest checks at most hourly, while valid 200/404 answers are checked daily.
Candidate hash verification is cached in the server process and invalidated by
file size, modification time, change time or inode changes.

### The phone's daily price file (21 November 2026)

After each import of Cardmarket's price file, the nightly price pass
(`refresh_all`) rebuilds `card_prices.tsv.gz` for the active index's ids and
printings (`app/phone_prices.py`): each card's Cardmarket trend in euro cents
(the `cardmarket_file` trend `best_prices` shows, empty when there is none),
its set name and image address. Phones download it to finish a scan with no
connection. It is served at `/api/v1/card-prices/manifest` and
`card-prices/files/<sha256>/card_prices.tsv.gz` from `CARD_PRICES_DIR`
(default `/data/phone-prices`) when `CARD_PRICES_PUBLISH` is on. A failed
build keeps the previous version active; the two versions before it are kept.
