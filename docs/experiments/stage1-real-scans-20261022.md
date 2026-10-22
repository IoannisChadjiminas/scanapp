# Stage 1 real-scan fixes — 22 October 2026

## Replay result

With the new flags enabled, the frozen 157-photo panel gives **58 early
answers (36.9%): 43 stage 1 + 15 stage 1b, 0 wrong**, versus **53 (33.8%)**
before. Every original early answer keeps its card and stage. The remaining
**99 full-pipeline answers are unchanged**. Printing grouping affects **0
panel photos**; the measured base/reprint reference cosine for
`en:sv04-159` / `en:PPS5-PAR-159` is **0.9763336**.

The five additions are `en:pop9-15`, `en:base5-21`, `en:base1-6` at stage 1,
and `en:base1-68`, `en:base1-24` at stage 1b. The last two still pass the real
artwork verifier with its unchanged 10-inlier floor.

The PR #65 kit has **zero rows in set_totals**. Replaying it without adding
operational totals would silently fail to exercise the new total filter.
This replay backs the kit up into an in-memory database and adds a frozen,
public-only snapshot of **560 staging set totals**. The original kit is
untouched. Both flag-off and flag-on runs use identical catalogue inputs.
The flag-off run reproduces the measured 40 + 13 baseline exactly.

Reproduce from the repository root with the local simulation kit present:

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python api/scripts/replay_stage1_real_fixes.py \
  --output data/latency/stage1-real-scans-20261022/replay.json
cd api
OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -m pytest -q -rs
```

Aggregate results, input hashes and duplicate audit are in
`stage1-real-scans-20261022.json`. The seven-scan fixture and operational
totals snapshot are committed under `api/tests/fixtures/`.

## What changed

- A known printed denominator overrides a bare catalogue alias. If no printed
  denominator exists, the stored set total qualifies the number; a known
  different total rejects the candidate. Explicit reprint fractions retain
  precedence over the reprint set's own total.
- Bare/`en:` aliases normalize set namespaces, collector zeroes, names and
  language, and prefer the `en:` ID. Optional printed-number metadata no
  longer prevents an otherwise identical pair collapsing.
- Same-name/number/language base/reprint candidates can form one identity
  when their references have cosine at least 0.95, or an explicit catalogue
  reprint link exists. The response displays the unambiguous non-promo base,
  returns `printing_ambiguous`, persists all offered choices, and requires
  explicit printing selection even if ordinary confirmation is disabled.
  A lone Prize Pack candidate abstains. Unrelated candidates and visual
  contradictions still block an early answer.
- Additional promo-code aliases are limited to promo sets. Existing bare
  collector/label lookup is preserved: filtering those existing candidates to
  promos would lose valid slab answers and could auto-select a Prize Pack
  while dropping its base card.
- Optional diagnostics log the searched vector's top ID/score, up to five
  text IDs plus the full count, and the actual contradicting ID/gap. They do
  not log vectors, images or raw OCR. Artwork completion preserves this
  metadata. No threshold was lowered.

All five code defaults are **false**: `STAGE1_SET_TOTALS`,
`STAGE1_NORMALIZE_DUPLICATES`, `STAGE1_PRINTING_GROUPS`,
`STAGE1_PROMO_NUMBERS`, `STAGE1_DIAGNOSTICS`. Only `compose.dokploy.yaml`
enables them by default. Production configuration is unchanged. Staging was
queried read-only; nothing was deployed or changed on the live server.

## Corrections to the proposed causes

The current active catalogue's Charmeleon rows match on every field in the
old duplicate rule: name `Charmeleon`, set `base1`, number `24`, printed number
NULL, language `en`. **No field broke the old rule.** All **561/561** pairs
from the PR #65 CSV are present and **0 were missed** by the old rule in this
snapshot. The old ambiguity is reproducible after correctly collapsing the
alias: Base Set still competes with Vivid Voltage until totals reject
`24/185`. Synthetic normalization cases cover the requested hardening.

Bare **Toxel + 078 already resolves uniquely** to `en:mep-078` in the old
lookup. Its real `stage0` line records **text=0**, and its saved OCR evidence
contains no parsed phone hint. The `Toxel / 078` in results is server OCR;
using it as phone evidence would manufacture a successful replay. The new
tests explicitly preserve this distinction.

## Seven real scans: before and after

These are the recovered parsed phone fields, not reconstructed request
payloads. The active catalogue candidate slice includes all name matches
for the recorded numeric keys, including localized rows with English titles.

| Scan | Retained phone evidence | Before | Text resolution after fixes |
|---|---|---|---|
| c5687ed0 | Ancient Booster Energy Capsule, 159/182 | ambiguous_text | `en:sv04-159`, choose base/Prize Pack printing |
| 70585dbe | Pikachu, 35/108 | ambiguous_text | `en:xy12-35` only |
| b438c6f1 | Charmeleon, 24/102 | ambiguous_text | `en:base1-24` only |
| 982a6a0d | Comfey, 077/128 | visual_contradiction | `en:30th-077` only; contradiction remains unverified |
| b3ac26f2 | No phone text | no_unique_text | No text candidate; cannot answer from these inputs |
| df96aa6a | Brute Bonnet, no number | no_unique_text | No text candidate |
| a19b066e | Brute Bonnet, no number, no embedding/quad | no_embedding | Still no_embedding |

**The expected four real early answers were not verified.** The six observed
phone vectors and all numeric corners were not persisted in results or review
files, and the user confirmed there are no saved request payloads. Those six
exact gate-replay tests are explicitly skipped. The manual no-embedding case
is replayed and still abstains. Three of the intended identities now resolve
from real retained phone text, but no real-vector success is claimed; Toxel
also needs phone text on a future scan. The fixture never substitutes server
OCR, a reference vector, an artificial full-frame quad or simulated vectors
for missing phone inputs.

## Comfey investigation

The phone's leading ID was not logged, so it cannot be recovered. The recorded
**0.0641** is the gate's top-versus-runner-up margin, not necessarily the gap
to Comfey. The separate server visual search led with **`ja:S10a-014`
(Pikachu), score 0.72840**, while the selected Comfey's visual score was
**0.65824**. Those two reference vectors have cosine **0.68568**, below the
0.84 language-twin floor. This is consistent with global visual confusion,
but does not establish which card led the phone vector. The contradiction
guard remains intact. The new logs distinguish the leader, runner-up margin
and actual contradiction gap for future scans.

## Validation

The full API suite passes: **932 passed, 10 skipped**. Six skips are the
missing real phone vectors/corners; three existing PostgreSQL checks require
a disposable loopback test database, and one existing two-lane model check
requires local ONNX models (the local models directory is empty). No failing
tests remain. Unit tests cover printed totals and precedence, alias normalization, promo codes and
uniqueness, base/Prize Pack ordering in both vector directions, explicit
reprint links, unresolved printings, contradictions, artwork completion,
persisted printing review and diagnostics flag gating. The frozen panel is
also tested with the flags both off and on.
