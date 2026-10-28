# Android: find the card automatically, like iOS (plan, 2026-10-26)

## Answer

Yes. The Android camera already has most of the path; the missing piece is the card finder.

- **iOS** finds card outlines in every camera frame with Vision (`ios/Runner/CardWarp.swift`: rectangle detector plus document segmentation). `ScannerCamera.swift` `captureOutput` streams the outlines and whether the lens is still focusing. `lib/features/scan/camera_screen.dart` `_maybeAutoCapture` fires the photo once the outline is locked, sharp, and not moving, so the user does not have to find the right distance or press the button.
- **Android** already sends the same message in the same words from `ScannerCamera.kt` (`look`): frame size, find time, focusing flag, sharpness, then per rectangle nine numbers and a 32-number colour fingerprint. Flutter handles it unchanged. What is missing is the finder itself: `var finder: CardFinder = CardFinder { emptyList() }` (`ScannerCamera.kt:208`) finds nothing, so the box stays red.
- Flutter turns the feature on only where `cardWarpSupported` is true (`lib/data/card_warp.dart:8`), which is iOS-only today, and `liveOutlineSupported` (`lib/data/card_outline.dart:16`) follows it. `ENABLE_CARD_WARP` defaults to false.

## What is missing

1. A finder that returns card-shaped quadrilaterals from the luma (Y) plane of each frame, in the 9-number format above.
2. Turning the feature on for Android behind the same `ENABLE_CARD_WARP` flag, default off.
3. Checking the photo crop on a live shot. iOS crops with a native `pokesingle/card_warp` call; Android has no such channel. The still-photo path on Android already finds cards in Dart (`detectCardInPhoto`), so the crop may reuse that. Confirm in step 0.
4. Measurement on the phone, then staging only if it passes.

## Detector options

| Option | What it is | Pros | Cons |
|---|---|---|---|
| **A. OpenCV (recommended)** | Canny edges, contours, polygon fit to four corners; aspect 0.62 to 0.82 and area at least 20% of the frame, as on iOS | Proven; a few ms per frame on the A55 at about 320 px; the server already uses OpenCV geometry | Adds a native library; keep it arm64-only and measure the APK size |
| B. Pure Kotlin | Own edge tracing and quad fit | No dependency | More code to get right, more bugs, slower to tune |

Expect Android to find cards less often than iOS at first. iOS also runs a document detector that finds cards in sleeves and in hands, and Android has no equivalent for live frames. Step 1 measures this before anything reaches the phone.

## Steps

0. **Read-only check.** Confirm how a live shot is cropped on Android (`framingForCard`, `detectCardInPhoto`) and whether the `focusing` flag is set from `CONTROL_AF_STATE` on main. Not a code change.
1. **Bench, no phone.** Run the chosen finder on stills with the gallery detector's quad as the reference (the 312-photo full-size corpus, `docs/experiments/internet-photo-test-fullsize-20261023.md`). Also run it on frames without a card (table, hand, empty box). Report the find rate, corner error against the reference, and false outlines. Photos stay out of git.
2. **Finder behind a flag.** `ANDROID_LIVE_CARD` (default off) in `ScannerCamera.kt`: implement `CardFinder`, unit tests on the bench fixtures. Draft PR.
3. **Flutter.** Let `liveOutlineSupported` and `cardWarpSupported` be true on Android when the flag is on. Check the auto-capture path against the iOS behaviour. Draft PR.
4. **Phone test (A55).** Same 8 cards, same lamp, auto-capture on. Record: time from the card appearing to the outline locking, number of automatic photos, number taken with no card in view, sharpness at the moment of firing, and the same measures for the manual quick press.
5. **Staging only if step 4 passes.** Read the staging records; no heavy jobs on the live container.

## Gates (proposal)

- 0 automatic photos with no card in view.
- Card found on at least 90% of frames with the card in view on the phone test, and at least 80% on the bench corpus.
- Automatic photos at least as sharp as the manual quick press (median).
- 0 wrong early answers and 0 background-check disagreements on staging.

## Rules

Each change behind its own flag, default off. Draft PRs, not merged without the owner's OK. Photos and OCR text never in git. No heavy jobs on the staging host (about 404 MB free). The camera PRs #180 (zero shutter lag, `z`) and #181 (continuous autofocus, `k`) are independent; step 4 works best with #181 for the focusing signal, but neither is required.
