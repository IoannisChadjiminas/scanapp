# Third untouched Internet physical-photo holdout — 2026-10-02

Result: **48/50 correct returned best matches (96%)**, zero wrong best matches,
two no-result/retake responses. All 16 automatic confirmations were correct.
This is a new holdout result, not a tuned regression result or a claim of 96%
accuracy across all phone scans.

## Sample and integrity

Fifty marketplace photos of physical cards, selected from 107 visually reviewed
candidates before inference. They cover 27 printing IDs: 36 English photos and
14 Japanese photos, 34 Pokémon full-art, eight trainer full-art and eight
standard-frame photos. Repeated new printings appear under different conditions;
these are not 50 distinct printings. Slabs, sleeves, stands, foil reflections,
handheld perspective, vintage cards and a busy background are represented.

No overlap with previous photo batches by printing ID, catalogue name, image URL
or exact bytes. No whole-image 256-bit difference-hash flag within Hamming
distance 12 against older downloads or other selected photos. This does not
prove the absence of every transformed crop, stock-photo reuse or pretraining
overlap. Physical authenticity and finish are not verified ground truth.

Labels use visible printed title, language and collector number, not search
titles. Several search hints were incorrect and corrected before inference.
Frozen source manifest SHA256:
`1eda7f1ee8b2c6fb1bb0ce2efa6735c8ca411c2040b1149d09629bef4dd9fc9a`.

All 50 retained. The audit verifies labels, image hashes and unchanged scanner
code relative to `physical-photo-holdout2-generic-fixes-final.json`. No tuning,
reference indexing, thresholds, database writes or deployment occurred here.
The local offline API pipeline ran with read-only reference mounts and no
network. This does not test deployed HTTP services or Flutter camera capture.

## Returned results

| Slice | Correct best | Wrong best | No best |
|---|---:|---:|---:|
| All | 48/50 | 0 | 2 |
| English | 35/36 | 0 | 1 |
| Japanese | 13/14 | 0 | 1 |
| Pokémon full-art | 33/34 | 0 | 1 |
| Trainer full-art | 7/8 | 0 | 1 |
| Standard frame | 8/8 | 0 | 0 |

Correct card in best or returned alternatives: 48/50. Response statuses: 16
matched, 29 uncertain, three printing-ambiguous and two retake. Thus 32 correct
best matches still require review; correct ranking is not confirmed printing
certainty. Blank and noise controls offered no cards and made no automatic
claims.

Full-card-only also scored 48/50, with the same two retakes. Artwork-assisted
retrieval did not add correct best matches on this batch. The artwork index
contains the truth for 29/50 photos; the full-card reference exists for all
27 printings. Thirteen printing rows have no primary Cardmarket URL, a separate
catalogue completeness issue; helper/variant URL coverage was not audited here.

Local artwork-assisted latency: median 4.50 seconds, nearest-rank sample P95
10.38 seconds, maximum 17.16 seconds. These are serial local benchmark timings,
not a hosted-service latency guarantee.

## Retained failures for follow-up

- `holdout3_095`: English Regigigas VSTAR GG55/GG70,
  [source photograph](https://www.ebay.com/itm/256810665752).
  Correct English printing absent from both initial shortlists. Internal leader
  was Japanese `ja:S12a-233`, conflicting with English OCR; returning no card
  avoided presenting the wrong language. No reliable collector number was read,
  and the boundary retry did not provide a compatible recovery. Retrieval and
  framing need further investigation, not simply a looser confidence threshold.
- `holdout3_107`: Japanese Lacey 131/102 SAR in a PSA slab,
  [source photograph](https://www.ebay.com/itm/226284954118).
  Correct card led the full-card search at similarity 0.877; local geometry
  yielded 84 artwork inliers and OCR read 131/102. Nevertheless no best match was
  exposed. OCR used the supporter instruction as the name, framing remained
  unverified, and the retry compatibility check rejected an uncertain recovery
  of the same card. These traces suggest an evidence/presentation guard issue;
  root cause is not yet established by a regression test. This counts as a
  failure despite the correct internal leader.

Neither failure was replaced, fixed or rerun with tuned code in this holdout.

Artifacts: `internet-photo-holdout3-sources.json` (labels/provenance),
`physical-photo-holdout3-final.json` (paired completed run), and
`physical-photo-holdout3-presentation-audit.json` (returned-match audit and
retained failures). Private original photo bytes remain under
`datasets/review/holdout3-frozen-20261002/photos/`; they are not published.
