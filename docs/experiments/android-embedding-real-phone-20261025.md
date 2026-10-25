# Android LiteRT embedding on a real phone, staging replay — 25 October 2026

Draft PRs: PokeSingle #167 (app sends model id `2ddf6ec79e37/litert-fp16`) and ScanApp #72 (API accepts it). Nothing merged; the embedding stays off by default and needs `/config` opt-in. No thresholds were changed. Photos and OCR text are not in Git; only aggregates are recorded here.

## Setup

- Phone: Galaxy A55 (SM-A556B, Android 16), the only Android device connected.
- Release build: `flutter build appbundle --release` with `ANDROID_DINO_EMBEDDING_ENABLED=true`, isolated package `com.pokesingle.stage1validation` (your regular app untouched). The pinned `CardEmbedding.tflite` is gitignored on main; the SHA-verified copy from the main checkout (sha256 `fe0ca5d6…dbe1a`) was used and not committed. The AAB built (176.3 MB), the SHA check passed, and the build installed through bundletool local testing and launched without a crash.
- Replay: the earlier temporary corpus runner (uncommitted; copy in the shared notes folder) on a **debug** build of the #167 branch, because the runner refuses release builds and `run-as` needs a debuggable app. It runs the app's real gallery path (gallery quad detector, preview encoding, ML Kit text, LiteRT GPU fp16 embedding, upload) for the frozen 157-photo panel against **staging** (`staging-scan.pokesingle.com`, `/config` had client text/label/quality/embedding on). The validation package loads the model from a private file, not the Play asset pack.
- The run was split into several passes because the phone locked itself once (Android then blocks the app's network, giving `offline` failures) and the staging host name changed. Every photo has exactly one completed result; the reported scans all went to the same staging API container (started 13:25 UTC), whose logs were joined by scan id.

## Result (157 photos)

| Measure | Result | Gate |
|---|---:|---|
| Early answers | **21** (17 stage 1, 4 stage 1b) | about 25 expected with ML Kit text (45 only with PP-OCR) |
| Wrong early answers | **0** of 21 | 0 |
| Background checks | 21 of 21 found, all `agree=true`; **0** `agree=false` | 0 |
| Embedding delivered | **123 / 157 = 78.3%** (34 missing, all because the gallery detector found no card quad; 0 late) | >= 70% |
| Embedding time per photo (phone, includes readback) | p50 **125 ms**, p90 **166 ms**, max 437 ms (n = 123) | speed guard p90 <= 200 ms |

Reasons for no early answer (136 photos): `no_unique_text` 101, `artwork_miss` 15, `ambiguous_text` 8, `no_embedding` 7, `visual_contradiction` 3, `no_server_frame` 2. (`no_embedding` counts only photos that had no other reason; all 34 photos without an embedding went to the full pipeline.)

## Reading

- The safety gates pass: 0 wrong, 0 background disagreements, delivery 78.3%.
- The early-answer count (21) is below the roughly 25 the offline replay gave and far below the original 45 target, which assumed PP-OCR numbers (not enabled). The shortfall is text: 101 photos did not get a unique card from the phone text. The embedding path itself did not cause wrong answers. Compared with the 23 October A55 run (24 early answers), the count is similar.
- Embedding timing was measured in a debug Flutter build; the native LiteRT call is the same as in release, but Dart-side timings in this run (encoding, text) are slower than a release build would be and are not reported.

## What was not verified

- Release-mode model loading: the release validation build cannot be given the model file, so the embedding was not executed in a release build (R8/ProGuard effects on LiteRT are unchecked on device). Only launch without crash was confirmed.
- Play asset pack delivery (local testing split was staged, but the validation package loads from a file).
- Second phone: only the A55 was available, so the golden-fixture check (cosine >= 0.995) on another device was not run. The golden fixtures were also not re-run on this exact build; the last A55 values on file are minimum cosine 0.99828 (23 October) and 91/91 same-JPEG, same-quad comparisons >= 0.995 after the Android warp fix.
- Camera-concurrency, thermal and battery behaviour.
- Staging has `STORE_CAPTURES=true`, so the replayed photos are stored on staging; it should be switched off and the captures deleted (not done here: staging was not modified).
