# Phone text hints: can the phone's own OCR cut server CPU per scan?

Date: 2026-10-20. Branch `claude/device-hints-13ebd5`. Nothing was deployed or pushed, and staging
and production were not touched. Every new switch is off by default.

## Result

| Change | OCR passes saved | CPU per scan | p50 / p90 latency | Answer changes (card_id, status) | Verdict |
|---|---|---|---|---|---|
| `CLIENT_TEXT_FAST_PATH=true`: skip the optional OCR re-reads when the phone's name and number confirm a clear visual leader with one printing | **0 of 437** | 0.2% (6,584 to 6,574 ms mean locally; the noise floor is also 0.2%) | 2,555 / 5,199 to 2,533 / 5,148 ms (noise) | **0 of 155** (also 0 exact-field changes) | Safe, but saves nothing on this panel. Keep off. |
| `CLIENT_TEXT_HINTS=true`: read and log the hint only | 0 | 0 by construction | n/a | 0 | Switch on with the app change, to measure the phone's accuracy on real scans. |
| Not built: skip the server's *initial* footer read when the phone confirms a lone printing | up to ~1 of the 2 initial reads on about half the scans | upper bound roughly 5 to 10% locally | n/a | not measured; changes the evidence model | Worth a separate, designed experiment (see "Where the phone could still help"). |

The fast path never fired on a scan that had anything to skip. It fired on 19 of 155 photos, and
all 19 had only the two initial reads (title and footer) in the baseline. The 43 photos where the
server does run optional re-reads are the photos where the phone's read also fails, the card was
not found, or the visual answer is not clear. That is structural, not a tuning problem: the server
re-reads exactly when its own first read missed the collector number, read a weak title, or used
an inferred frame, and the same small, blurred, clipped or slabbed footer defeats the phone too.

The grading hint (`graded=false` skips label OCR, 24.5% less CPU, already the production default)
remains the only phone-side change with a large measured saving. Part A below shows the app sends
it, but only when its 300 ms ML Kit check answers in time.

## Part A: what the app already sends (PokeSingle at `20f5bc2`, read only)

| Field | Sent? | Evidence |
|---|---|---|
| `graded` | Yes, when `GET /config` returns `slab_detection: true` (server `APP_SLAB_DETECTION`), or the build sets `ENABLE_SLAB_DETECTION`. Only when non-null: the ML Kit (Latin) check of the unwarped photo has a 300 ms timeout and returns `null` when late, unsure, unsupported, or before the config has loaded. Photos the camera followed as a holder are always `graded=true`. | `lib/data/scan_price_settings.dart:184`; `lib/data/providers.dart:64-66`; `lib/data/scan_pipeline.dart:97-106`; `lib/data/slab_detector.dart:49-85`; `lib/data/repositories.dart:148` (plain) and `:290` (stream); `lib/features/scan/batch_controller.dart:354`, `:379` |
| `skip_detect` | Always, as `warped.toString()`. `warped` is true only when the iOS native warp ran (`app_card_warp` / `ENABLE_CARD_WARP`, 400 ms timeout; Android has no implementation). The server ignores it unless `TRUST_CLIENT_WARP`. | `lib/data/repositories.dart:146`, `:289`; `lib/data/card_warp.dart:6-9`; `lib/data/scan_pipeline.dart:100-102` |
| `card_quad` (+ `quad_source=rect`) | When the live camera saw the card and the crop keeps it (corners within -0.05..1.05 of the crop); dropped when the photo was warped. Eight comma-separated fractions, 4 decimals. | `lib/data/scan_source.dart:76-95`; `lib/features/scan/batch_controller.dart:200-226`, `:310`, `:340-343` |

So `GRADING_REQUIRES_CLIENT_HINT` does get its hint, except on the scans where the phone's check
was late or unsure; those are graded in full, as designed. How often that happens is not in this
repository; the phone records `slab.detected` / `slab.unsure` in its diagnostics, which reach
`POST /api/v1/diagnostics`. The check creates a new ML Kit recognizer and writes a temporary file
for every photo, which makes the 300 ms deadline harder to meet. `google_mlkit_text_recognition`
(0.17.1) is already in the app; its iOS plugin returns no confidence for any line.

