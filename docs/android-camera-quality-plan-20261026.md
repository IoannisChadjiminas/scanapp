# Android camera: sharper quick photos (plan, 2026-10-26)

Goal: quick presses (what most users do) produce sharp, readable footers, close to the stock camera. The stock camera's own image processing can't be matched; the aim is the closest achievable with public Android camera APIs, measured on the A55.

Repo: PokeSingle (`~/StudioProjects/PokeSingle`). Native camera: `android/app/src/main/kotlin/com/pokesingle/pokesingle/ScannerCamera.kt`. Dart switches: `lib/core/blur_fixes.dart` (`BLUR_FIXES` letters). Rules: every change behind its own build flag, default off until measured; open draft PRs, no merge without the owner; no photos or OCR text in git.

## Baseline (A55, 2026-10-26)

- Capture mode: `CAPTURE_MODE_MINIMIZE_LATENCY` (default), not zero-shutter-lag.
- Autofocus: CameraX default; a focus-settle wait exists (`b`, off by default); tap-to-focus at the card centre.
- Burst keep-sharpest (`h`, 3 frames) and fast shutter (`f`) exist in PR #165 (`claude/android-sharper-capture-c09842`), unmeasured.
- Number read on sharp shots: 4 of 6 (steady shots, footer build). Quick shots not yet measured.

## Steps

### 1. Measurement protocol first (required for every step)

- Cards: the 8 test cards (Pikachu 35/108, Brute Bonnet 123/182, Comfey 077/128, Charmander 9/108, Charmeleon 24/102, Zorua 095/128, Toxel 078, Capsule 159/182).
- Per variant: 3 quick presses and 3 steady presses per card. Record: blur (from the staging record), number read (`client_text.number`), top card, status, time to result.
- Light: same room, same lamp, recorded.
- Baseline first (current build), then each variant, same protocol.

### 2. Zero-shutter-lag capture (`z`)

- `ImageCapture.Builder().setCaptureMode(CAPTURE_MODE_ZERO_SHUTTER_LAG)` when the flag is on; fall back to minimize-latency if the device does not support it.
- Check `ImageCapture` binding succeeds on the A55 with Preview and ImageAnalysis bound; log the chosen mode.
- Gate: quick-press blur at least as good as steady presses on the baseline, no crash, capture delay not worse.

### 3. Explicit focus before the shutter (`a`)

- Use Camera2 interop to set `CONTROL_AF_MODE_CONTINUOUS_PICTURE` on Preview and capture.
- Before capture, wait for `CONTROL_AF_STATE` to be FOCUSED_LOCKED or PASSIVE_FOCUSED, with a cap of about 400 ms; then take the photo.
- Gate: quick-press blur up; the 400 ms cap never exceeded by more than 10% of presses.

### 4. Focus on the footer (`t`)

- When the user taps, focus on the bottom of the card (the number), not the centre.
- Also run a continuous focus region on the lower third of the guide.
- Gate: number read rate on quick presses up vs step 3.

### 5. Burst keep-sharpest (`h`, from #165) on quick presses

- Burst of 3 frames, keep the sharpest by Laplacian variance over the card area.
- Gate: no added wait beyond about 150 ms; number read rate up on quick presses.

### 6. Vendor extension mode (optional, check first)

- CameraX `ExtensionsManager` with `AUTO` mode, only if the A55 supports it. Check support and the resolution it allows before any build.
- Gate: only if steps 2 to 5 leave a clear gap to the stock camera on the same cards.

### 7. Guidance (later, UI)

- "Move closer" when the card is under about 30% of the frame; "hold still" only when blur is high; "tilt to remove glare" when glare covers the footer. Not for quick presses, since it adds friction.

## Order and exit

Steps 1, 2, 3, 4, 5 in order, one flag each, one build each. Stop when quick-press number read is at least as high as steady-press read on the baseline, or when a step shows no gain. Report each step with the table from step 1.

## Not covered

- Stock-camera parity: not achievable with public APIs; the goal is the closest measurable gain.
- iPhone: its live text and auto capture already exist; this plan is Android only.
