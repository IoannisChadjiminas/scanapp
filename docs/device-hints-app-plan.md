# Device text hints: what the PokeSingle app needs to change

**For:** the Flutter app (`PokeSingle`, separate repository)
**Server side:** this repository, `client_text` on `POST /api/v1/scans`, flags `CLIENT_TEXT_HINTS`,
`CLIENT_TEXT_FAST_PATH`, `CLIENT_TEXT_OCR`, `APP_CLIENT_TEXT` (all off by default)
**Measured basis:** [experiments/device-text-hints-20261020.md](./experiments/device-text-hints-20261020.md)

The phone reads the card's printed name and collector number on the device, for free, and
sends what it read with the photo. The server never lets that text choose a card. It uses it
only to skip its own optional OCR re-reads when the phone confirms the server's clear visual
answer. A wrong, late or missing hint costs nothing but the saving.

**Priority, from the replay:** the fast path built so far saved no server OCR on the frozen
panel (the photos where the server re-reads are the ones the phone cannot read either). The
phone change that is worth most today is making the existing slab check answer more often
(section 6, "Do it once"), because every scan without `graded` pays for a full label read. The
card-text hint is worth shipping alongside it, in the same text pass: with
`CLIENT_TEXT_OCR=footer` the server skips its own footer read when the phone's name and number
confirm the visual answer, which saved 4.4% of server CPU on the replay with no wrong answer, and
the `client_text` log lines measure the phone's accuracy on real captures first. Every hint that
is missing a field (55 of 155 panel photos) is a scan where that saving cannot happen, so the
number read in section 4 is the part worth tuning.

## 1. What the app does today (PokeSingle at `20f5bc2`)

| Field | Sent? | Where |
|---|---|---|
| `graded` | Yes, when `GET /config` has `slab_detection: true` (server `APP_SLAB_DETECTION`) or the build sets `ENABLE_SLAB_DETECTION`. ML Kit (Latin) reads the unwarped photo, 300 ms timeout; `null` (field left out) when unsure, late or unsupported. A photo the camera saw as a holder is always sent as `graded=true`. | `lib/data/scan_price_settings.dart:184`, `lib/data/scan_pipeline.dart:97-106`, `lib/data/slab_detector.dart:49-85`, `lib/data/repositories.dart:148` and `:290`, `lib/features/scan/batch_controller.dart:354` and `:379` |
| `skip_detect` | Always, equal to "the phone straightened the card" (iOS only, when `card_warp` is on). The server ignores it unless `TRUST_CLIENT_WARP`. | `lib/data/repositories.dart:146` and `:289`, `lib/data/card_warp.dart:7-9` |
| `card_quad`, `quad_source=rect` | When the live camera saw the card and the crop kept it; dropped when the photo was straightened. | `lib/data/scan_source.dart:76-95`, `lib/features/scan/batch_controller.dart:200-226`, `:310`, `:340-343` |

So the server's grading skip (`GRADING_REQUIRES_CLIENT_HINT`, 24.5% less CPU on the replay) works
today, but only for scans where the ML Kit check answers inside 300 ms. Every `null` is graded
in full. The share of `slab.unsure` among `slab.*` phone diagnostics is the number to watch; the
check also opens a new recognizer and writes a temporary file for every photo, both of which eat
into the 300 ms (section 6).

`google_mlkit_text_recognition` (0.17.1) is already a dependency. Its iOS plugin returns
`confidence: nil` for every line and element; Android returns a confidence.

## 2. The server contract

`client_text` is one extra multipart field holding a JSON object, at most 512 bytes:

```json
{"v":1,"engine":"apple-vision","name":"Blastoise","name_conf":0.98,"number":"14/100","number_conf":1.0,"ms":84}
```

| Key | Rule |
|---|---|
| `v` | `1` |
| `engine` | lower-case token, `[a-z0-9._-]`, at most 32: `apple-vision`, `mlkit-latin`, `mlkit-japanese` |
| `name` | the printed card name as read, 1 to 64 characters, at least one letter, no control characters; or `null` |
| `name_conf`, `number_conf` | 0 to 1, or `null` when the engine gives none |
| `number` | the collector number as printed: `14/100`, `045/198`, `TG01/TG30`, `GG01/GG70`, `SWSH050`, `SVP 045`; or `null` |
| `ms` | how long the phone's read took, an integer 0 to 60000 |

Any other key, a wrong type or an out-of-range value drops the whole hint (logged with the
reason). Send only what was read; leave a field `null` rather than guessing.

The server reads `client_text` only with `CLIENT_TEXT_HINTS=true` (log only) or
`CLIENT_TEXT_FAST_PATH=true`. `GET /config` returns `client_text: true` when `APP_CLIENT_TEXT=true`;
the app sends the field only then, like `slab_detection`.

The fast path needs both fields with confidence at least `CLIENT_TEXT_MIN_CONFIDENCE` (0.9). A
`null` confidence counts as low, so on Android with ML Kit the hint is useful, and on iOS it is
only useful from Apple Vision (ML Kit gives no confidence there).

