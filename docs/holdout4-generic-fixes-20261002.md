# Generic holder, framing and OCR recovery

Local scanner changes only. No card-specific names, catalogue IDs, URLs, photo
hashes or benchmark labels were added to recognition rules. No catalogue,
vector, mapping, PlanetScale or deployed-service changes were made.

The untouched fourth Internet-photo holdout scored 45/50 correct displayed best
matches, with four retakes and one wrong, review-required reprint. Its original
report and labels remain unchanged. The five targeted diagnostic reruns and
the completed whole-batch regression now return the correct best matches.

## Reusable changes

1. **Layout-aware title selection.** Printed stage/trainer badges anchor the
   following title instead of accepting a shop/packaging label above the card.
   A one-character-clipped long Basic Pokémon badge is recognized as layout
   boilerplate. Weak title retries require a materially stronger, compatible
   reading, including case-insensitive comparison. An inferred crop can reuse
   an agreeing, confident title from the original upload without deleting its
   weaker observation or contradicting a different confident title. If a name
   is missing but a reliable printed identifier exists, it stays unknown rather
   than being replaced by a holder title. An English holder title also cannot
   override visible Japanese/Korean/Chinese script evidence.
2. **Small-image and located OCR.** Small title/footer strips are interpolated
   before OCR. A full-frame fallback promotes text to name/collector evidence
   only when its returned bounding box actually lies in that region. Missing
   boxes remain unknown; arbitrary rules/footer text never becomes a title.
3. **Footer semantics.** Level/Pokédex and long descriptive prose do not produce
   synthetic collector identifiers; explicit fractions on those lines survive.
   A bounded, decorated gallery fraction with a repeated GG/TG namespace keeps
   that namespace. Bare/prefix-only IDs and inconsistent gallery namespaces are
   not rewritten into an invented fraction.
4. **Language evidence.** Multiple explicit English layout labels outweigh at
   most two incidental CJK footer symbols only when real localized phrases,
   kana/Hangul and longer CJK text are absent. Localized names are preserved.
5. **Holder interior and artwork-guided framing.** A lower portrait-aspect
   window avoids grading labels. On a non-quality framing retake, verified
   artwork keypoints can project the reference's complete outline into the
   original upload. Convexity, area, side-ratio and in-image checks reject
   implausible or missing corners. The warp samples the upload, never reference
   pixels, and preserves the better-sampled axis under foreshortening. It is a
   retrieval hypothesis, not proof of the reference's printing.
6. **Crop selection is not confidence scoring.** Up to eight line proposals and
   one artwork-aligned proposal are compared by their best retrieval score,
   above the unchanged OCR-assisted floor. A printing confidence gap no longer
   lets an earlier crop hide a slightly better crop. There is at most one extra
   full recognition evaluation; its title, language, collector, quality and
   first-pass contradiction guards still apply. Useful first-pass results are
   not replaced, and recovered proposals remain review-only.
7. **Separate artwork proof from edition ranking.** Local keypoint counts verify
   artwork, not which shared-art reprint wins. OCR/global ranking is preserved
   among geometrically verified, compatible references. An isolated #SKU next
   to a confidently read GEM MT grading label is separately tagged
   `holder_collector`: it may help rank an agreeing title, requires geometry or
   independent printed identity evidence, cannot veto a printed fraction, does
   not satisfy printing proof and cannot automatically confirm a match. Real
   footer evidence retains its region/confidence if the label repeats it.

The final match-confidence thresholds, full/artwork vectors, catalogue,
Cardmarket mappings and finish-selection policy are unchanged. Proposed crops
and holder labels never certify finish, authenticity or exact printing.

Versions: `rank-v13-holder-layout-review` and
`rapidocr-ppocrv6-small-regions-v6-located-frame`.

## Original failure diagnoses