## What was built (Part B)

- `client_text` on `POST /api/v1/scans` (multipart field, JSON, at most 512 bytes):
  `{"v":1,"engine":"apple-vision","name":"Blastoise","name_conf":0.98,"number":"14/100","number_conf":1.0,"ms":84}`.
  Strict validation in `api/app/recognition/client_text.py` (`parse_client_text`): known keys only,
  version 1, token engine name, name 1 to 64 printable characters with a letter, number in a
  collector-number shape that the server's own parser accepts (`TG01/TG30` is normalised to
  `TG01/30`), confidences in 0..1 or null, `ms` 0..60000. Anything else drops the hint and the
  reason is logged. It is read only with `CLIENT_TEXT_HINTS=true` or `CLIENT_TEXT_FAST_PATH=true`.
- Logging: one `client_text` line per hinted scan (`scan.diagnostics` logger) with the parse result,
  engine, which fields came, confidences, the number, and whether the phone's name and number
  agree with the server's top answer and with the server's own OCR, plus the fast-path outcome.
  The phone's title text is not logged; it is stored with the scan evidence (`ocr_json.client_text`).
  `req_client_text` is added to the scan summary flags.
- `CLIENT_TEXT_FAST_PATH` (default false), `CLIENT_TEXT_MIN_CONFIDENCE` (0.9). Decided before OCR on
  the first evaluation only (title and boundary recoveries always read in full). Eligible only if:
  both fields present and at least 0.9 confident; card-shaped frame (0.62 to 0.80); full-card leader
  at least 0.85 and 0.08 above the best other card in the leader's language (an alias id of the same
  card is not a rival); the artwork index has the leader at 0.80 or more; the phone's name matches
  the leader; the phone's number matches the leader's printed number; and the catalogue has exactly
  one printing of that name and language with that number. When the same artwork in another
  language is within 0.08 (common: Drowzee vs スリープ), the server's own first title read must also
  read the phone's name at 0.85 or more. Then, after the server's untouched first title and footer
  reads, a gate checks that they do not contradict the phone (no confident different title, no
  readable different number). Only then are the weak-header, wider-header, small-footer and
  footer-half re-reads and the original-upload re-read left out. A skipped number read marks the
  printing unconfirmed (`collector_retry_skipped`), exactly like the adaptive footer, so a skip can
  lower `matched` to `uncertain` and never the other way. The complete-frame probe is unchanged:
  when it is used it replaces the selected read rather than adding one.
- `GET /config` gains `client_text` (from `APP_CLIENT_TEXT`, default false) so the app can be told
  to send the hint without a rebuild.
- Tests: `api/tests/test_client_text.py` (parser, decision, contradiction gate, engine and cache
  behaviour, three pipeline-level cases) and a route test in `api/tests/test_scan_progress.py`.
  Full API suite: 779 passed, 3 skipped.

## Simulating the phone (Part B.3)

`api/scripts/vision_text.swift` (a small Apple Vision CLI: `VNRecognizeTextRequest`, `.accurate`,
no language correction, en-US + ja-JP) and `api/scripts/simulate_client_text.py`. Each panel photo
is cropped to the card the way the phone would after straightening: the server's own card detector
stands in for the phone's rectangle finder (103 photos); a card-shaped upload with no edge found is
read as uploaded, as the phone's framing crop would be (39); otherwise no hint (13). Vision reads
the crop; the name is the tallest word-like line in the top 20% after dropping badges, holder words
and HP; the number is a collector fraction or promo code in the bottom 20%. The hints are stored
next to the panel:
`data/latency/staging-reference027-20261003/device-text-hints-apple-vision-20261020.jsonl`
(and a `.fast` variant).

Hint quality against the expected catalogue card:

| Photos | Hint sent | Both fields | Name right / wrong | Number right / wrong | Both fields ≥ 0.9 and both right / not |
|---|---|---|---|---|---|
| 100 raw | 88 | 68 | 75 / 10 | 70 / 1 | 57 / 3 |
| 49 slab (with expected card) | 44 | 28 | 26 / 14 | 27 / 4 | 17 / 10 |
| 5 phone captures | 5 | 4 | 5 / 0 | 4 / 0 | 4 / 0 |

- Apple Vision reports confidence 1.0 on most lines, including wrong ones ("HP7O" as a name,
  204/197 for 204/193). Its confidence is not a safety signal; the agreement checks are.
- Slabs are weak: the top band of a slab is its label (grader, year, set), and the phone's crop
  there is the holder, not the card.
- Time: a median of 84 ms per card on an M4 Pro (p90 108 ms, max 258 ms), on a crop of about
  0.9 megapixels. Vision's `.fast` level took 14 ms but found both fields on only 28 raw cards and
  1 slab; not usable.
- Hint size: 101 to 128 bytes.

## Replay (Part B.4)

Local, on the M4 Pro, the setup of the 2026-10-19 experiment: staging's catalogue export (sqlite),
staging's artwork bundle `PS-CATALOGUE-EN-JA-SETH3-20261017`, staging's recognition flags
(`OCR_ADAPTIVE_FOOTER`, `OCR_COMPLETE_FRAME_FIRST`, `OCR_PARALLEL_REGIONS`, `OCR_CONFLICT_TITLE_RETRY`,
deadline grading, `GRADING_REQUIRES_CLIENT_HINT`), `ORT_INTRA_THREADS=2`, `DINO_INTRA_THREADS=2`, no
reference features (the x86 bundle is rejected on ARM). Every run sends the oracle `graded` hint
(today's production behaviour for an app that answers) and the simulated `client_text`; only the
fast-path flag differs. CPU is the server process tree's CPU time (`cpu_replay.py --server-pid`).
Local CPU-seconds are not server numbers; only differences carry over. The machine was shared
with other work (load average 5 to 9), so runs that are compared ran at the same time.

| Run pair (concurrent) | CPU mean / p50 / p90 (ms) | HTTP p50 / p90 (ms) | Correct | Answer changes |
|---|---|---|---|---|
| baseline vs baseline2 (noise floor) | 6,623 / 4,302 / 13,734 vs 6,611 / 4,237 / 13,731 | 2,513 / 5,255 vs 2,517 / 5,318 | 143/154 both | 0 (0 exact-field changes) |
| baseline4 vs fastpath4 (fast path on) | 6,584 / 4,320 / 12,654 vs 6,574 / 4,347 / 12,667 | 2,555 / 5,199 vs 2,533 / 5,148 | 143/154 both | 0 (0 exact-field changes); OCR passes 437 vs 437 |
| fastpath2 vs fastpath3 (fast path repeat) | 6,367 vs 6,391 | 2,501 / 4,816 vs 2,494 / 5,176 | 143/154 both | 0 (0 exact-field changes) |

The fast path's outcome per photo (refined gate; the first, stricter version measured the margin to
any runner-up and was eligible on almost no photo, because the runner-up is nearly always the same
artwork in the other language or the same card under a second id):

| Outcome | Photos | Of the 43 photos with optional re-reads |
|---|---|---|
| used (re-reads switched off) | 19 | 0 |
| no hint (no card found, or nothing read) | 18 | 11 |
| incomplete hint (no number, or no name) | 37 | 16 |
| visual margin not clear | 47 | 13 |
| artwork index weak or missing | 15 | 1 |
| low confidence | 9 | 2 |
| name or number disagrees with the leader | 7 | 0 |
| server's first read contradicts the phone | 2 | 0 |
| frame not card-shaped | 1 | 0 |

The optional re-reads cost 522 ms of the 1,795 ms of OCR pass time per scan in the baseline (29%),
spread over 43 photos: mostly the original-upload re-read (`original:initial`) and footer halves.
The answers on those 43 are where the expected-card misses and `printing_ambiguous` results live.
They are the scans that need the extra evidence.