## 3. Which engine

| Platform | Engine | Why |
|---|---|---|
| iOS | Apple Vision `VNRecognizeTextRequest`, `.accurate`, `usesLanguageCorrection = false`, `recognitionLanguages = ["en-US", "ja-JP"]` | System framework: no download, no app size. Gives a confidence. `CardWarp.swift` already imports Vision and uses a method channel; add a `recognizeText` method beside `detectAndWarp`. The `.fast` level missed the collector number on most cards in the simulation; do not use it. |
| Android | ML Kit Text Recognition v2, the plugin already in the app | On device, free, gives a confidence on Android. Latin script covers English cards; Japanese cards need the Japanese script recognizer (`TextRecognitionScript.japanese`), which adds a model. Check the size it adds with `flutter build apk --analyze-size` before shipping it, or ship Latin only first (it still reads numbers on Japanese cards). |

Both run on the device's own CPU/NPU; neither sends the image anywhere.

## 4. What to read

Read the card, not the photo. Use the card the app already found:

1. When the phone straightened the card (`warped`), read the straightened JPEG.
2. Otherwise, when the live camera gave the card's corners (`cardQuad` in crop coordinates),
   read the uploaded JPEG and map each recognised line's box centre into card space with the
   quad's perspective transform.
3. Otherwise, when the crop itself is card-shaped (width / height 0.62 to 0.80), read it as the card.
4. Otherwise send no hint.

Then, in card space (0 at the top, 1 at the bottom), apply the same rules as
`api/scripts/simulate_client_text.py`:

- **Name:** among lines whose centre is in the top 20%, drop stage badges (`BASIC`, `STAGE 1`,
  `TRAINER`, `たね`, ...), holder words (`PSA`, `BGS`, `CGC`, `TAG`, `GRADE`, `MINT`, ...) and any
  `HP 120` text, strip a leading badge from the line (`STAGE1 Parasect`), and drop lines with
  fewer than 3 letters (2 for Japanese) or at least as many digits as letters (the styled
  "HP 70" glyph is the tallest thing there). Send the tallest remaining line.
- **Number:** among lines whose centre is in the bottom 20%, find a fraction
  (`\d{1,4}/\d{1,4}`, optionally with a `TG`/`GG`-style prefix) or a promo code
  (`SWSH050`, `SVP 045`, `SM35`, ...). Read a letter O as zero inside `TG`/`GG` numbers. Send
  the most confident match.

Port these rules to Dart as a pure function with unit tests; the simulation's raw Vision lines
for the 155-photo panel are a ready fixture set.

## 5. When to send

- Only when `GET /config` returns `client_text: true`.
- Only when the card was found (rules 1 to 3 above).
- Start the read as soon as the final still is chosen, in parallel with the JPEG encode, the
  warp and the slab check, exactly like `detectSlab` today. Never delay the upload for it:
  give it a deadline (below) and upload without the field when it is late.
- Send whatever was read, even one field. The server logs agreement for every hint, which is
  how the rollout measures the phone's accuracy before the fast path is switched on.
- Record `client_text.done` / `client_text.late` in `ScanDiagnostics` with `elapsed_ms` and which
  fields were found, so `/api/v1/diagnostics` shows phone cost and hit rate.

## 6. Size and latency budget

- **Upload size:** the field is about 100 to 130 bytes of JSON. Nothing else changes.
- **App size:** iOS adds nothing (Vision is a system framework). Android adds nothing for
  Latin (already shipped for slab detection); the Japanese recognizer adds a model (measure).
- **Time:** Apple Vision `.accurate` on the straightened card took a median of 84 ms
  (p90 108 ms, max 258 ms) per card on an M4 Pro Mac in the simulation. A phone will be
  slower; budget **250 ms** on iOS and **300 ms** on Android (the slab check's budget), measured
  from the still being ready, and drop the hint when it is later. Read a crop no larger than
  about 1,200 px on the long edge.
- **Do it once:** the slab check and the card text are both text recognition. Run one
  recognizer pass on the photo and use it for both: the slab classifier wants every line, the
  card hint wants the lines inside the card quad. Keep one recognizer instance alive between
  photos instead of creating and closing one per photo, and pass the bytes rather than writing a
  temporary file where the platform allows. Together that likely brings both checks inside the
  budget more often, which also raises the share of scans that get the grading skip.
- **Battery:** one text recognition per photo, which the slab check already pays.

## 7. Rollout

1. Ship the app change behind `client_text` from `GET /config` (off).
2. Server: `APP_CLIENT_TEXT=true`, `CLIENT_TEXT_HINTS=true`. Read the `client_text` log lines for a
   week: parse failures, how often name and number agree with the server's answer, per engine.
3. Replay the frozen panel on staging with the fast path (section "Staging replay" in the
   experiment report). Only then consider `CLIENT_TEXT_FAST_PATH=true`.
