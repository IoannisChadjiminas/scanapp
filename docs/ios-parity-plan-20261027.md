# iPhone: bring the Android scanning changes across (plan, 2026-10-27)

Goal: the iPhone 15 scans like the A55 does since today's rounds 5–11 and the provisional build: early answers on about half the photos, the bigger box with the card chips, the live reader, a sharper number read, and the phone's own provisional card.

## Where iPhone is today

| Change | Android (main, default) | iPhone today |
|---|---|---|
| Server: bare-number guard, phone-number agree rule, background check with phone inputs, original uploads | on | on (server side) |
| Name rules (CARD_NAME_RULES) | on | on in shared Dart; not tested on iPhone |
| Fingerprint for early answers | LiteRT, on time on most photos | Core ML, 27 ms, but in the gallery test the 250 ms deadline was missed on 42/90 and there was no card outline on 47/90 |
| Bigger box + chips (number, price, Cardmarket logo, Live/Trend/date) | on (`scanBigGuide()` is Android-only) | old box and strip |
| Live reader while aiming + live-name rule | on | exists (`IOS_LIVE_TEXT`, ScannerCamera.swift `readLiveText`), off |
| Sharp footer read from the full-size still + 250 ms extra | on | none |
| Outline fix for manual photos | on | own outline (CardWarp.swift), not checked against the Android fix |
| On-phone index search + provisional card | on (Android native CardIndex) | none |

## Rules

Each step behind its own switch, default off until its iPhone round passes, then on (owner's call). Draft PRs; the owner decides merges. Photos and OCR text never in git. Read-only on staging. Never uninstall the app on the iPhone; installs keep app data.

## Steps (one helper, in this order; each its own draft PR)

1. **Fingerprint on time and with an outline (iOS).** Find why the Core ML fingerprint misses its 250 ms deadline and why there is no outline on half the photos. Match Android: the same outline-first order, the deadline the server expects, and the upload making its own fingerprint when an early one is missing. Log `embedding.*` and `manual.quad` the same way as Android so the rounds compare. Switch: `IOS_EMBEDDING_FIX`.
2. **Bigger box and chips on iPhone.** Let `scanBigGuide()`/`scanMiniStrip()` apply on iOS (switches `IOS_BIG_GUIDE`, `IOS_MINI_STRIP`), check the layout on the iPhone 15 screen (box size unchanged with and without the strip; nothing covers the shutter) and that the crop, footer and live quads follow the box.
3. **Live reader on iPhone.** Turn on the existing iOS live text (`IOS_LIVE_TEXT`) with the same vote, name rules and live-name rule as Android; the text line to the device log only outside release builds.
4. **Sharp footer read on iPhone.** Read the collector number from a tight footer crop of the full-size still (Apple Vision), merged into the hint as Android does, within the same text budget plus the 250 ms extra. Switch: `IOS_FOOTER_FULLRES`.
5. **On-phone index search and provisional card on iPhone.** A Swift version of the index search (float16 dot products over 43,695 × 384 with Accelerate; target under 20 ms on the iPhone 15), the same card details file, and the same `phoneProvisionalDecision` rule and chip "checking" state. For the test, the four index files go into the app's support folder with `xcrun devicectl device copy to`. Switches: the existing `ON_PHONE_INDEX` / `PHONE_PROVISIONAL`, made to work on iOS.

## Test

One combined iPhone round at the end (16 photos, the same 8 cards), all five switches on, compared with the A55's rounds: early answers, fingerprint on time, outline found, numbers read, provisional cards and whether the server agreed, wrong cards (must be 0), background-check disagreements (must be 0). If a step fails, its switch stays off and the others go ahead.

## Not in this plan

Shipping the index and card details file to every phone (Play asset pack, iOS on-demand resource, versioned with the server's model and catalogue): a separate plan for both platforms.