| Photo/card | Root cause | Generic recovery | Required user decision |
|---|---|---|---|
| Zeraora VMAX GG42 | Two footer glyphs overrode clear English labels | Qualified language fusion | Confirm card |
| Melony GG64 | Grading slab selected; decorated gallery OCR and crop-order interaction | Interior recovery, gallery parsing, best crop selection | Confirm card |
| Staryu 65/102 | Pokédex N120 became a conflicting collector | Footer semantics and existing boundary retry | Select printing |
| Abra 43/102 | Holder outline/foreshortening; shared-art keypoint counts favored reprints | Artwork-guided warp, located title OCR and lower-trust holder SKU ranking | Select printing |
| Oddish 58/64 | Background label won; corrected crop clipped its title | Badge anchoring and agreeing original-title recovery | Confirm card |

None of these five targeted recoveries is an automatic `matched` response.

## Verification

Full suite: 553 passing tests, one pre-existing Starlette/AnyIO deprecation
warning. Forty-one cases in `test_holdout4_generic_fixes.py` and a new boundary
selection test cover evidence provenance, missing OCR boxes, localized text,
gallery namespaces, preserved printed-number conflicts, shared-art ranking,
holder hints without geometry, and missing-corner/reference-pixel rejection.
The whole-batch run caught and corrected a Japanese-card regression where a
missing title plus a readable collector fraction was supplemented with an
English holder label. The printed-identifier/unknown-title regression test
locks down that evidence precedence; the diagnostic photo recovered without
inventing or translating its title.

The four frozen 50-photo reruns use the same scanner revision, source labels,
image checksums, model, vectors and decision thresholds. They run locally with
no network, a read-only catalogue and in-memory scan results. Baselines reuse
the previous completed enabled-artwork results, not a new full-card-only run.

| Frozen batch | Before: correct displayed best | After: correct displayed best | Automatic matches: before → after | Wrong automatic matches |
|---|---:|---:|---:|---:|
| Fourth physical-photo batch | 45/50 | 50/50 | 13 → 14 | 0 |
| Third physical-photo batch | 50/50 | 50/50 | 16 → 15 | 0 |
| Second physical-photo batch | 50/50 | 50/50 | 12 → 11 | 0 |
| Earlier fresh physical-photo batch | 50/50 | 50/50 | 11 → 9 | 0 |

All 200 original photos, labels and checksums were retained. The same 18
scanner/runtime/schema/configuration/script hashes match all four completed
reports and the current checkout. There are five best-match gains and zero
best-match losses. All eight blank/noise control evaluations returned zero
suggestions and no automatic claim.

The final statuses are 49 automatic matches, 130 review-required matches and
21 printing-ambiguous matches; none is a retake. Four previous automatic
responses now request review while retaining their correct best match. One
previous review case, a clean Melony photo with its gallery identifier recovered,
now correctly confirms automatically. This is not 200 automatic confirmations.
OCR/layout changes can alter evidence confidence, and inferred holder crops,
missing mechanic suffixes and local geometry remain conservative review paths.

The scored identity is exact catalogue set/collector number/language, allowing
legacy English provider aliases only. These results do not establish exact
finish, printing stamp, authenticity or calibrated match probabilities. Some
truth rows still lack a primary Cardmarket URL; the audit records those gaps
separately, and mapping/helper coverage was not changed or re-audited here.

Reports and displayed-best audits:

- `physical-photo-holdout4-holder-v13-final.json`
- `physical-photo-holdout4-holder-v13-audit.json`
- `physical-photo-holdout3-holder-v13-final.json`
- `physical-photo-holdout3-holder-v13-audit.json`
- `physical-photo-holdout2-holder-v13-final.json`
- `physical-photo-holdout2-holder-v13-audit.json`
- `physical-photo-fresh50-holder-v13-final.json`
- `physical-photo-fresh50-holder-v13-audit.json`

This is tuned regression testing, not fresh evidence of 100% unseen-camera
accuracy. Source-manifest limitations describe their original untouched runs;
these reruns explicitly evaluate the now-tuned cases. Internet
marketplace photos are a convenience sample, not authenticated camera captures;
finish/authenticity are not ground truth. These are API recognition tests, not
deployed HTTP/Flutter camera tests. Concurrent local rerun latency is not a
production latency measurement. No staging deployment was performed.
