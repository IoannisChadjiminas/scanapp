# Catalogue completion: plan and pending work (handoff for the Mac)

15 Oct 2026, 05:45 UTC. Run this from the scanapp checkout on the Mac:
`/Users/ioannischadjiminas/WebstormProjects/scanapp`.

## Where things stand

The English batch of 51 cards is half-written to PlanetScale. Nothing is visible to the app yet.

| Item | State |
| --- | --- |
| English gaps | 109 cases: 51 release-ready, 58 held |
| Overlay for the 51 | Built and inspected: existing 39,747 vectors byte-identical, 51 normal (non-holo, unstamped) cards |
| Staging files for the 51 | Copied and checksum-verified (images, feature folder `20261014-en109`, artwork `PS-CATALOGUE-EN-ENFIVE-20261014-EN109`) |
| PlanetScale write | 48 of 51 pad vectors inserted and verified; everything else not written |
| Candidate | `pokesingle_completion_20261014_enfivecmsetfix`, still inactive, `activation_allowed=false` |
| Staging | Still serving `ENFIVE-REBASE-20261014` |
| PR #44 (local candidate tooling) | Open draft, not merged. Not needed for the next steps |

Run folder: `data/catalogue-completion/20261004-01/batch-preparation-20261014/english-109-local-batch-v1/`
- `prepared-51-v2/publish-51.sql`: the original single statement (sha256 starts `56fe88cc`). Do NOT run it now, because it clashes with the 48 rows already written.
- `prepared-51-v2/chunks-v2/`: 40 retry-safe chunks. Chunks 01 to 08 are done. Resume at `09-pad-9.sql`.
- `staging-light-check-v1/`: `checkpoint.json`, `inspect-out.json`, `scan-list.json`, `CHANGE-SET.md`.
- `PROCESS-AND-PENDING.md` and `events.jsonl` in the run folder carry the history.

## Rules

- Scanner thresholds, ranking, grading, models and preprocessing stay unchanged.
- Delete nothing: no rows, files or rollback archives.
- Uncertain cards stay held; a plausible guess is not evidence.
- Staging is a test environment with no users. Ioannis approved PlanetScale writes and staging switches, with a one-step rollback ready before each switch.

## Step 1. Unblock the Mac session

Claude Code on the Mac refused the PlanetScale plugin's `planetscale_execute_write_query` tool and Bash partway through. Allow both for this project (answer the prompt, or add allow rules in the project's Claude Code settings).

## Step 2. Finish the English write (pick one)

**A. Plugin (no credentials):** run `chunks-v2/09-pad-9.sql` through the last chunk with the write tool, in order. Every chunk is idempotent, so a repeat is harmless. The last chunk is the guarded statement. It checks every new row's checksum and that the parent is unchanged, then sets the 51 card images, provenance rows, 3 manifests and import metadata. On any mismatch it writes nothing.

**B. Import role (faster):** put the import/admin URL in `~/keys/ps-import.env` as `PLANETSCALE_DATABASE_URL=…` and run the remaining chunks with `psql` or the `docker run … scanapp-api:local-amd64` one-liner from `CHANGE-SET.md`, pointed at each chunk file in order. Don't run `publish-51.sql`.

Then read back on the primary and expect:
- pad vectors 39,798 and square vectors 39,798
- artwork 13,754
- 51 cards with the new image paths

## Step 3. Switch staging and run the light check

1. Archive `/etc/scanapp-staging/catalogue-release.env` to `/etc/scanapp-staging/catalogue-rollback/en109-source51-20261014/`.
2. Point the release file at the CMSETFIX candidate import (values in `CHANGE-SET.md`) and recreate only the API.
3. Read `https://scan.pokesingle.com/api/v1/health` and confirm `ready=true` and the new `catalogue_import_id`.
4. Scan the 28 photos in `scan-list.json` with `api/scripts/run_scan_stream_panel.py`. They are the affected cards with real photos (latia-8, latia-9 and one more), 5 Latios-deck lookalikes, 10 trainer-kit siblings and the 10 regression photos.
5. On any miss, restore the archived release file, recreate the API, and confirm the old import ID by health read.

Known gap: there are no photos of main-set basic energies, and 28 of the 51 are visually identical kit energies. A main-set energy scan should now offer both printings; check this by hand if you have one of those cards.

## Step 4. English siblings and holds

- **Trainer-kit siblings (61) and Yellow A (6):** pair each with its identical main-set card. Example: HS Trainer Kit Poké Ball TK4G23 with HeartGold SoulSilver Poké Ball HS95. The kit card reuses the twin's vectors and keeps its own Cardmarket URL. Auto-confirm only when the artwork perceptual hash matches; borderline pairs stay held. Release them as a second candidate through Steps 2 and 3.
- **Held, with reasons:**
  - 28 Unown Collection: share the exact Cardmarket URL with Unseen Forces Unown, so likely duplicates. Don't merge or hide without a decision.
  - Ancient Mew: 5 Cardmarket versions.
  - Terapagos & Friends: no source image.
  - BW77 and BW78: cancelled promos with no Cardmarket product.
  - 6 My First Battle energies, Potion and Switch: risk of confusion with lookalike cards.
  - 5 MFB Pokémon and 2 McDonald's 2015 (Mudkip, Meditite): image rights or an independent scan missing.
  - 5 DP trainer-kit cards: no physical photo.
  - 5 HS/SM trainer-kit cards: their scan queries failed.
- Record the English gate in `PROCESS-AND-PENDING.md`: live counts, import ID, held list with reasons.

## Step 5. Japanese

Same flow (candidate, write, staging switch, light check), one wave at a time.

1. **Baseline:** read live Japanese gaps by set, gap type and rarity. The last known totals were 2,583 missing images and 2,408 missing URLs.
2. **Link-only first:** match each row to the Cardmarket Japanese expansion list by exact set and collector number. Accept one candidate automatically; zero or several stay held. Never copy an English URL.
3. **Printing siblings:** same artwork-hash pairing as English.
4. **Images, set by set:** use one source per set family (official database, established archives, verified provider images, then marketplace photos), tested on about 10 cards first. Vintage sets (PMCG, neo, VS, web) have no collector numbers, so match on name, set symbol and Pokédex number. Sets with no reliable source stay held with a named reason.
5. Build vectors only for new references with the pinned models, then write, switch and check as in Steps 2 and 3.

## Done when

- English: the 51 and the confirmed siblings are live on staging, and the holds are documented.
- Japanese: every gap is either live or held with a named cause, with counts recorded in `PROCESS-AND-PENDING.md`.
