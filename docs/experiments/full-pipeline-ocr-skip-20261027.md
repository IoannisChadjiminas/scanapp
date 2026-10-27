# Full pipeline: why the phone's text never skips OCR (2026-10-27)

Plan: `docs/full-pipeline-speed-plan-20261026.md`. Steps covered: 0 (runner and reproduction check), 1 (reasons), 2a (behind a flag, default off). Step 3 (off/on measurement) was not run, because step 0 did not pass.

## Result in five lines

1. **Step 0 failed.** The offline runner reproduces the stored answers on 57% of the scans where the phone sent its corners and text (114 of 201 with the same status and first card), and on 77% of the older 226 Android uploads. The gate is 95%.
2. **The cause is the photo, not the pipeline.** The server keeps a copy of each upload for review, resized to 1600 pixels on the long edge. The pipeline ran on the full-size original (for example 1363 x 1904 or 1432 x 2000). The copies are all that is on staging, so the runner replays a smaller photo than the one the stored answer came from.
3. **Step 1: the phone's text never qualified for skipping OCR.** On the 164 live staging scans that sent text, every one was refused before OCR: 86 had no collector number, 75 had a name or number below 0.9 confidence, and 3 had complete, confident text but failed the visual floor. None was ever `eligible`.
4. **Step 2a is written and tested behind `CLIENT_TEXT_TOP20` (default off).** It lets the phone's name and number pick a card anywhere in the top 20 visual candidates, when they name exactly one card. A result that used the phone's number can never be `matched`.
5. **The gate was not evaluated.** Without a passing reproduction the off/on numbers cannot be trusted, so there are no time savings or wrong-card counts to report.

## Step 0: reproduction

| Set | Scans | Same status | Same first card | Both |
|---|---:|---:|---:|---:|
| Phone-input scans (26 Oct, phone corners and text replayed as recorded) | 201 | 147 (73%) | 136 (68%) | 114 (57%) |
| Android manual uploads (25 Oct, server's own text as the phone text) | 226 | 175 (77%) | 164 (73%) | - |

Gate: at least 95% on both. Not met.

Why it falls short:

- **Photos were resized when saved.** The review copy is 1600 pixels on the long edge. On the 201 phone-input scans the pipeline recorded an input size of 1363 x 1904 (or up to 1432 x 2000) for all 201, and the saved copies are 1145 x 1600 or similar. On the 226-scan set, 142 differ in the same way. The only remedy is to store the original upload bytes (or a hash plus the original) in the review record. That is a server change, and it is not part of this step.
- **The phone's embedding was not recorded.** Only a yes or no flag was stored. The embedding is read only by the stage 1 early-answer gate, which the runner does not run, so this does not explain the gap on its own.
- **The 25 Oct set has no phone corners or text on record.** Its runs use the server's own text as a stand-in. The 142 resized photos in that set are the likely reason for the 77%, but this has not been checked scan by scan.

The runner itself is in `api/scripts/full_bench/run_full.py`. It now has a `--phone` mode that replays the recorded corners, the phone's text with its confidences, and the route defaults (language `auto`, graded unset).

## Step 1: why the phone's text never skipped OCR

Counts from the 164 live staging scans on 26 October that sent text (from the staging log, matched against the stored records):

| Reason the skip was refused | Scans | Plain English |
|---|---:|---|
| `incomplete` | 86 | The phone sent no collector number (61 had a name only, 14 had a name plus candidate numbers, 11 had a number only). The rule needs both. |
| `low_confidence` | 75 | Both fields were there, but the name or the number was read below 0.9 (`CLIENT_TEXT_MIN_CONFIDENCE`). |
| `visual_floor` | 3 | Complete and confident, but the visual leader scored below 0.78. |
| `eligible` | 0 | Never reached. |

Scans that sent no text at all (37 of 201) cannot skip either.

So the answer is "never qualifies": the condition that fails is completeness (number missing) and then confidence. No scan was blocked by a late hint, and none reached the OCR step with a usable phone text and then ran OCR anyway. The phone's text arrives with the upload, before recognition starts.

## Step 2a: what changed

- `CLIENT_TEXT_TOP20` (default off) lets `ocr_skip_decision` look at the top 20 visual candidates instead of only the leader. It accepts exactly one card whose name matches and whose number fits (set totals applied), with one printing of that number in the catalogue. Two qualifying cards in the list (not aliases of each other) refuse the skip.
- The title read is kept: the footer mode still requires the server's own title read to agree with the phone before the phone's number is used.
- With the flag on, a result whose number came from the phone is capped at `uncertain`. The phone's text never makes a result `matched` on its own.
- Unit tests in `api/tests/test_client_text.py` cover the top-20 rule, the refusals, and the cap. All 66 tests in that file pass.

Because step 1 found that almost no phone text reaches the 0.9 and complete-number bar, this change can only apply to a small share of scans even when the replay works. Lowering the confidence bar or using the phone's number candidates would reach more scans, and both need their own replay before they are considered.

## Step 3: not run

Not measured: the off/on median and p90, the per-stage times, the status changes, the first-card changes and the wrong-card count. These need a runner that reproduces at 95% first. The gate result is therefore not evaluated, not failed.

## What is needed next

1. Store the original upload bytes (or a hash plus the original) in the review record, so the runner can replay what the pipeline saw. This is a change to the server's review store and needs the owner's go-ahead.
2. Re-run step 0 on those records. Only if it reaches 95% should the off/on measurement (step 3) run.
3. Decide whether lowering the 0.9 confidence bar or using the phone's number candidates is worth a replay.
