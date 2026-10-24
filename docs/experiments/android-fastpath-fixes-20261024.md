# Android fast path: server-side fixes, replayed offline — 24 October 2026

## Result

On the A55's 157-photo frozen panel, replayed offline with the phone's captured ML Kit text, **only the server-frame fix adds early answers: +2 (25 → 27), 0 wrong.** Number repair and the constrained fuzzy name add **0** on this panel. Full-scanner top card is unchanged: **148/156**. The full API suite passes: **951 passed, 12 skipped** (the skips are the same environment skips as before). All three flags are **default off in code**; only `STAGE1B_SERVER_FRAME` is on in `compose.dokploy.yaml`.

This is far short of the 50/157 release gate. The replay shows why, and it is not a server normalisation problem (see "What limits coverage").

| Step (flag) | Early answers | New | Wrong | Photos changed | CPU |
|---|---:|---:|---:|---|---|
| Replay baseline (all flags off) | 25 (15 stage 1 + 10 stage 1b) | — | 0 | — | stage 1 gate ≈ 3 ms |
| 2. `STAGE1_NUMBER_REPAIR` | 25 | 0 | 0 | none | ≈ 0 |
| 3. `STAGE1_FUZZY_NAME` | 25 | 0 | 0 | none | ≈ 0 |
| 4. `STAGE1B_SERVER_FRAME` | 27 (15 + 12) | **+2** | 0 | `fresh100_236504673185`, `fresh100_135586143350` | 0.24–0.31 s on an answer; 0.03 s when no frame is found; 0 when the text does not name one card |
| All three together | 27 (15 + 12) | +2 | 0 | the same two | as step 4 |

Aggregate numbers and photo IDs are in `android-fastpath-fixes-20261024.json`. No photo, OCR text or vector is committed.

## Step 1: the replay harness and its baseline

