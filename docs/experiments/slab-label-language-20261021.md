# Slab label language and same-artwork twins: Lugia ex, Japanese vs English

Date: 2026-10-21. Branch `claude/slab-language-siblings`, from `origin/main` at 74de222 (PR #61 merged). Staging was only read: scan rows and API logs.

## The failure

After PR #61 was deployed, the user's app scans of the Lugia slab got worse: from an Inteleon suggestion to `retake` with nothing shown. The scans were `df0e5562` and `41abdcce` (09:56–09:57Z, build 147, gallery, 421,985 bytes, slab-outline quad).

What went right:
- Name selection worked: `LUGIA EX`, no longer `CLASSIC COLLECTION`.
- The label path found `ja:CLF-017` from `#17HOLO` + JP + LUGIA EX.

What went wrong:
- **Language:** the label text is Latin, so the scan's language came out as `en`.
- **Two candidates:** the numerator path (017/012 → 017 + "Lugia ex") proposed both `en:CLV-017` (the English Classic deck Lugia ex, 017/034) and `ja:CLF-017`. They share their artwork.
- **Only the twin verified:** verification is filtered by the scan's language, so only CLV was tried, and the real verifier verified it (53 inliers). Projection onto the upload then never ran for CLF, because one text candidate had already verified.
- **Retake:** CLV contradicts the footer read (017/012 against its 017/034). That gave `local_artwork_incompatible`, which became a retake with no suggestions, followed by a 5.6–8.6 s boundary retry that found nothing.

### Does ja:CLF-017's own reference verify on this upload?

Checked with the real `LocalArtworkVerifier` and the staging reference images.

| Frame | en:CLV-017 (reference 734×1026) | ja:CLF-017 (reference 500×698, the pokemon-card.com deck image) |
|---|---|---|
| Slab-outline frame, 923×2000 JPEG (q95/q97) | verifies, 50–51 inliers | **does not verify** |
| Upload with CLF's artwork projected (`propose_frame`) | 17–24 inliers | **verifies, 32–37 inliers** |
| Original PNG, slab frame | 51 | 50 |

CLF's reference is the small official deck image. On the app's re-encoded upload it yields too few keypoints on the slab frame, but it verifies once its own artwork is projected onto the upload. The pipeline has that projection, but skipped it here because the English twin had already verified.

## What changed (under `SLAB_TEXT_RECOVERY`, already on in both compose files)

1. **Label language decides.**
   - A label that names its language decides the language even when the card name on it is Latin: `2023 POKÉMON JP`, PSA's `JAPANESE`, or CGC/BGS `Japanese`.
   - Text candidates are restricted to that language, and it becomes the scan's ranking language (`frame_selection.label_language`).
   - So CLF-017 is the only candidate, is checked first and verifies by projection.
2. **Same-artwork twins.**
   - When a verified text candidate is in the wrong language, or a same-name candidate comes earlier in text order, the better-fitting twin leads. Both are shown as suggestions needing confirmation (`text_identity_language_sibling`).
   - Text order is label candidates first, then the numerator candidates sorted by how close their printed total is to the read one: 017/012 puts /032 before /034.
3. **Never an empty retake when verified artwork exists.** A text or label candidate whose artwork verified is returned for confirmation, even when a compatibility check fails (`text_identity_verified_review`). Status is then `uncertain`, so the boundary retry is skipped.
4. **The label beats an unverified visual guess.** Below the visual floor, a visual leader that no read name supports no longer outranks the label's candidates when nothing verifies. The candidates are shown for confirmation (the Inteleon case).

All earlier safety rules still apply: review-only, at most 3 suggestions, artwork verification first.

## Reproduction without mocking the verifier

- **Setup:** the real pipeline with real catalogue, verifier and reference images, on the Lugia screenshot re-encoded at 923×2000 (LANCZOS q97 and BICUBIC q95, the variants closest to the app's bytes) with the slab-outline quad. Staging's recorded OCR (df0e5562) stands in for the first read of the 784×1238 slab frame. The app's exact 421,985-byte file was never stored.
- **Main (74de222):** reproduces the staging result exactly: `retake`, no suggestions, CLV-017 verified (50 inliers), `local_artwork_incompatible`, boundary retry 2.1–3.1 s.
- **This branch:** `uncertain`, **ja:CLF-017** (verified by projection, 37 inliers), no boundary retry.

| Run | Status | Total ms | of which grading safety net | Boundary retry |
|---|---|---|---|---|
| main, q97 ×2, q95 | retake ×3 | 25,951 / 25,380 / 24,552 | 20,895 / 20,818 / 20,836 | 3,102 / 3,002 / 2,092 |
| this branch, same | ja:CLF-017 ×3 | 23,487 / 22,719 / 22,723 | 21,374 / 20,929 / 20,888 | 0 |

Recognition alone (total minus grading) goes from about 4.5 s to about 1.8 s. The grading safety net is a harness effect: it sends no `graded` hint, and the app sends `graded=true`.

## Tests and fixtures

- Fixtures: the recorded OCR of `df0e5562` and `41abdcce` join `862c09b5`, `ad1b8f19` and `072818fe`. With recovery, the label path gives exactly ja:CLF-017 for each.
- New pipeline tests use the real-world verifier behaviour (en:CLV-017 verifies on the slab frame; CLF-017 only after projection, or never):
  - with the label's `JP`: ja:CLF-017, no boundary retry, never a retake;
  - CLF never verifies: ja:CLF-017 still shown first, needing confirmation, never a retake;
  - no language on the label: the closer printed total leads, so ja:CLF-017 comes first and the verified en:CLV-017 second; both need confirmation.
- Full API suite: 878 passed, 4 skipped.

## Replay

Same 168 photos as PR #61 (155-photo panel, the Lugia and Charmander extras, 4 slab-outline and 3 card-window quads). Both arms ran with the deployed flags, baseline main versus this branch.

| | Answer changes | Field changes | Regressions | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|
| main (74de222) | - | - | - | 4,989 / 3,672 / 7,523 | 2,258 / 4,279 |
| this branch | 0 | 0 | **0** | 4,977 / 3,594 / 7,516 | 2,204 / 4,215 |

The new rules engage only when the label's language, a twin and the verifier interact as in the app's exact upload. The local re-encodes already ended on CLF-017 on main, so the panel shows no change. The fix is shown by the no-mock reproduction above.

## Caveats

- **ARM, not x86.** The reproduction ran on ARM with features computed from the images, not staging's x86 bundle. Staging also verified CLV (53 inliers), so the mechanism is the same; the exact inlier counts differ.
- **Projection's verdict on the real bytes is untested.** Whether CLF-017 verifies by projection on the app's exact upload can't be checked without its bytes. If it doesn't, rules 2–4 still show ja:CLF-017 first, needing confirmation.

## Recommendation

Merge, then rescan the Lugia slab from the iOS gallery with the slab outline. It should end on ja:CLF-017 (`frame_selection.label_language: ja`), with no boundary retry.