Per-scan CPU differences between the fast-path pair are noise (p10 -147 ms, p50 +15 ms,
p90 +157 ms). An earlier fast-path run that was not paired showed 3.9% less CPU; that was the
machine getting quieter during its last 36 photos, not the fast path (the same 437 passes).

## Where the phone could still help

1. **Get the grading hint on more scans.** Every `null` `graded` costs a full label read (a third
   of scan CPU on raw photos in the 2026-10-19 panel). Measure the share of `slab.unsure` in phone
   diagnostics first. Then make the check faster: one recognizer kept alive, no temporary file,
   and one text pass shared with the card-text read (`docs/device-hints-app-plan.md`, section 6).
   This is likely the largest phone-side CPU lever left, and it needs no server change.
2. **Skip the server's initial footer read when the phone confirms a lone printing** (not built).
   The initial footer read is 752 ms of OCR pass time per scan here, against 522 ms for the title.
   About half the hinted scans (78 of 141 hint log lines) had a phone name and number that both
   matched the server's final answer. Dropping the footer read on those would be an upper bound
   of roughly 5 to 10% of local CPU, before the visual-margin and lone-printing conditions shrink
   it. But it changes what the server knows: the collector number would come only from the phone,
   so the existing rule that missing text never certifies a printing (as with
   `OCR_TITLE_ONLY_SINGLE_PRINTING`, off in production) must decide the status, and a frozen-panel
   replay on x86 must show no lost answers before anyone relies on it. This is the experiment to
   run next if more CPU is needed, and it keeps the rule that the hint never picks a card.
3. Keep `CLIENT_TEXT_FAST_PATH` off. It is safe on this panel (0 answer changes) but saved no work.
   It may matter for a different traffic mix (real phone photos are cleaner than eBay listings),
   which the `client_text` log lines will show before anyone switches it on.

## Staging replay (proposed, not run)

For final confirmation on x86 with reference features and the cloud catalogue, using the same
throwaway-container method as 2026-10-19 (stop the live staging API during the runs, `--cpus 2`,
fresh results database, scrapers and price jobs off, restart staging unchanged afterwards):

1. Build an image from this branch and start `bench-api` with staging's environment plus
   `CLIENT_TEXT_HINTS=true`. Copy the panel and
   `device-text-hints-apple-vision-20261020.jsonl` into the container.
2. `python scripts/cpu_replay.py --panel cases.json --root panel --hint --client-text hints.jsonl --out base.jsonl`
3. Restart `bench-api` with `CLIENT_TEXT_FAST_PATH=true` added; same command to `fast.jsonl`.
4. Repeat 2 and 3 once (noise floor), then `python scripts/compare_replay.py base.jsonl fast.jsonl base2.jsonl`.
5. Pass: 0 card or status changes, and the `client_text` log lines' `fast_path=used` scans' OCR pass
   counts lower than the baseline's. On this evidence the expected result is no saving, so this
   replay is only worth running together with the experiment in item 2 above.

## Limits

- One frozen panel of 155 eBay and user photos; not live phone captures. Real phone photos are
  framed by the app and usually sharper, which would raise hint coverage and could change the
  outcome table.
- Apple Vision on a Mac is a proxy for iOS; ML Kit on Android was not simulated.
- The phone's crop is simulated with the server's detector.
- Local ARM run without reference features; answers differ from staging on some photos (see the
  2026-10-19 report), but both sides of each comparison used the same setup.

## Files

- Server: `api/app/recognition/client_text.py` (new), `api/app/recognition/pipeline.py`,
  `api/app/recognition/ocr.py`, `api/app/recognition/ocr_cache.py`, `api/app/routes/scans.py`,
  `api/app/routes/health.py`, `api/app/config.py`, `api/app/scan_summary.py`.
- Scripts: `api/scripts/vision_text.swift`, `api/scripts/simulate_client_text.py`,
  `api/scripts/cpu_replay.py` (`--client-text`, records `scan_id`).
- Data (not in git, beside the 2026-10-19 data): the hints next to the panel, and the replay rows and
  comparisons in `data/latency/device-text-hints-20261020/`.
- App plan: `docs/device-hints-app-plan.md`.