`api/scripts/android_fastpath_replay.py` (with `dart_card_text_port.py`, a port of `lib/data/card_text.dart` that reads the app's own `set_totals.dart`). For each panel photo it:

1. maps the captured ML Kit lines onto the card through the A55's gallery corners (the corners of the live run), picks the name and number with the app's rules, and builds `client_text` exactly as the app would, including dropping a number the bundled set totals cannot hold;
2. takes the phone vector and corners where the live run sent them;
3. runs the real `evaluate_stage1` (stage 1, stage 1b, the single-card artwork verifier) against the PR #65 catalogue and reference kit plus the frozen 560-row set-totals snapshot, with the shipped flags on;
4. scores against `expected_card_ids`.

**Text fidelity is good:** the rebuilt text is present for **131/157** photos, the same count as the 131 the phone really sent.

**The baseline does not match the live run photo for photo: 25 early answers against 21 live (17 + 4), both with 0 wrong; 15 are in both.** The causes, none of them a gate difference:

- **Phone vectors were not retained.** Only 91 of the 123 vectors the phone sent were stored, and those used a fixture quad, not the corners it sent. The replay therefore embeds the exact gallery-quad crop with the server's DINO model (about 0.998 cosine to the phone model on the same crop). Against the logged live gate lines, the vector's top card matches on 105 of 114 photos and the top score differs by a median of 0.002 (p90 0.006).
- **Artwork verification is more permissive offline.** 7 of the 10 replay-only answers are stage 1b photos the live run reported as `artwork_miss`; they pass here. This is the known Android `artwork_miss` problem from `docs/android-fast-path-plan.md` step 4, and it is not explained by anything in this replay. Treat every stage 1b gain below as an upper bound until a real A55 rerun.
- **ML Kit is not deterministic across runs.** Six live answers do not replay (`fresh100_116219612870`, `fresh100_145701209354`, `fresh100_227337115305`, `freshextra_6_1736995038`, `freshraw_4_123815526`, `reported:ea69f453…`), in some cases because this capture read different text than the live run.
- One photo's live corners were never stored, so it replays without a quad.

Every gain below is relative to the replay baseline, not to the live 21.

## What limits coverage (and why steps 2 and 3 find nothing)

Rebuilt text on the 157 photos: name and number 59; name only **70**; number only 2; neither 26. **Name alone can never select a card**, so those 70 can only be answered by the full pipeline. The server cannot recover a number the app never sent:

- **The app drops a number the catalogue cannot hold.** `_validNumber` in `card_text.dart` returns null for `205197`, `013T2`, `2o4193-` and `204/19)`: its number shape needs a slash and at most four digits a side, and it must also pass the set-total table. The server therefore never sees the misreads that the analysis listed; it only sees `null`. Server-side repair is correct and tested, but it has nothing to repair for this app version.
- **The shipped name match is already tolerant.** `name_match` accepts a similarity of 0.72, so `Seizor`, `DrowzZee`, `Mavill` and `GENGAR & MIMIK YU GX` already matched when a number was present. The analysis's 48 "non-exact names" were exact-string checks, not failures of the gate. The 9 photos with name and number that still abstain at stage 1 are wrong picks by the app (`1999 POKEMON GAME`, `SURFACE 10`, `CENTERING 9…`, grader words, a misread `203/197` for a 205/197 Scizor), which no fuzzy match can fix.

**What-if (needs an app change; not shipped).** If the app also sent the raw footer token whenever it has a name but no valid number, number repair would add **+1** (`fresh100_316758938735`, Marill, `2o4193-`, stage 1, correct). A crude token picker that returned copyright years for most photos, so this is a floor and not a measured ceiling. It is the only evidence that repair can matter, and only after an app change.

## Step 2: `STAGE1_NUMBER_REPAIR` (default off)

`api/app/recognition/stage1_text_repair.py`, used by `stage1_gate.lookup` only when the exact lookup found nothing:

- o/O to 0 and l/I/| to 1 **inside the number only**, prefixes stay letters (`#TGO5` → `TG05`);
- a missing slash, or a `T` or `)` read as the slash, or a total cut short, accepted **only** when the result is a numerator and total the catalogue holds for that numerator (`205197` → `205/197`, `204/19)` → `204/193`, `013T2` → `013/172`, `2o4193-` → `204/193`); trailing junk is stripped;
- the variants are then run through the ordinary strict lookup, so a card's **name** must still agree and the number can never pick a card; nothing is ever produced that the catalogue does not hold (`999/193`, `204/777` and `205198` give nothing).

Replay: 0 changes. Unit tests cover each example above, the refusals, and that an exact hit is untouched.

## Step 3: `STAGE1_FUZZY_NAME` (default off)

After the number **with its set total** has narrowed the candidates (a bare number never triggers it), a name that is within two edits on names of 6+ letters, one edit on 4–5 letters, or 0.8 similar, is accepted. Names are folded for case, accents, spaces and `&`; CJK names stay exact; names under four letters must match exactly (`Mew` is not `Mewtwo`). A fuzzy name alone never selects a card: no number, a bare number, or a wrong number returns nothing.

Replay: 0 changes. The shipped 0.72 rule already covers nearly everything this would; the new rule adds accent folding and the edit-distance route. **Recommendation: do not enable it** until an app version exposes names the 0.72 rule misses.

## Step 4: `STAGE1B_SERVER_FRAME` (default off; on in `compose.dokploy.yaml`)

When stage 1b is on, no phone vector was sent (usually because the gallery found no corners) and the text names **exactly one card** (after the same duplicate, twin and printing-group handling), the server:

1. detects its own frame with the full pipeline's detector (`server_frame_rect`), and embeds that crop once, as the pipeline does;
2. runs the ordinary stage 1/1b gate with that vector. A stage 1 agreement is **downgraded**: nothing is answered on the server's own frame without the artwork check. The `visual_contradiction` rule (another card leads by ≥ 0.05) still blocks;
3. runs the same single-card artwork verification, with the 10-inlier floor unchanged, using the server frame (or the phone's corners if it sent them without a vector);
4. answers at stage 1b with reason `server_frame_artwork`.

If the text does not name one card, nothing runs and the full pipeline starts as today. If no frame is found the gate abstains with `no_server_frame`.

| Photo | Label | Replay baseline | With the flag | CPU |
|---|---|---|---|---:|
| `fresh100_236504673185` | Armarouge 203/198 (`en:sv01-203`) | `no_embedding` | stage 1b, correct | 0.31 s (0.06 frame + embed, 0.26 artwork) |
| `fresh100_135586143350` | Kirlia 212/198 (`en:sv01-212`) | `no_embedding` | stage 1b, correct | 0.24 s (0.07 + 0.17) |

**CPU.** 0.24–0.31 s on this Mac at one thread, so the ≤ 0.3 s target is met here but only just; a slower server CPU will exceed it. No work is wasted when the text is not unique, and a missed frame costs about 0.03 s. The server-frame path is only entered for photos that already have no vector, which the full pipeline would otherwise have started from scratch.

**Visual review of the changed photos** (photo beside the reference, both by eye):

- `fresh100_236504673185`: a card photographed on white, tilted a few degrees, with a dull holo. Same card as the reference: Armarouge, the Fire Off and Flame Cannon text, the SVI 203/198 footer and the same street-and-arch art. Correct.
- `fresh100_135586143350`: a card on granite, rainbow holo glare over the art. Same card as the reference: Kirlia, Magical Shot and Psychic, the sofa-and-baby scene, footer 212/198. Correct.

**Photos that still miss.** Of the 43 photos with no vector, 10 still end as `no_embedding` (their text is empty), 6 give `no_server_frame` (Armarouge `fresh100_227232802112` and `fresh100_286467766284`, Kirlia `fresh100_127125641244` and `fresh100_356618307865`, Lechonk `fresh100_167884982800`, and the Ancient Booster Energy Capsule scan): the server's detector finds no frame in them. An as-uploaded fallback for card-shaped images is the obvious next experiment, but it is a different decision than the one asked for here, so it is not included. The other 27 abstain because the text names no single card (a missing, misread or ambiguous number).

## Other gaps the replay surfaced (not in scope)

- **4 `ambiguous_text` photos** (Tangela 178/165 twice, Abra 063/165 and 43/102): one English and one Japanese row share name and number, and stage 1 has no language rule without a slab label. Stage 1 could prefer the vector's language twin when the cosine is above the twin floor. This is a separate gate change.
- **`name only` is the big one.** 70 photos have a readable name and no number. The cheapest lever is in the app: send the raw footer token when no valid number was found (with the repair in this PR, the server could use it), or run a number-only pass on the footer.

## Gates

| Gate | Result |
|---|---|
| 0 wrong early answers on the panel | Pass, in every mode |
| Full-scanner top card unchanged (≥ 148/156) | **148/156**, same as the live run |
| Full API suite | **951 passed, 12 skipped** |
| Flags off in code | Pass (`Settings` defaults, tested) |
| PR #65/#67 panel replay (40 + 13 and 58 answers) | Still passes with the new flags off |

## Before this goes to production

- This panel has now been used for tuning twice. A **fresh holdout** and **one real A55 rerun with the flag on** are still required. In particular, the A55 rerun is needed to confirm the stage 1b artwork results and the CPU of the server-frame path under real load.
- The replay uses stand-in vectors and one capture of ML Kit text; it does not prove any live number.

## Reproduce

```sh
cp /tmp/a55-fastpath-ocr-157.json "$SCRATCH/"        # local only, never committed
OPENBLAS_NUM_THREADS=1 .venv/bin/python api/scripts/android_fastpath_replay.py \
  --ocr "$SCRATCH/a55-fastpath-ocr-157.json" --output "$SCRATCH/out.json" \
  [--number-repair] [--fuzzy-name] [--server-frame] [--whatif-raw-number]
cd api && OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -m pytest -q -rs
```

It needs the local simulation kit, the A55 parity data, the DINO teacher model, and `~/StudioProjects/PokeSingle/lib/data/set_totals.dart`.
