# Conflict-only title recovery

`OCR_CONFLICT_TITLE_RETRY` is disabled by default. It adds one focused title read
after ordinary recognition returns an uncertain, unrelated candidate list.
This addresses split title text such as `BASIc Charmar` plus `nder` on the
18 October Charmander scan.

The gate excludes matched results, ambiguous printing choices, quality retakes,
unknown/weak titles or languages, any existing title-compatible candidate,
confident explicit collector identifiers, explicit user crops, and requests
that skip detection. Eligible frames must be large enough and card-shaped.
The normal image detection, OCR, ranking and thresholds are unchanged.

The retry reads the central 60% of the selected frame's upper 24%, with a
maximum width of 1000 pixels. It uses literal OCR text at confidence >= .90;
it does not join fragments, substitute catalogue text, repair numbers, or
increase confidence. A complete separated BASIC/STAGE badge may be excluded
only from the compatibility comparison with the first partial title.
Readable conflicting mechanic suffixes remain contradictory.

The pipeline evaluates the same selected frame with supplemented observations.
It preserves the frame's original detection state and all original hits and
footer observations, emits no second preview, starts no additional grading
job, and persists only the selected final evaluation. A replacement requires
existing independent local artwork geometry for the selected card, compatible
original language/number evidence and the fresh observed title. It must remain
uncertain or printing-ambiguous. Missing verification, incompatible text, and
optional errors keep the original result.

The focused read and its observations, original title, first/retry card IDs and
selection decision are retained in `ocr_json.title_recovery`.
`timings_ms.title_retry_ms` includes the additional read and evaluation even if
the retry is rejected. Original first-pass duration is retained when a retry
is selected. Boundary recovery diagnostics stay separate from title recovery.

## Validation

Run `python -m pytest` from `api/`. The tests cover gate exclusions, immutable
original observations, contradictory title rejection, mandatory geometry,
review-only results and exactly one persisted scan.

`api/scripts/regression_title_retry.py` compares the flag off/on against the
same catalogue and models. Use a separate resource-limited API-image container
with read-only data, an immutable hash-checked manifest, in-memory results,
capture storage disabled and grading disabled. It does not write catalogue,
feedback, prices or operational scan records. Results are flushed per pair;
`--resume` checks the manifest, application code, catalogue and settings.

By default, exact-pixel model inference is memoized only within each paired
case; different crops/preprocessing/readers are separate keys and both policies
still run. This makes raw arm durations unsuitable for latency comparisons.
Use `--uncached` for separate latency measurements. Resource limits and grading
differences mean these measurements are not production response-time estimates.

The retained recent photos are lossy JPEG copies. In addition to fresh image
replays, cases with `recorded_ocr` reproduce the original first-pass observations
on the retained selected frame, then run the new focused OCR and artwork
verification with real models. These are evidence-reproduction cases, not
byte-exact original-upload OCR tests. Ordinary frozen photo cases always run
their original pixels through current framing, OCR and matching.

The final panel and latency results are recorded in the task's investigation
artifacts. A change to correct identities or a downgrade of existing results
must be reviewed before enabling this flag. No rollout is performed by the
regression runner.

### 18 October validation

711 API tests passed. The paired replay completed 251 cases: the 242 unique
existing photos, six fresh retained-image variants of the three recent scans,
and three original-OCR reproduction cases. All 242 existing responses were
identical apart from scan IDs and timings; there were no lost correct matches
or status downgrades. The intended recorded-evidence failure recovered from
Torchic to Charmander with 34 verified artwork inliers. The other two original
cases stayed correct. Fresh recompressed variants can still fail with different
footer OCR errors; confident contradictory identifiers continue to block this
recovery.

Nine separate uncached pairs (three repetitions of the original evidence
cases) recovered the failure every time. Additional recovery work had a median
of 1.599 seconds on the resource-limited test container. Four existing
unresolved vintage cases rejected their focused reads and retained their
original responses, adding approximately .91–1.04 seconds each. Matched results
never enter the retry. These recognition-only tests do not validate grading or
production latency. The flag remains disabled by default.
