# Plan: sharper footers for OCR on Android (steady gate, burst, multi-frame voting)

**Repo:** PokeSingle (`~/StudioProjects/PokeSingle`). New branch from latest `origin/main` (it has #161 and, once merged, #164 with the capture diagnostics and fixes A–E behind `BLUR_FIXES`).
**Device:** Galaxy A55 plugged in, screen on, Auto-Lock off.
**Rules:** every change behind its own build/`/config` switch and measured alone; auto capture and iPhone unchanged; `flutter analyze` clean; `flutter test` passing; debug-only instrumentation compiled out of release; open a PR, don't merge; no store publishing; photos and OCR text never in git.

## Goal

Raise the share of manual and auto camera scans where the phone reads the correct collector number (and name), with **0 wrong numbers**, without adding more than about **300 ms** between the tap and the capture, and keeping the text pass inside its **300 ms** live budget.

Evidence so far: on the A55 listing-photo panel only **46 of 102** labeled numbers were read, and extra footer crops added nothing (PokeSingle draft #162). On live manual shots the click sounds 330–750 ms **before** the exposure, so people move away and the photo blurs. Whether the real limit is blur or pixels is still being measured by the live-camera experiment.

## Measurement protocol (same for every idea)

- **Cards:** the owner's 10 physical cards (list in `docs/android-camera-test-cards.csv` as `card_label,name,collector_number,set_total,era`).
- **Per variant:** 30 manual in-hand captures (3 per card, mixed distance and light), same owner, same stand-free hand technique, same room.
- **Metrics per capture** (debug/profile only, from the #164 `[capture-diag]` line): sharpness, tap-to-capture ms, number read (catalogue-valid) vs the CSV (`correct`/`wrong`/`none`), name read, raw candidates, text-pass ms.
- **Report per variant:** sharpness median and share below the blur threshold, number-read rate, **wrong numbers (must be 0)**, name-read rate, tap-to-capture and text-pass ms (median and p90).
- **Baseline:** the build with all switches off. Keep any scans already taken by the live-camera experiment (`android-live-camera-numb`) as extra baseline data.

## Step 1: capture only when steady (cheap, no new capture work)

- Before `takePicture` on a **manual** tap, wait until the phone is steady: gyroscope rotation rate below a threshold (choose it from the #164 diagnostics) **and** the last preview frames' sharpness not dropping. Cap the wait at **400 ms**, then capture anyway.
- Combine with fix A from #164 (click and haptic at the real exposure) and D (hold-still cue). Measure `steady` alone, then with A+D.

## Step 2: burst, keep the sharpest

- On the tap, take **3 captures** back to back (CameraX `ImageCapture` in minimize-latency mode, about 100 ms apart, within a 350 ms total cap).
- Compute sharpness (reuse `photoQualityProvider` / the Laplacian-variance measure) on the card region of each frame, keep the sharpest, discard the rest. Run text reading and upload on the winner only.
- Measure with 2, 3 and 5 frames. Report the extra tap-to-capture time and the memory use. Abort the burst early when the first frame is already above a "sharp enough" threshold.

## Step 3: multi-frame footer voting while aiming (expected biggest gain)

- During aiming, run ML Kit on a **small crop of the footer** of the live analysis frames (about every 150 ms, only when the outline sees a card and the phone is fairly steady). Raise the analysis stream's resolution for this, if the card footer is too small in the current stream, and report the cost.
- Keep a short rolling window of the last 8–10 reads. A number counts only when the catalogue accepts it (with its set total, via the existing set-total check) and it was read in **at least 2 frames**, or in 1 frame with high confidence and agreement with the final photo's read. Vote the name the same way.
- At the tap, merge the vote with the still photo's own read. A valid number from the still always wins over a vote only if both agree or the vote is absent; if they conflict, send neither as `number` and put both in `number_candidates` (the server repairs and checks them).
- Respect the deadlines. Show nothing new in the UI. Battery: sample at most 6–7 reads per second, stop when no card is in view, and report CPU/battery impact (a 2-minute continuous aim test).

## Step 4: focus and exposure on the card (only if steps 1–3 leave blur or dim-light misses)

- **AF/AE metering on the detected card region** (not the screen centre), through `FocusMeteringAction`, before a manual capture (a short, capped wait).
- **Cap exposure time in dim light** (Camera2 interop: bias AE toward a shorter exposure and higher ISO, for example by asking for a 30 fps AE range for stills), and offer the torch when the preview is too dark. Compare sharpness in the dim-light and lamp-glare conditions.

## Out of scope for this plan

A second zoomed or 50 MP "footer shot" (heavier, only if the pixel-height analysis shows pixels, not blur, are the limit), and a number-only recognizer (`docs/android-footer-reading-plan.md` step 3).

## Done when

- Each idea has a measured result (kept with its numbers, or dropped with its numbers), all in the PR description.
- The kept combination shows a higher number-read rate than the baseline on the same 30 captures, **0 wrong numbers**, and tap-to-capture time within about 300 ms of baseline.
- `flutter analyze` and `flutter test` pass, instrumentation is compiled out of release, and the release build still launches on the A55.
- A PokeSingle PR is open and not merged.
