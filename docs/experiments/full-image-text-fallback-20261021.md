# Whole-image text fallback for screenshots with no card frame

Date: 2026-10-21. Branch `claude/full-image-text-fallback`, from `origin/main` at 8745804 (includes PR #59). Staging was only read: the scan row and `/root/bench/lugia-app.jpg`.

Follows `slab-text-identity-20261021.md` and `slab-label-identity-20261021.md`. It uses the same local replay setup.

## Result in one table

The 155-photo panel plus the Lugia PNG, staging's Lugia JPEG (`lugia-app.jpg`), the Charmander screenshot and three reproductions of the app failure: 161 photos.
- The baseline is today's deployed flags: `OCR_LABEL_NAME_FILTER`, `TEXT_IDENTITY_CANDIDATES` and `SLAB_LABEL_IDENTITY`.
- The variant adds `FULL_IMAGE_TEXT_FALLBACK=true`.
- Two replays were run; run 7 is the final code.

| | Answer changes (card or status) | Regressions | Fixed | Fallback fired | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|---|
| Baseline (run 7) | (run 6 vs run 7 baseline: 0) | - | - | - | 5,039 / 3,801 / 8,324 | 2,376 / 4,913 |
| + fallback (run 7) | 3 | **0** | the 3 app-failure reproductions | 4 of 161; **1 of the 155 panel photos** | 4,933 / 3,811 / 8,203 | 2,371 / 4,852 |

- Correct answers: baseline 152/160 labelled photos, with the fallback 155/160.
- The only fields that change on all 161 photos are the card and status of the three reproductions. Name, collector text, printing and grading are unchanged everywhere else.
- **Firing on the panel:**
  - One panel photo fired: `phone_ed6e6f2e-a6eb-4100-861d-810fa2f65a5b`, a phone capture with no card frame. Its whole-image read found nothing (`no_label`); the answer is unchanged and it cost 0.58 s.
  - The 100 raw camera photos and 50 slabs never fired.
  - The first version also fired when the selected crop was merely not card-shaped. That added 2 more panel photos (both unchanged) and was tightened to "the frame is the whole upload".

## The app failure

Staging scan `59c9f424` (2026-10-21T07:20:38Z, iOS gallery, `quad=none`, 923×2000, 421,985 bytes) returned `retake` in 15.8 s; the boundary retry alone took 8.6 s.
- No card frame was found, so the selected frame was the whole screenshot (`primary`, 923×2000).
- Its title strip (923×440) and collector strip (923×360) held only the phone status bar and the browser bar: `11:38`, `ıの`, `1/5`, `③ auctaro.com`, `36`.
- So neither the number+name path (`no_confident_fraction`) nor the label path (`no_label`) had anything to work with.
- The boundary retry then found a frame with ルギア but no number.

The same screenshot posted directly (PNG, or staging's 1179×2556 JPEG) works, because a different frame is selected. The app's bytes were not stored (`STORE_CAPTURES` off).

**Reproduction:** I degraded the Lugia screenshot near the app's size: 923×2000 (±3%), LANCZOS/BICUBIC/BILINEAR resampling, JPEG quality 60–97. Of 24 variants, 11 fail exactly like the app scan: whole-image frame, only status-bar/browser-bar lines in the strips, retake. The rest pass. Whether a variant fails depends on the exact bytes, not on quality as such. The variant closest to the app's upload fails: 923×2000, LANCZOS, q97, 451 KB.

## What changed (code default off; on in both compose files)

`FULL_IMAGE_TEXT_FALLBACK` (`api/app/config.py`; requires `TEXT_IDENTITY_CANDIDATES`).
- **When it runs (all must hold):**
  - the number+name and label paths found no candidate;
  - no card frame was detected, and the selected frame covers at least 85% of the upload;
  - the strips read no confident printed fraction;
  - the existing text gate is open: the visual top is below the automatic floor, or within the near-threshold margin under `SLAB_LABEL_IDENTITY`.
- **What it does:** one OCR read of the whole upload, downscaled to 1,400 px on the long edge (`read_whole_image` in `text_identity.py`). It takes 0.6–0.9 s locally and is logged as `ocr_passes` scope `full_image_text`.
- **How the read is used:**
  - Its lines go to the number+name path in a new "any fraction" mode. A whole screenshot also holds page counters such as `1/5`, so each fraction is tried on its own, and exactly one may lead to candidates. Otherwise it abstains.
  - If that finds nothing, the lines go to the slab-label path.
  - The language for these candidates comes from the whole-image read, so a Japanese card on an English browser page is not filtered out.
- **When it finds candidates:**
  - its lines join the scan's OCR record as region `full_image`, never as a title or footer collector;
  - its language decides ranking.
  - Every existing safety rule applies: local artwork verification, then projection onto the upload; review-only (`uncertain`, `requires_confirmation`); at most 3 suggestions.
  - A verified single candidate leaves the scan `uncertain`, so the boundary retry is skipped.
- **When it finds nothing:** the scan's evidence is untouched. Only the pass and `text_identity.full_image` (line count, ms, reason) are recorded.

## Time

Per photo, CPU / latency in seconds, from runs 6 and 7. Run 7 ran on a busier machine (its baseline was about 5% slower).

| Photo | Baseline | + fallback | Note |
|---|---|---|---|
| Lugia 923×2000 LANCZOS q97 (closest to the app) | 10.7–13.7 / 5.6–9.1, retake | 5.2–6.9 / 2.9–5.0, CLF-017 verified | boundary work 3.7–5.5 s skipped |
| Lugia 923×2000 BICUBIC q95 | 10.4–12.9 / 5.4–8.3, retake | 5.0–6.1 / 2.6–3.7, verified | same |
| Lugia 923×2000 q75 | 8.0–10.1 / 4.3–6.4, retake | 4.6–5.9 / 2.6–4.3, verified | same |
| Staging's Lugia JPEG (`lugia-app.jpg`, 1179×2556) | 9.0–10.6 / 5.1–6.9, CLF-017 | same | fallback not needed, does not fire |
| Charmander screenshot | 8.5–10.4 / 4.4–6.3, sm3-18a | same | the label path already finds it, so no fallback |

- On the three failing reproductions, the mean goes from 10.9 s to 5.6 s CPU (−49%) and from 6.5 s to 3.9 s latency (−41%).
- Projected for staging: that scan's 15.8 s included 8.6 s of boundary retry plus 2.5 s of proposals and selection. The fallback adds about one OCR read instead. This is not measured on staging.

## Regression fixture

- `api/tests/fixtures/text_identity_cases.jsonl` gains `lugia_app_gallery_923x2000`. It holds the failing variant's recorded first-pass OCR (status/browser bars only), its whole-image read and the 160-card catalogue neighbourhood. The test asserts:
  - the first pass reaches nothing on either path;
  - the whole-image read conflicts on `1/5` versus `017/032` in the old single-fraction mode;
  - "any fraction" mode gives exactly `ja:CLF-017`.
- Pipeline tests:
  - with the flag, the screenshot gets exactly one whole-image read (≤ 1,400 px), a verified CLF-017, no boundary retry, and `017/032` recorded as `full_image` evidence;
  - without the flag it stays a retake;
  - it never runs when a card frame was detected or the strips read a printed number.
- Full API suite: 858 passed, 4 skipped. The failing JPEG variants themselves stay out of git, as photos do elsewhere. They are generated from the Lugia screenshot as described above.

## Caveats

- **ARM, not x86.** The replay ran on ARM with on-the-fly reference features; see the earlier reports. Staging latency is projected, not measured.
- **The reproduction is an approximation.** The app's exact bytes are unknown. The fixture reproduces the same failure mode (whole-image frame, status-bar text only), not necessarily the same pixels.
- **The panel has few true screenshots.** The panel holds few photos where no frame is found. The fallback's firing rate on real gallery screenshots is expected to be higher than on the panel, and each firing costs one OCR read (~0.6–0.9 s locally).

## Recommendation

The flag is on in `compose.dokploy.yaml` and `compose.dokploy.production.yaml`, and the code default stays off, as PR #58 and #59 did. After deploy, rescan the Lugia screenshot from the iOS gallery and watch `text_identity.full_image` in stored evidence for how often it fires and finds candidates.
