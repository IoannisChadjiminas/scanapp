# Fourth untouched physical-photo holdout — 2026-10-02

**45/50 correct returned best matches (90%).** One wrong best printing and four
retakes/no best match. Correct printing in the best or returned alternatives:
46/50 (92%). All 13 automatic confirmations were correct; the wrong best was
explicitly printing-ambiguous and required user selection.

This independently tests the scanner after the third-batch generic fixes. It
does not repeat or tune those known photos. Scanner code hashes match
`physical-photo-holdout3-generic-final.json`; no scanner changes, threshold
changes, new vectors, mappings, deployment or database writes occurred here.
All 50 selected photos, including failures, were retained.

## Sample

114 public marketplace candidate images were downloaded privately and manually
reviewed on 19 contact sheets before inference. Fifty physical-card photos were
selected, covering 20 new printings and subjects: 42 English and eight Japanese;
26 Pokémon full-art, nine trainer full-art, 15 standard-frame. Different photos
of the same new printings are repeated: this is not 50 unique printings.
Slabs, sleeves, foil glare, stands, perspective, worn vintage cards and busy
packaging backgrounds are represented. Digital renders and multi-card
composites were excluded before scanner results existed.

No prior printing-ID, catalogue-name, exact-photo-byte or image-URL overlap;
no whole-image 256-bit difference-hash flags within Hamming distance 12 against
older downloads or the other selected photos. These checks cannot prove the
absence of all transformed-photo reuse or model-pretraining overlap. Labels
come from printed title, language and collector number, not search titles.

Frozen manifest SHA256:
`1e9694734f266f342b8db205dbe1ced5ec6f3df690b9008e071d1a6d566702a0`.

## Breakdown

| Slice | Correct best | Wrong best | No best |
|---|---:|---:|---:|
| All | 45/50 | 1 | 4 |
| English | 37/42 | 1 | 4 |
| Japanese | 8/8 | 0 | 0 |
| Pokémon full-art | 25/26 | 0 | 1 |
| Trainer full-art | 8/9 | 0 | 1 |
| Standard frame | 12/15 | 1 | 2 |

Statuses: 13 matched, 26 uncertain, seven printing-ambiguous, four retake.
Full-card-only and artwork-assisted passes had the same displayed-match counts;
this batch does not show an accuracy gain from the artwork retrieval stream.
Artwork-index truth coverage is 32/50 photos; full reference images exist for
all 20 printings. Blank and noise controls offered zero cards and made no
automatic claims. Four Japanese printing rows lack primary Cardmarket URLs;
helper/variant URL coverage was not evaluated here.

Serial local latency: median 4.42 seconds, nearest-rank sample P95 9.94 seconds,
maximum 12.64 seconds. No network, hosted HTTP or Flutter camera was exercised.

## Retained failures and initial diagnostic evidence

- **Zeraora VMAX GG42** (`holdout4_011`):
  [physical photo](https://www.ebay.co.uk/itm/334842178952).
  The correct card was in both shortlists and led internally, but inferred
  language conflicted with English. A retry also found the correct card but
  first-pass compatibility blocked presentation. Language/framing evidence
  needs investigation; an internal correct leader is not a displayed success.
- **Melony GG64** (`holdout4_023`):
  [slab photo](https://www.ebay.com/itm/364183662928).
  Strong glare and slab framing. OCR used the slab text `FA/MELONY`; title
  retrieval proposed the correct card despite its absence from both visual
  shortlists, but its original visual score was only 0.478. Boundary recovery
  still returned retake. No geometry verification supported acceptance.
- **Staryu 65/102** (`holdout4_058`):
  [holder photo](https://www.ebay.com/itm/176169588591).
  Correct card retrieved, but OCR read 55/102. A boundary retry produced a
  printing-ambiguous Staryu result; the retained first-pass number evidence
  prevented recovery. Need examine OCR region/read reliability, not broadly
  ignore conflicting printed numbers.
- **Abra 43/102** (`holdout4_067`):
  [slab photo](https://www.ebay.co.uk/itm/365909128525).
  Returned Base Set 2 Abra 65/130 as best instead of Base Set Abra 43/102. The
  true Base Set printing was among alternatives. The selected crop was small
  (195 × 273), with no usable name/number OCR, and local verification matched
  several shared-art printings. Response correctly retained printing ambiguity,
  but the best-printing ranking was wrong and counts as a failure.
- **Oddish 58/64** (`holdout4_072`):
  [packaging-background photo](https://www.ebay.com/itm/395449009259).
  OCR used background packaging text as the title despite reading 58/64. The
  correct printing missed the initial visual/artwork shortlists. Boundary retry
  found it but did not pass evidence checks. Background/title localisation and
  framing require investigation.

These are trace-based observations, not fully isolated root causes. No failure
was replaced, fixed or rerun with tuned code in this holdout. The observed drop
from the previous 48/50 unseen batch is real for these samples, but differing
composition and repeated identities prevent a claim of a population-wide
regression or a causal failure of the latest fix.

## Artifacts and limitations

- `internet-photo-holdout4-sources.json`: frozen labels and photo provenance.
- `physical-photo-holdout4-final.json`: completed paired run.
- `physical-photo-holdout4-presentation-audit.json`: actual returned-match audit.
- Private originals: `datasets/review/holdout4-frozen-20261002/photos/`.

Convenience marketplace sample, not population-random sampling; physical-copy
independence, authenticity, finish and pretraining overlap unverified. This is
unseen-photo local API accuracy, not a measured production or phone-camera
accuracy guarantee. It shows remaining OCR/framing and shared-art ranking
weaknesses despite no wrong automatic confirmations in this batch.
