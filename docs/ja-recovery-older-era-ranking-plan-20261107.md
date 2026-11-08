# Older-era Japanese cards: fix the ranking, not the release order (plan, 2026-11-07)

Companion to `ja-recovery-older-era-vectors-proposal-20261107.md`, which describes the problem and
proposes an era-by-era release gated by a synthetic bad-photo test. This plan replaces that proposal.
It keeps the proposal's facts and gates and changes the approach: the ~6,220 held cards are a
ranking problem inside the scanner, and the scanner already has the parts needed to solve it.

## Where things stand (unchanged)

Staging serves `PS-CATALOGUE-EN-JA-REC5-20261107`. The all-eras candidate `jarec`
(`pokesingle_completion_20261107_jarec`, inactive, 50,882 pad vectors) gave every new Japanese
card scan vectors and changed 4 of the 98 regression photos; the modern-era-only release gave 0.
About 6,220 older-era cards with images are therefore "printing alternatives": a scan can show them
only as a printing choice behind a same-artwork scannable card. Nothing is missing from the
catalogue; only the scan path is blocked for them.

Both failures were Japanese photos scanned with Japanese already among the search languages:

- `ja:PMCG4-017`: a new Mewtwo promo took first place and the right card left the suggestions.
- `ja:PCG1-048`: the top two became so close that the local artwork check rejected the leader and
  the scan asked for a retake.

## Why the proposal is the wrong tool

1. **It fences off the cause instead of fixing it.** The embedding scores the right card at about
   0.72 on blurry vintage photos, and thousands of vintage artworks score the same. Releasing by era
   only decides which cards may crowd; every later era release re-opens the same risk.
2. **The retrieval cut is fixed at twenty.** The full-card stream takes `top_k(..., k=20)`
   (`api/app/recognition/pipeline.py:560`) and the artwork stream `k=15`
   (`api/app/recognition/artwork.py:107`). "Not in the suggestions" is exactly what a fixed cut
   does when thousands of neighbours arrive: the right card falls out before any later check can
   look at it. No test schedule changes that.
3. **The synthetic test measures the wrong stage.** It checks picture ranking; the `PCG1-048`
   failure came from the local artwork check, which only the full pipeline runs. The proposal says
   so itself.
4. **Better photos already exist.** Staging keeps review copies of real uploads (`store_captures`)
   with the stored full-pipeline answer in `results.sqlite`, and the owner's confirmations and
   corrections label them (`api/scripts/export_labels.py`). The full offline runner
   (`api/scripts/full_bench/run_full.py`) replays them with the real `recognize_bytes`. Real
   sleeves, glare, shadows and crops, hundreds of photos, hours of work. The 98 eBay photos stay as
   a second panel.

## What the scanner already has

| Part | Where | Today's role |
|---|---|---|
| Query-time retrieval mask | `_scan_keep` (`pipeline.py:87`): language choice and the physical-card mask, passed as `keep` to `top_k` | Excludes languages the user did not pick and Pocket rows |
| Deeper candidate streams | full card `k=20`; artwork index `k=15`; OCR metadata, title, geometry and number+name candidates merged into `combined` | Builds the candidate list |
| Reranker | `rerank` (`rank.py:522`): name, collector number, language bonus (+0.05 / −0.04) on top of the visual score | Orders `combined` |
| SIFT geometric verifier | `LocalArtworkVerifier.verify` (`local_match.py:208`): up to 8 references, RANSAC homography, `artwork_inliers`, two passes (1,000 then 2,000 features) | Confirms or rejects the leader's artwork; ranking among verified cards stays the OCR/global order by design |
| Status rules | `decide_status_with_reason`, `threshold_min_visual=0.78`, `threshold_min_visual_ocr=0.70`, `threshold_min_gap=0.04` | `matched` / `uncertain` / `retake` |

Two existing rules must be kept: keypoint counts certify a **shared artwork**, never which reprint it
is (`pipeline.py`, comment above the verified-candidate sort), and a scan that needed the verifier is
never `matched`, only `uncertain`. The plan uses inliers only to choose **between different
artworks**; the printing within an artwork family is still chosen by number, name and the existing
order.

## The plan

Four steps. Steps 0 and 1 are measurement and decide whether steps 2 and 3 are built at all.

### Step 0: demand (minutes)

