# Printed identity and layout recovery

The 17 October 2026 Jumpluff scan (`0fd8365b-d94b-46f7-9952-96559889e024`)
returned `retake` although the card's printed title and `7/111` are visible.
The existing artwork verifier rejected the correct reference. Its DINO
similarity was approximately 0.55; regenerating the reference vector agreed
with the stored vector, so this was not a stale-vector mismatch.

`STRUCTURED_LAYOUT_RECOVERY=true` enables an optional recovery path. It is
**off by default**, including in `compose.dokploy.yaml`. After ordinary
recognition abstains (`retake` or `no_match`), the recovery may run one compact
footer OCR pass when no collector fraction at confidence 0.90 or above exists
on an upright card-shaped image with a title read at 0.95 or above. The pass
retains only literal fractions at OCR confidence 0.90 or above. These hits
gate layout review only: they never re-enter ordinary ranking, status or
`footer_retry_contributed`, so a result that did not abstain cannot change.
They are recorded separately as `layout_footer_hits`. No digits or expected
titles are substituted.
Signed resistance values such as `-30` are excluded from collector parsing.
When identical footer tokens repeat, collector parsing retains the strongest
actual OCR observation, without combining confidences. Raw observations and
all different, potentially conflicting tokens remain available.

After ordinary recognition abstains, the recovery requires:

- An exact normalized printed title at OCR confidence 0.95 or above.
- Known agreeing language and a literal collector fraction at confidence
  0.90 or above, including a matching known printed denominator.
- No prior collector or structured identity contradiction.
- Exactly one eligible set/number/language identity, with at most four
  reference aliases. Larger or ambiguous groups abstain.
- Full-card reference geometry with at least 30 inliers, at least eight in
  each of the header and footer regions, and at least 30% query coverage.
  The existing homography, spatial spread, orientation and ratio checks
  still apply. Insufficient size or sharpness cannot use this recovery.

The result is `uncertain` and requires confirmation. Layout landmarks are
stored separately from artwork evidence; similarity scores and automatic
match thresholds are unchanged. This does not establish authenticity, finish
or catalogue completeness. Existing useful results are not replaced.

Reference layout features are extracted locally from at most four files
under the configured reference root. With an existing validated feature
bundle, the file mapping and source SHA-256 must agree with that bundle.
The artwork bundles are not changed. A missing or changed reference abstains.

## Verification

Run `python -m pytest -q api/tests` from a prepared development environment.
`api/tests/test_layout_recovery.py` covers literal footer recovery, gameplay
numbers, language/number conflicts, weak OCR, missing denominators, ambiguous
identities, reference integrity, insufficient layout evidence, and the
confirmation-only pipeline result.

`api/scripts/replay_layout_recovery.py` compares the recovery flag off/on
using real models, the guarded read-only cloud snapshot, and SQLite memory
for scan results. It disables capture writes and grading, and does not call
feedback, price queues or the public scan endpoint. Supply one or more
`--image` paths and a new `--output` JSON path.

Run the full replay in a **separate resource-limited container**, with the
API data volume mounted read-only. Do not run a second complete runtime
inside the serving API container: the first diagnostic attempt exceeded
that container's 3 GiB limit and caused an automatic API restart. The API
returned to healthy; subsequent full replay work uses a separate container
with a memory limit and a high OOM score so the diagnostic process is the
first to stop under memory pressure.

Retained review JPEGs are recompressed copies of uploads. Their replays are
useful reproductions, not byte-identical original requests or a general
accuracy benchmark. Sequential warm-cache comparisons do not establish
latency improvements. Keep this path opt-in pending representative positive
and negative photo evaluation; do not enable it through a full-stack Git push.

## Saved-photo replay result, 17 October 2026

The final isolated replay used the live validated catalogue and models, with
the recovery flag off/on and all scan records confined to memory:

| Retained photo | Recovery off | Recovery on |
| --- | --- | --- |
| Jumpluff `0fd8365b…` | `retake`, no displayed card | `uncertain`, `en:neo1-7` (Neo Genesis 7/111), confirmation required |
| Oddish `0bf34f5b…` | `printing_ambiguous`, `en:A2-001` | Same identity and ambiguity |

