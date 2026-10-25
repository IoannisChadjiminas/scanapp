# Plan: find the card in gallery photos and screenshots (PokeSingle app)

**Repo to change:** `~/StudioProjects/PokeSingle` (Flutter app). The ScanApp server needs no change for this.
**Goal:** a photo picked from the gallery, including a phone screenshot of an auction or Facebook listing, reaches the server with the card's corners (`card_quad`), the phone's text read (`client_text`) and the slab hint (`graded`), exactly like a live-camera scan does today.
**Approved by the owner.** The app isn't live yet, so this ships with the first store release.

## Why

Real staging scan `59c9f424` (2026-10-21 07:20 UTC, iOS, `capture=gallery`, `quad=none`, 923×2000 JPEG) of a slabbed ルギアex (`ja:CLF-017`) returned **"retake" after 15.8 s**. With no corners, the server took the whole screenshot as the card. Its name and number strips (the top 22% and bottom 18% of the image) held only the phone status bar (`11:38`, `1/5`) and the browser bar (`auctaro.com`, `36`), so it never read `ルギア` or `017/032`.

The server already does the right thing when it gets a card. The same image framed correctly gives `ja:CLF-017` on staging. Live-camera scans already send corners. **Gallery imports don't.**

## What the app does today

| Piece | Where | Today |
|---|---|---|
| Gallery import | `lib/features/scan/camera_screen.dart:800` `_gallery()` | `ImagePicker().pickMultiImage(maxWidth: 2000, maxHeight: 2000, imageQuality: 90)`, then `batch.enqueue(bytes, capture: ScanCapture.gallery)`. No corners, no holder flag |
| Corners sent to the server | `lib/features/scan/batch_controller.dart:300-311` | Only from `_cardsInView` (the live camera's outline). Gallery entries have none |
| Upload fields | `lib/data/scan_source.dart:76-95` `toFields()` | Sends `card_quad` (8 numbers, 0..1, from the top-left) and `quad_source=rect` when `cardQuad` is set |
| Text pass, slab check and client_text | `lib/data/scan_pipeline.dart:115-150` `_finalizeJpeg` | Runs on every scan; `cardTextFromText(..., cameraQuad: cardQuad)` uses the corners to read the card. Without corners, gallery hints are weak or missing |
| Holder (slab) flag | `batch_controller.dart:194-247` (`_holders`, `enqueue(holder:)`) | Set only by the live camera |
| iOS rectangle detection | `ios/Runner/CardWarp.swift` `quads(_ handler:, size:)` (line ~99), `cardRequest` (line ~60) | Already finds **card and holder shaped** rectangles (aspect 0.55–0.82) plus a document-segmentation shape, up to 6 candidates. Exposed only as `detectQuad`, which takes a **luma preview frame** |
| Dart card picker | `lib/data/card_outline.dart`: `detectQuad` (83), `cardInBox` (140), `holderShaped` (209), `holdsCard` (223) | Picks the card (or the card inside a holder) from the candidates for the live outline |
| Android | `android/app/src/main/kotlin/.../{ScannerCamera,StillPrep,CardText}.kt` | **No rectangle detection on Android** |

## Implementation

### 1. iOS: detect the card in a still image

In `ios/Runner/CardWarp.swift`, add a method-channel case **`detectQuadInImage`**:
- Input: `jpeg` (FlutterStandardTypedData). Optional `maxEdge` (default 1024).
- Decode with `CGImageSource` and downscale to `maxEdge` (the same pattern as `recognizeText`), then run the existing `quads(VNImageRequestHandler(cgImage:), size:)` on it.
- Return the same layout `detectQuad` returns: `[elapsedMs, confidence, x1, y1, x2, y2, x3, y3, x4, y4, …]`, with corners in 0..1 of the decoded image, top-left origin.
- Run it on the existing `queue`. Budget: **≤ 150 ms on a recent iPhone** for a 1024 px image (measure it).

### 2. Android: rectangle detection

Android has none today. Pick the cheapest option that adds no large dependency:
1. **Preferred:** a small Kotlin contour finder. Downscale to 512–768 px, grey, Canny or adaptive threshold, find contours, approximate polygons, keep convex quads with aspect 0.55–0.82 and area ≥ 4% of the image, scored by edge strength. Expose it as the same `detectQuadInImage` channel method with the same output layout.
2. If quality is poor, consider ML Kit **Document Scanner** detection only if it can run without UI, or OpenCV. **Report the APK size cost** (`flutter build apk --analyze-size`). Don't ship anything that adds more than about 3 MB without asking.

The iOS path is the priority. If Android takes much longer, ship iOS first and leave Android's gallery path unchanged (as today).

### 3. Dart: choose the card and attach it to the gallery entry

In `lib/data/card_outline.dart`, add `Future<GalleryCard?> detectCardInPhoto(Uint8List jpeg)`. It calls the new channel method and **reuses the live-outline rules** (`cardInBox`, `holderShaped`, `holdsCard`) to return:
- `corners`: for a raw card, the **card's** quad in 0..1 of the JPEG. For a graded card, **the slab (holder) outline**, as build 147 does. Don't send the card window inside the slab. Tested on 2026-10-21: the card-window quad made Lugia return the wrong card and made Charmander slower and only tentative. With the slab outline, both return the right card (`ja:CLF-017`, `en:sm3-18a`). The server reads the label and the card from the slab outline itself.
- `holder: bool`: true when the quad is a slab outline.

Selection rules for screenshots (the new cases):
- **Ignore the screen edges:** discard rectangles that touch the image border on two or more sides, or cover more than 95% of the image (the whole screenshot or the page).
- **Prefer the slab or card:** among candidates, prefer the slab outline when there is one; otherwise the largest card-aspect quad that isn't the slab **label** (a wide, short rectangle above the card) and isn't a thumbnail-strip item (small rectangles in a row near the bottom; require area ≥ 8% of the image).
- **On a tie,** prefer the quad nearest the image centre.

In `camera_screen.dart` `_gallery()` and `batch_controller.dart`:
- After reading `bytes`, call `detectCardInPhoto(bytes)` with a **250 ms deadline**. On timeout or no result, enqueue exactly as today.
- Pass the result into the batch entry: `ScanSource(cardQuad: corners)` (stored in `_sources[id]`, the same map the live camera fills), and `holder: true` into `enqueue(...)` so `graded=true` is sent.
- **The corners must refer to the uploaded bytes.** The gallery bytes go through `previewBytes` / `finalizePreparedPreview`. Check whether either changes the image (orientation, crop, resize). If it does, transform the corners the same way, or detect on the final JPEG instead of the picked bytes. Add a test that the corners still line up after preparation.
- When `prepared.warped` is true (iOS card warp), keep the existing rule: don't send the corners (`withCardQuad(null)`).

### 4. Text pass and slab hint for gallery imports

No new code should be needed. Once `cardQuad` is set, `_finalizeJpeg` passes it to `cardTextFromText(..., cameraQuad: cardQuad)`, so `client_text` is read from the card. The `holder` flag makes the slab check send `graded=true`. Verify both are sent for gallery imports with a unit or integration test.

### 5. Diagnostics

Record, in `ScanDiagnostics`:
- `gallery.quad` with `found`, `holder`, `elapsed_ms`, `candidates` and `reason` (`timeout`, `none`, `rejected_border`, `rejected_label` and so on)
- whether `card_quad`, `client_text` and `graded` were sent for the gallery entry

The server log line `scan_summary` will then show `capture=gallery quad=…`.

## Tests

1. **Unit tests for selection** (pure Dart, no device). Feed recorded candidate lists for:
   - **Lugia auction screenshot:** `/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/1299f40e-image.png`. Expected: the slab outline, `holder=true`. Not the label alone, not the thumbnail strip, not the whole page.
   - **Charmander CGC Facebook screenshot:** `/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/e1a30482-image.png`. Expected: the CGC slab outline, `holder=true`.
   - Two or three ordinary raw-card gallery photos, if the repo has any. Expected: the card itself.

   Record each image's candidates once on a simulator or device with the new `detectQuadInImage`, and save them as JSON fixtures. Copy the images into test fixtures only if the repo already keeps images there.
2. **Corner mapping:** the corners survive `previewBytes` / `finalizePreparedPreview` (orientation and resize).
3. **Fields:** a gallery entry with a detected card sends `card_quad`, `quad_source=rect`, `client_text` (when `/config` enables it) and `graded=true` for holders.
4. **Fallback:** on timeout or no detection, the upload is exactly as today.

## End-to-end check against staging

Post both screenshots through the app, or through the app's API client with the computed quad, to the **staging** scanner. It already runs the slab fixes `OCR_LABEL_NAME_FILTER`, `TEXT_IDENTITY_CANDIDATES` and `SLAB_LABEL_IDENTITY`. Expected:

| Photo | Expected result | Target time |
|---|---|---|
| Lugia slab screenshot | `ja:CLF-017` ルギアex, for confirmation | under ~6 s (it was 15.8 s, and "retake") |
| Charmander CGC screenshot | `en:sm3-18a` Charmander, for confirmation | under ~8 s (it was 13.8 s, and wrong) |

Report status, card_id and `total_ms` for each. Don't change any server settings.

## Done when

- `flutter analyze` is clean, and `flutter test` passes (existing plus new tests).
- iOS and Android release builds succeed.
- **App size before and after** is reported (expected about 0 MB on iOS; report the Android delta).
- Both screenshots give the expected cards on staging, with times reported.
- It's committed on a new branch with a PR in the PokeSingle repo. Don't publish to any store.

## Out of scope

- Live-camera scanning (already sends corners).
- Server changes. A separate ScanApp session is adding a full-image OCR fallback as a safety net for photos where the phone still finds no card.
- Moving the image model to the phone (tested; not worth it now).
