# Card index shipping: review fixes (plan, 2026-10-28)

Review of the owner's local changes for `docs/phone-index-shipping-plan-20261028.md`:
- **scanapp** (uncommitted on main): `api/app/routes/card_index.py`, `api/scripts/on_phone_index/export_index.py` + README, `check_compressed_index.py`, `client_diagnostics.py`, `config.py`, `main.py`, tests.
- **PokeSingle** (uncommitted on main): `lib/data/card_index_download.dart`, `on_phone_match_log.dart`, `lib/main.dart`, `pubspec.yaml` (adds `background_downloader`), tests.

What already holds: the server API suite passes (1114 passed, 10 skipped); the app's tests pass except the 2 known failures; the app and server agree on the manifest (relative `card-index/files/<version>/<name>` urls, 64-hex content-derived version, the same four files, `model_id` 2ddf6ec79e37). Safety is good on both sides: the manifest refuses a candidate that doesn't match the loaded snapshot, file names and versions are allow-listed (no path traversal), every file is checked by size and sha256 before use, the swap is one rename, and a working index is never removed first. Both switches default off (`CARD_INDEX_PUBLISH`, `CARD_INDEX_DOWNLOAD`).

## Fixes, in order

### 1. App: a failed check waits a whole day (`card_index_download.dart`, `_start`)
The daily throttle time is saved **before** the manifest request, so an offline start or a server 503 blocks the next check for 24 h.
**Fix:** save the time only after a manifest answer (200, or 404 = not published); after a failure retry on the next start, at most once an hour.
**Test:** a failed manifest request leaves no throttle; a success sets it; a second start within a day does nothing.

### 2. App: old versions are never deleted (disk grows ~34 MB per catalogue update)
Superseded `card_index_download/<env>/<version>/` folders, and half-downloaded versions replaced by a newer manifest, stay forever.
**Fix:** after a successful swap, delete every version folder except the new ACTIVE one (and the one the running process has loaded, if different — delete that on the next start). On a new pending manifest, cancel the old pending tasks and delete their folder.
**Test:** after two swaps only the newest folder remains; a superseded pending folder is removed.

### 3. Server: every request re-hashes ~34 MB (`routes/card_index.py`, `_candidate`)
The manifest (`no-cache`, so every app's daily check reaches the server) and every file request hash all four files, about 34 MB of reading and SHA-256 each time.
**Fix:** check a version folder once and keep the result in memory, keyed by version plus each file's size and modification time; re-check only when those change.
**Test:** a second manifest call doesn't hash again (patch `sha256_file` and count calls); a tampered file (size or mtime change) is still refused.

### 4. App: the download flow has no tests
The 4 tests cover the manifest parser and the folder check, but not the flow: not published (404), same version, wrong model, new version downloaded → verified → swapped, a checksum mismatch keeps the old index, recovery of a pending download after a restart, and the switch off.
**Fix:** put `FileDownloader` behind a small interface so tests can use a fake, and add those cases.

### 5. App: a damaged active version is never repaired
If `ACTIVE` names a version whose folder is missing or damaged, the check sees the same version and reports "current", so it never re-downloads (the loader quietly falls back to the old hand-copied folder or to no index).
**Fix:** before "current", check the active folder's file sizes against the manifest (cheap); if they don't match, download again.
**Test:** a missing file in the active folder leads to a new download.

### 6. Deployment
- Add `CARD_INDEX_PUBLISH: ${CARD_INDEX_PUBLISH:-false}` (and `CARD_INDEX_PUBLISH_DIR`) to `compose.dokploy.yaml` and `compose.dokploy.production.yaml`, as for every other switch.
- Publishing is manual by design (export a vetted candidate, copy it to `/data/phone-index/<version>/`, write `ACTIVE`). Every catalogue change makes the manifest answer 503 until a new candidate is placed, so phones keep their old index (safe). Write the operator steps in the README, and note it in the shipping plan (step 1 there said automatic).

### 7. Small
- `flutter analyze`: 1 warning (unused `../core/config.dart` import) and 6 style infos in `card_index_download.dart`.
- `check_compressed_index.py` no longer re-normalises the reference vectors; say so in its docstring, since earlier gate numbers used normalised vectors.
- `background_downloader` is a new native plugin on both phones: run `flutter build ios --profile` and `flutter build appbundle --profile` once before merging.

## Then

1. Commit each repo's changes with the fixes as a draft PR (scanapp, PokeSingle).
2. Test as in the shipping plan's step 4: on staging, export and place a candidate, turn `CARD_INDEX_PUBLISH` on; build the app with `CARD_INDEX_DOWNLOAD=true`; on the A55 and the iPhone 15 remove the hand-copied files, let the app download, then one 16-photo round each. Gate: download finishes and checksums hold on both phones, provisional cards as before, 0 overturned, 0 wrong cards.