The compact footer uses bicubic reduction. On this Jumpluff image it read
`7/111` at 0.92775 OCR confidence; Lanczos reduction of the same strip read
the same text at only 0.85729. These are model scores, not probabilities.
The result retains the original low visual similarity instead of rewriting
it as a high-confidence visual match.

The complete API test suite passed: **671 tests**. The two-photo comparison
supports this case-specific recovery and preserves one existing useful
result; it does not measure general accuracy or false-positive rates. The
new flag remains disabled on the serving API. No Git push or deployment was
performed.

## Existing-photo regression procedure

`api/scripts/regression_layout_recovery.py` compares the proposed recognition
rules against recovery disabled with the original, pre-change collector
extractor restored in all four importing modules. This includes the signed
gameplay-number and duplicate-confidence changes in the comparison; merely
turning the new flag off would not test those changes.

The frozen manifest combines the 155-photo suite and the 28-photo regression,
32-photo JAW2, 20-photo PCG and 18-photo vintage panels. The 253 panel entries
contain 242 unique photo hashes. Each original panel label remains separate:
one existing image has conflicting Latias/Latios labels, and some panel
entries are unlabelled even though the frozen suite labels the same image.
Original manifests are not edited.

Each pair runs against the same validated catalogue and real models in a
separate container. Results and sessions live only in SQLite memory. Exact
pixel/model outputs may be reused within one photo's pair; different crops,
rotations, resize filters, readers and preprocessing modes are distinct keys.
No OCR decisions or outputs are shared between photographs. Initial uncached
completed pairs remain part of the same report when resuming.

This is **recognition-only** regression: grading extraction is disabled in
both arms. The runner compares best identity, recognition status and lost
expected-card matches, and preserves complete responses and evidence in an
incrementally flushed JSONL report. It is not grading QA or a timing benchmark.
`--resume` checks that the manifest, collector rules and catalogue metadata
are unchanged before continuing completed pairs.

### Completed existing-photo comparison

All **242 unique photos / 253 panel entries** completed on 17 October 2026.
There were **no changed card identities and no lost correct matches**.

| Panel | Entries | Expected-ID matches before / after | Identity or status changes |
| --- | ---: | --- | ---: |
| Regression | 28 | 13/18 labelled / 13/18 labelled | 0 |
| JAW2 | 32 | 24/32 / 24/32 | 0 |
| PCG | 20 | 17/20 / 17/20 | 0 |
| Vintage | 18 | 16/18 / 16/18 | 0 |
| Frozen suite | 155 | 150/154 labelled / 150/154 labelled | 2 |

This is **not a clean status-stability pass**. Parasect
`en:swsh11tg-TG01` (`fresh100_334557743755`) and Raikou V
`en:swsh12.5gg-GG41` (`holdout3_018`) both kept their correct identities but
changed from `matched` to `uncertain`. The compact footer read contributed
new evidence, triggering the existing `footer_retry_contributed` review
guard. No guard was bypassed to hide these changes. Recovery remains disabled
on the serving API.

The isolated test process reached its own memory cap after 230 complete
pairs. All output was flushed, and the final 12 pairs resumed with matching
manifest, source and catalogue metadata. The serving API stayed healthy and
its restart count did not change during this regression run.

Complete paired responses, source/configuration hashes, manifest and a human
report were saved in PokeSingle's
`output/scan-investigation-2026-10-17/regression-242/`. The next implementation
step is to confine extra footer recovery to abstained recognition, then replay
the changed cases and the regression before enabling it.

### Compact footer confined to abstained recognition

The compact footer read was moved out of `CardOcr.read` into
`CardOcr.read_compact_footer`, which the pipeline calls only inside the
layout recovery block. Parasect and Raikou V were `matched` before
recovery and are no longer eligible for the read, so their
`footer_retry_contributed` downgrades cannot recur. The API suite passes
(674 tests). The real-model replay of Jumpluff, Parasect, Raikou V and the
242-photo regression must be repeated before enabling the flag.
