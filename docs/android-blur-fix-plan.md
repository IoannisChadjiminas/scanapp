# Plan: reduce blurry manual captures on Android

**Repo:** PokeSingle (`~/StudioProjects/PokeSingle`). New branch from latest `origin/main`.
**Device:** Galaxy A55. **Rules:** every behaviour change behind its own switch (a build flag or `/config`), measured alone; no store publishing; open a PR, don't merge; `flutter analyze` clean and `flutter test` passing.

## Why

The owner's manual shots on the A55 often come out blurry, mainly because the phone moves right after the tap. Reading the code (PokeSingle `main` at `4d517d9`) shows several likely causes. **All of them need measuring before any is kept:**

1. **The shutter click sounds at the tap, not at the exposure.** `ScannerCamera.kt` `capture()` calls `shutter?.play(MediaActionSound.SHUTTER_CLICK)` and only then `capture.takePicture(...)`. The click is the user's cue "done", so they move the phone away while the exposure hasn't happened yet.
2. **Continuous autofocus may still be hunting at the tap.** The camera tracks `focusing` (CONTROL_AF_STATE_PASSIVE_SCAN / ACTIVE_SCAN) but `takePicture` doesn't wait for it.
3. **`CAPTURE_MODE_MINIMIZE_LATENCY`** is set on the `ImageCapture` (4000×3000, JPEG quality 95). It trades noise reduction and processing for speed, which can soften an image in dim light.
4. **The sharpness check only runs for auto capture.** `camera_screen.dart` `_captureNative` has `auto.quality` / `photoQualityProvider`, `settings.photoCheck` and `autoRetakes` for auto captures. A **manual shot goes straight to `_deliver` with no quality check**, so a blurry manual photo is uploaded and scanned.
5. **No "hold still" cue,** and the preview doesn't make clear when the capture has finished.

## Step 1: instrument (no behaviour change)

Add debug/profile-only diagnostics for **manual and auto** captures:
- time from the tap to the capture callback (`onCaptureStarted` if available in the bundled CameraX, and `onCaptureSuccess`)
- whether autofocus was still scanning at the tap (`focusing`) and how long it took to settle
- the sharpness of every captured photo (reuse `photoQualityProvider`), and the exposure time and ISO if CameraX gives them
- motion at the exposure: the gyroscope's rotation rate (a few samples around the capture), so blur from motion is separable from blur from focus

Record **20 manual captures of the same card on a stand, held still** (this separates focus and processing blur from hand motion), and **20 manual captures in hand with normal behavior**, with the diagnostics. Report the sharpness distributions and what correlates with low sharpness (AF still scanning, motion, exposure time).

## Step 2: fixes, each measured alone

A. **Click and haptic at the real exposure.** Play the shutter sound, and a short haptic, in `onCaptureStarted` (CameraX 1.4+; if the bundled version lacks it, play after `onCaptureSuccess`) instead of before `takePicture`. Keep the preview visible until the capture finishes (`capture.done`).
B. **Wait for focus.** If `focusing` is true at a manual tap, wait until it settles, at most **350 ms**, then capture. Before a manual capture also trigger a one-shot AF/AE meter on the card's center (`FocusMeteringAction`) and wait for the result, with the same cap. Report the added latency.
C. **Quality mode for manual shots.** Test `CAPTURE_MODE_MAXIMIZE_QUALITY` for manual captures only (auto capture keeps minimize-latency). Report the sharpness gain and the extra capture time on the A55.
D. **"Hold still" cue.** A short on-screen "Hold still" after the tap that disappears at `capture.done`, plus the haptic from A.
E. **Soft sharpness check for manual captures.** Run the existing sharpness measure on manual photos too. If it's below a threshold chosen from step 1's data, show "Looks blurry, retake?" with **"Use anyway"**. Never discard silently, and never block gallery imports.

Run A to E in this order. Keep a fix only if it **raises median sharpness or cuts the share of blurry shots** without adding more than about 300 ms to the tap-to-capture time. Don't change auto capture's behavior.

## Step 3: measure before and after

With the same owner, the same cards and the same stand, take **at least 30 manual captures before** (the current build) and **30 after** (all kept fixes), in hand. Report:
- the sharpness distribution and the share below the blur threshold
- the number-read rate (the app's own `number` / `name` read) and the text-pass time, before and after
- tap-to-capture time, median and p90
- a short note on anything that got worse

## Also found (a separate bug)

The **Android release build crashes on launch**: R8 strips `androidx.work.impl.WorkDatabase_Impl` (a Room-generated class). It doesn't show in a debug or profile build. The fix is a keep rule for androidx.work / Room in the Android proguard config. Write the stack trace and the fix in the PR description or a second PR, and **verify with a real release build on the A55** before any Android release. Don't ship Android without this.

## Done when

- **The diagnostics report** shows what causes the blur on the A55, with numbers.
- **Each kept fix** has a measured gain, and the ones that didn't help are listed and dropped.
- **Before and after** sharpness and number-read results are in the PR description.
- **`flutter analyze` and `flutter test` pass,** and the debug-only instrumentation is compiled out of release builds.
- **A PokeSingle PR is open,** not merged.