From `results.sqlite` on staging, count scans whose search languages include `ja` and whose first
card, or any confirmed/corrected card, belongs to an era now held (Original, Neo, VS, e-Card,
vending, old promos, ADV, PCG, DP, Platinum, LEGEND, BW, XY). Report absolute counts and the share of
all Japanese-language scans, by era. Counts and scan ids only; no photos or OCR text leave the
server.

Decision: if held-era demand is a handful of scans, stop after step 1 and keep the held cards as
printing alternatives. The phone pipeline helps every scan; this would help almost none.

### Step 1: the verifier experiment (under an hour)

Offline, in the replay container (`replay_panels.py` setup: served API image, the `jarec`
candidate's four catalogue keys, `persist=False`), for the two failure photos and the 98-photo
panel:

1. Retrieve deeper: the full-card stream at `k=100` and the artwork stream at `k=50`, same `keep`.
2. Collapse to artwork families: group candidates that share an artwork (same `art_box` reference
   features or a twin at the existing twin cosine threshold), keep the best-scoring member per
   family, take the top 24 families.
3. Run `verifier.verify` over one reference per family with `limit=24` (the method takes a limit; no
   code change for the experiment).
4. Record, per photo: the correct card's rank in the raw retrieval, its family's rank, the
   `artwork_inliers` of every verified family, and whether the correct family has the most inliers
   with a margin (propose 1.5× over the runner-up and at least 12 inliers; tune on the panel).

Pass: `PMCG4-017` and `PCG1-048` come out as the top family by inliers, and on the other 96 photos
the inlier leader never contradicts the current correct answer. Measure the time per photo of
verifying 24 references, on the staging-sized CPU.

Fail: the embedding and SIFT together cannot separate these artworks. Then the remaining options are
a better embedding (hard-negative fine-tuning on the vintage Japanese catalogue; a project of its
own) or leaving the held cards as they are. Do not fall back to the era-by-era release; it has the
same failure mode with a longer fuse.

### Step 2: evidence-gated retrieval for held cards (server, flag off)

Give the held cards vectors again (the `jarec` build already has them) and add a per-card
**held** mask to the runtime beside `physical_cards`, loaded from a catalogue column so the set
can change by release without rebuilding vectors. In `_scan_keep`, held cards stay masked out
unless the request carries evidence for them:

- the user's search languages include `ja` **and** the OCR detected Japanese script
  (`resolve_search_languages('auto', confident_language_texts(...)).detected`, already computed
  in the pipeline), or
- the OCR read a name or collector number that matches a held card (the existing
  `ocr_title`/`ocr_metadata`/`ocr_text_identity` streams already produce these ids; let them
  bypass the mask), or
- the user asked for a Japanese-only search (`requested.reason == "user"`).

Scans without that evidence see exactly today's index, so their results cannot change. Flag:
`RETRIEVAL_HELD_CARDS_GATED` (default off; off means held cards stay masked always, which is
today's behaviour with the vectors present).

### Step 3: deeper retrieval, family collapse, verifier-ranked artworks (server, flag off)

Behind `RANK_FAMILY_VERIFY` (default off), when the condition that already triggers the verifier
holds (low visual score, small gap, or any of the existing reasons at `pipeline.py:836`):

1. Retrieve `k=100` full card and `k=50` artwork instead of 20 and 15. The merge into `combined`
   is unchanged.
2. Collapse `combined` into artwork families before building the verifier's reference list, one
   reference per family, best scoring member first; raise the verifier limit from 8 to a setting
   (`local_verify_families`, start at 16).
3. If one family leads by inliers with the margin tuned in step 1, that family's members move to the
   top of `combined`; within the family the existing order (number, name, language, visual) chooses
   the printing. If no family leads, nothing changes from today.
4. Status stays `uncertain` whenever the verifier decided (`local_artwork_used`), as today. No new
   automatic `matched` path.

Latency: step 1 gives the per-photo cost of the wider verification. Budget it against the current
`local_artwork_ms` and keep the wider pass only when the trigger condition holds, which is a
minority of scans.

## Gates for every switch

Each of steps 2 and 3 ships only with, in this order:

1. Unit tests for the mask and the family collapse with fixed vectors.
2. The stored-upload replay (`run_full.py` cases plus every stored upload with a confirmed or
   corrected card) on the served API image: **0** changes of first card or status on scans without
   Japanese evidence; on scans with evidence, every change listed and checked by eye against the
   stored photo.
3. The 98-photo replay (`replay_panels.py`) against the served release: 0 best-match or status
   changes with the flag off; with the flag on, `PMCG4-017` and `PCG1-048` correct and nothing else
   changed.
4. Staging health ready, no restarts or OOM, `local_artwork_ms` p95 recorded before and after.
5. Rollback file archived under `/etc/scanapp-staging/catalogue-rollback/`, `events.jsonl` and
   `japanese-set-recovery-finish-plan-20261106.md` updated.

The flags turn on one at a time, step 2 first. The all-eras catalogue (`jarec` rebuilt on top of
`jarec5` with the held column) is published with both flags off, which is behaviour-identical to
`jarec5`, before either flag turns on.

## eBay photos: coverage only

Collecting 100+ real photos of unnumbered vintage cards (handoff rule: test use only, each checked
by eye against the reference) remains worth doing, in parallel and off the critical path. It
answers "do the new cards find themselves", which protects nothing and is not a gate for steps 2
and 3. Add them to the panels when they exist.

## What this plan drops from the proposal

- The synthetic bad-photo test and its calibration step.
- The era-by-era release order and per-era catalogue candidates.
- Permanent "printing alternative" status for older eras as the end state.

## Open points for the owner

- Approve step 0 and step 1 now; they change nothing on staging and decide the rest.
- Agree that the stored-upload replay, not the 98-photo panel alone, is the primary gate.
- Approve the eBay photo collection as a coverage task.
- Baseline first: the last replays ran on the previous API image (`e99c2332…`); staging now runs
  `cbbf83b2…`. Re-run the 98-photo baseline on the running image once before any switch.

## Amendment, 2026-11-08: the verification trigger (step 3b)

The trace of `PMCG4-017-2` (results doc) showed the vintage name choice is not the blocker:

- the OCR name strip read the evolution note at 0.995;
- that "confident name" skipped local verification;
- on the shortlist it vetoed the right, Japanese-named card, while new cards with English-only
  names stayed neutral.

Step 3b, flag `VERIFY_UNMATCHED_NAME` (default off, used together with `RANK_FAMILY_VERIFY`): a
confident name read that names none of the shortlisted cards counts as no name for:

- the local verification trigger (the close-neighbour condition then applies as for a weak read);
- every artwork-compatibility filter in the verification step: the reference filter, the eligible
  matches, and the incompatible-artwork retake.

Ranking and all other rules still see the read. The flag is scoped to **Japanese scans with no
printed collector fraction**, where the name is otherwise the strongest text evidence.

**The rule itself is language-independent.** Any scan whose confident "name" names no candidate
is reading something else. **Next step: the general version**, for every language and for
numbered cards. It needs its own replay on the English panels and the stored uploads, because
there a confident collector fraction usually decides first and the interaction differs.

Gates for 3b, unchanged from this plan:
- `PMCG4-017-2` fixed on the all-eras catalogue;
- zero other best/status changes across the 98 photos and the stored uploads (203 confirmed
  uploads);
- the staging CPU cost reported.

The new vintage eBay panel (135 photos) is baselined with flags off and on; its right and wrong
counts decide whether it is large enough.

## Amendment, 2026-11-08: Japanese species names for English-named rows (step 4b)

### Why

Step 3 (with 3b and the family language fix) passes the `PMCG4-017-2` gate. On the vintage panel
it moves the all-eras catalogue to 116 right first, 11 offered, 0 wrong and 8 retakes, against
82 / 6 / 17 / 30 on the served catalogue. One photo still gets worse than on the served catalogue,
with the flags on or off: `neo1-072-1` (Lugia) is right first on served and a retake on
all-eras. The trace:

| | Served (`jarec5`) | All-eras (`jarec`) |
|---|---|---|
| Name read | ルギア, 0.99 | same |
| Numbers read | `30`, `249` | same |
| First card | `neo1-072` ルギア, visual 0.790 | `jr-play-promos-030` "Ho-Oh ex", visual 0.717 |
| `neo1-072` | first | second, combined 0.7257 against 0.7276 |
| Verification | not triggered (visual ≥ 0.78) | triggered by the weak leader; the blurry photo verifies nothing |
| Result | right card, uncertain | retake (`conflict`, `framing_unverified`) |

The new row wins on two things:
- `name_evidence_comparable` treats a Japanese row with an English-only name as unknown, never as
  a contradiction, so a confident ルギア costs "Ho-Oh ex" nothing;
- the stray `30` (HP or damage) matches its collector number `030/PLAY`.

This is the same weakness as the first `PMCG4-017-2` failure, where English-named new rows stayed
neutral while the right card was vetoed. **8,516 of the 8,741 held cards have English-only
names**, so it is the general blocker for step 5, not a single photo. Verification cannot carry
it: on a photo too blurry to verify any reference, only the name separates the cards.

### What

A Japanese species table derived from the catalogue itself, and a ranking rule that uses it behind
a new flag `RANK_SPECIES_NAMES` (default off).

**The table** (`api/app/recognition/data/ja_species_names.json`, generated by a committed script
from the catalogue being served, with the import id in its header):
- Source pairs: Japanese rows from Sun & Moon onward (`SM*`, `S*`, `SV*`, `M*`, `MC`, promos)
  with a Japanese `name` and an English `view_title`. Those sets carry the official Japanese
  names. The older-era rows do not: 456 Japanese-named rows carry machine transliterations
  (マチャンプ for Machamp, which is カイリキー; アルカニン for Arcanine, which is ウインディ), all from
  the e-Card, PCG, neo and web sets.
- Species, not titles: suffixes (`ex`, `EX`, `GX`, `V`, `VMAX`, `VSTAR`, `BREAK`, `LV.X`, `-GX`,
  `-EX`) and prefixes (`M`, `Mega`, `Dark`, `Light`, `Shining`, `Radiant`, regional forms) are
  stripped on both sides.
- An English species enters the table only when one Japanese name holds at least 80% of its rows.
  Today that gives about 1,150 species, including リザードン, ルギア, ホウオウ, バリヤード and
  カプ・コケコ.
- No hand-written aliases. A species missing from the modern sets stays out, and its rows stay
  neutral.

**The rule**, for a Japanese row and a confident Japanese name read (the same confidence floor as
today):
- *Row species*: the longest table species inside the row's English `name`, or, for a
  Japanese-named row whose name contains no official species, inside its `view_title`. The second
  case covers the 456 transliterated rows.
- *Read species*: the longest official Japanese species contained in the OCR name.
- Both known: equal counts as a name match and different as a name mismatch, exactly as for a
  Japanese-named row today, in `rerank` and in `artwork_evidence_compatible`.
- Either unknown: neutral, as today. A read that contains no species (an evolution note, a
  trainer, a misread) changes nothing, so 3b keeps its role.

Coverage today: about 10,200 to 10,500 of the 14,276 Japanese rows with English-only names get a
species. The rest are mostly trainers and energy, which stay neutral.

### Tests

- ルギア against "Ho-Oh ex" (mismatch) and "Lugia" (match), with the `neo1-072-1` numbers.
- `Charizard-GX`, `M Mawile-EX`, `Dark Charizard` and わるいリザードン resolve to their species.
- マチャンプ / "Machamp" matches a カイリキー read.
- A read with no species (モンスターカードに重ねて使います。) leaves every row neutral.
- Trainer and energy rows stay neutral; English and other-language rows are untouched.
- Flag default off.

### Gates, unchanged in kind

- `neo1-072-1` right first on the all-eras catalogue, with all three flags on.
- `PMCG4-017-2` still fixed.
- The 98 photos: 0 changes with the flags off. With the flags on, only the changes already listed
  for step 3, plus any new fix each checked by eye.
- Stored uploads (203): 0 other best/status changes.
- Vintage panel (135), flags on, against the served catalogue: no photo worse.
- Staging CPU cost reported (a dictionary lookup per candidate, expected negligible).

Still open from step 3, for the owner, not loosened here. Two stored uploads change from one
wrong card to another with the flags on:
- base-set Charmeleon: Japanese `PMCG1-017` becomes English `xy12-10`, the Evolutions reprint of
  the same artwork, while the right card `base1-24` stays among the alternatives;
- `b9c67517`: the same wrong card, now offered with printing choices.

### Order

1. Script, table, rule and tests on PR 108's branch, flag off.
2. The step 3 gate replays again on the served image (16 GB Docker, five lanes, about 25 minutes).
3. Report. Step 5 starts only after that.
