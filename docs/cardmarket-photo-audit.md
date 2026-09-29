# Cardmarket unmatched-photo audit — 26 September 2026

## Latest manual review — 27 September 2026

The user requested direct visual analysis without DINOv2. The latest deliverable
is `exports/matching-audit/manual/final.html` (local cached assets), with a
self-contained copy at `manual/standalone.html`. The earlier vector-ranked page
is superseded as the review deliverable; no scores/ranks were used in this pass.

The report includes all 3,400 products with stored photo URLs and explicitly
separates inspected photos from metadata-only triage. Across the saved manual
passes, 817 distinct listing photos were inspected. All 385 existing pairs with
available official art, excluding the 72 known language conflicts, were compared
on `manual/linked-1.jpg` through `linked-20.jpg`; artwork/language/layout agree.
The 72 conflicts were individually compared on `manual/wrong-1.jpg` through
`wrong-4.jpg`: same artwork, Japanese listing versus English catalogue print.
The other 84 existing photographed links lack official art and remain unverified.

One additional exact visual proposal is Japanese Metal Energy, `ja:S8a-MET`,
linked to `25th-Anniversary-Collection/Metal-Energy`. Its official art and listing
agree in the Japanese label, energy symbol/background, 25th logo and `s8a MET`
marking. Its catalogue name is `Unknown`; the intended display name is Metal
Energy. This raises the combined proposal total to **165**: 96 visually checked
without a collector correction, one visually checked M Tyranitar proposal
requiring the existing 089/081 → 090/081 correction, and 68 metadata-only proposals.
N BW100 and M Tyranitar were re-inspected directly; previous vector scores were
not imported into the manual decisions.

The 33 English 30th Celebration photos were inspected. **28 provisional**
name/stamp candidates correspond to unique entries in `en:30th-c`, but those
records lack official images and use sequential numbers instead of the printed
original-set numbers. The current TCGdex set endpoint was fetched and confirms
that catalogue structure; it does not establish exact print mappings. Two
Darkrai & Cresselia halves cannot be assigned to the two same-name entries;
three Mew colour variants are absent from that catalogue set. Do not apply these
28 provisional candidates as verified links.

Also inspected: all 39 anniversary photos, 56 selected BW/movie/ADV promo photos,
and 137 Battle Academy 2020 card photos. Missing Japanese promo/deck records,
oversized cards, and stamped Battle Academy prints were kept separate from
ordinary cards with similar artwork. This was not a complete manual inspection
of the remaining images: 1,800 photo rows retain unresolved metadata triage,
and 576 source photos remain unavailable (403/no cache).

Current database counts were independently rechecked: **42,457 unlinked products**,
**2,859 unlinked products with photo URLs**, and **39,598 unlinked without photo
URLs**. There are still 11,488 catalogue records without official images. All
165 proposals remain unapplied. No database links, matcher code, vectors, source
card metadata or published Gists were changed by this manual review.

Machine-readable decisions are in `manual/decisions.json` and the 165 proposals
in `manual/proposed-matches.json`. Regenerate from the saved evidence with
`python3 scripts/build_manual_cardmarket_review.py`. The builder never invokes
an embedding model and contains no database writes. Counts, URL/card uniqueness,
proposal state and cached-image availability were checked; the final report's
search and paired image rendering were verified in the browser.

---

The old Gist comparisons are candidate suggestions, not approved print matches.
The audit reviewed metadata for all **2,931 currently unlinked products with listing
photos**, using a read-only export of the local running catalogue. It proposes
**162 links** and changes no database records. The input snapshot had 42,921 unlinked products overall; this work covers the
photographed subset. See the live-update note below for concurrent changes.

| Proposed identity matches | Count | Official images visually compared |
| --- | ---: | ---: |
| Base Set 2 | 90 | 90 |
| BW Trainer Kit | 59 | 0 |
| Aquapolis | 8 | 0 |
| BREAKpoint | 3 | 3 |
| BREAKthrough | 1 | 0 |
| Ancient Origins | 1 | 1 |
| Total | **162** | **94** |

The other 68 proposed links have catalogue records but no official image. Their
identity evidence is metadata only. This audit does not add images or vectors.
The 94 visual comparisons used the cached Cardmarket listing thumbnails and
TCGdex official images, arranged in eight contact sheets. All 94 showed agreement
in artwork/layout/language; the full collector number is established from the
metadata. Thumbnail comparison is not physical-card authentication.

## Why the old pages were misleading

- **Short set codes are not global identifiers.** Cardmarket `B2` means Base Set 2
  here; catalogue `en:B2` is Fantastical Parade. The old report paired Base Set 2
  cards with unrelated cards from that set. Likewise, Japanese Bandit Ring `XY7`
  and Awakening Psychic King `XY10` must not be paired with English Ancient Origins
  and Fates Collide merely by code and padded number.
- **Name-only and cross-set number matches do not establish a print.** The Japanese
  25th Anniversary Edition Charizard was suggested against `en:pl4-1`, an English
  Arceus card. Do not approve it. The Japanese `s8a-P` and `s8a-G` sets are absent
  from this catalogue snapshot.
- **URL parsing loses identity.** `singles_code_and_number()` interprets `B276` as
  `B` / `276`; the listing label explicitly says `B2 76`. The current collector
  digit extraction also discards meaningful suffixes, while the URL regex cannot
  read endings such as `95b` or `146a`.
- **Deck suffixes matter.** In BW Trainer Kit, `18Z` belongs to the Zoroark deck
  (`en:tk-bw-z-18`, Pokémon Communication), while `18E` belongs to the Excadrill
  deck (`en:tk-bw-e-18`, Audino). The explicit E/Z deck mapping recovers 59 entries.
- **A missing image is not a missing card.** Aquapolis `95a` / `95b` and the Trainer
  Kit cards can have exact catalogue identities even without an official scan.
- **Product IDs are supporting evidence only.** This snapshot duplicates TCGdex
  Cardmarket IDs between the two BW Trainer Kit decks and between some Aquapolis
  a/b variants. Never link solely by those IDs.

The old “official candidate” page has 488 rows. Of those, 97 now have a proposed
identity in this audit; only four retain an ID already shown on the old page.
The other 391 are still unresolved or need a separate variant. This does not
assert that every old suggestion was independently proven wrong.

## Held cases

- **Raichu Lv.46 / Arceus:** the listing photo visibly has a Prerelease stamp.
  Keep it separate from `en:pl4-27`, which already owns the ordinary product URL.
- **Darkness Energy (TK5 20E):** the photo is Darkness Energy, but `20E` selects
  Fighting Energy in the Excadrill deck. `en:tk-bw-z-20` is a possible intended
  target if the label should say `20Z`; it is deliberately not proposed until the
  deck/number is independently verified.
- **Oversized and other product variants:** same artwork/collector number is not
  enough to replace a standard-size card's URL.
- **Unresolved expansion names:** 2,673 photo rows have no exact expansion/deck
  mapping under the conservative rules. Many are missing Japanese/Chinese sets
  or special decks, but this count is not proof that all 2,673 prints are absent:
  additional researched aliases/catalogue imports may resolve some of them.

All 2,931 rows are classified: 162 proposed, 46 non-card redemption items,
7 variant holds, 2 metadata conflicts, 33 missing collector labels, 8 no exact
collector match in a recognized set, and 2,673 unresolved expansion/deck mappings.
There may be more recoverable matches after additional research; 162 is not an
upper bound.

## Review artifacts

Generated local files (ignored by Git) are under `exports/matching-audit/`:

- `review.html`: searchable comparison page, defaulting to the 162 proposals.
- `review.json`: all 2,931 decisions, evidence, candidates, and previous suggestions.
- `proposed-matches.json`: the 162 proposed product URL → catalogue ID assignments.
- `visual-review.json`: explicit evidence for the 94 comparisons and two holds.
- `contact-1.jpg` through `contact-8.jpg`: inspected side-by-side comparisons.
- `catalogue-snapshot.json`: read-only input containing cards/products only, no
  authentication/helper-token tables.

The HTML embeds 2,355 listing photos recovered from the original exported HTML;
remaining listing images and official images use their existing remote URLs.
Some direct Cardmarket image requests return HTTP 403, so preserving those cached
photos is useful. No replacement URLs or official image paths are invented.

The original Gists have not been edited or republished. The production matcher,
live catalogue, links, images, and vectors have not been modified.

## Reproduce

Export only the relevant tables from a read-only SQLite connection:

```sh
mkdir -p exports/matching-audit
docker compose exec -T api python -c 'import sqlite3,json; c=sqlite3.connect("file:/data/catalog.sqlite?mode=ro",uri=True); c.row_factory=sqlite3.Row; print(json.dumps({t:[dict(r) for r in c.execute("SELECT * FROM "+t)] for t in ["cards","cardmarket_expansion_products"]},ensure_ascii=False))' > exports/matching-audit/catalogue-snapshot.json
python3 scripts/audit_cardmarket_photos.py \
  exports/matching-audit/catalogue-snapshot.json \
  --old-review exports/unmatched-compare/unmatched-cardmarket-compare.txt \
  --output exports/matching-audit
python3 -m unittest discover -s scripts/tests -v
```

For the saved visual evidence and embedded-photo cache, also pass
`--visual-review exports/matching-audit/visual-review.json` and
`--embedded-photos exports/matching-audit/embedded-photos.json`. Visual evidence
only attaches when the proposed catalogue ID agrees; it cannot create a match.

Future application should revalidate the proposed IDs/URLs against the current
catalogue, preserve existing owners, persist provenance, and back up the affected
rows. Proposed links must not silently become image/vector additions.

## Follow-up: image search completed on 26 September

The first pass above was followed by an actual DINOv2 image search of the remaining
products. Both **active** indexes were used, each covering 33,937 cards. Do not
load the loose files directly in `/data/vectors/pad/`: they are an older 568-card
index. Resolve `ACTIVE` first, as `scripts/rank_cardmarket_photos.py` does.

After excluding the 162 prior proposals and 46 redemption codes, 2,723 photo rows
remained. **2,147 cached photos were embedded and ranked successfully**, with eight
neighbours saved per image. Both pad and square modes were used; the mean cosine
similarity determined ordering. **576 stored image URLs returned HTTP 403** and
had no cached photo, so those rows could not be visually compared. The run took
about 291 seconds and produced no inference errors.

443 of the compared photos had a top mean similarity of at least 0.90. This is a
retrieval score, not an accuracy estimate or probability of the same print.
Chinese listings frequently retrieve Japanese prints with shared artwork, and
special deck products retrieve ordinary set prints. They remain candidate-only.

Two additional identities were manually resolved:

1. **N BW100 → `N-V2-BWBW100`, `en:bwp-BW100`.** Both the official image and V2
   listing visibly carry the Pokémon League stamp. V1 has no stamp. The model
   actually scored V1 higher, demonstrating why similarity cannot select the
   product variant by itself.
2. **M Tyranitar EX → `Bandit-Ring/MTyranitar-EX-V2`, existing extra record
   `extra-m-tyranitar-ex-089-081`.** The stored extra photo matches the listing and
   reads **090/081**. The catalogue/manifest collector number **089/081 is wrong**.
   This proposal requires correcting that field to `090/081` before applying the
   URL. Keep the internal ID stable to preserve its vector reference. The model
   scored this pair 0.969981; the collector-number correction is based on the
   visible photo, not that score. No source or live data correction was applied.

The additional reviewed holds include N V1, oversized Victini BW32, the stamped
Prerelease Raichu, and the conflicting Darkness Energy 20E label. Victini's photo
explicitly says “Oversized Card / Not Tournament Legal.”

There are now **164 combined proposals: 163 without a required collector-number
correction, plus one requiring the M Tyranitar correction**. They remain proposals;
no database matches, vectors, original Gists, or source-card metadata changed.
The initial snapshot had 42,921 unmatched products. At the later live-state check,
a separate update had reduced that count to 42,457 (2,859 with stored image URLs).
All 164 proposals from this review were still pending. These concurrent links
need their own validation; see the note below.

Additional artifacts:

- `exports/matching-audit/visual/review.html`: the two additional proposals, four
  manually reviewed holds, 2,141 candidate-only rankings, and 576 unavailable photos.
- `exports/matching-audit/visual/visual-candidates.jsonl`: all ranking results,
  per-mode scores, top-eight IDs, and source-photo hashes.
- `exports/matching-audit/visual/index-evidence.json`: exact active index manifests.
- `exports/matching-audit/visual/additional-proposed-matches.json`: two additional
  decisions, including the required catalogue correction.
- `exports/matching-audit/combined-proposed-matches.json`: all 164 proposals.

The remaining 2,141 ranked results have not each been manually approved or rejected;
the completed search makes their nearest images reviewable. Some exact identities
may still require researched set/deck aliases or adding missing catalogue prints.
The other 39,990 unmatched products have no stored listing photo at all.

## Concurrent live update detected at final verification

A separate update changed the production matcher and marked 464 products linked
during this review. This audit did not execute that update or change those files.
72 newly linked rows had photos in the audit: **65 Japanese Bandit Ring products
were linked to English Ancient Origins cards, and 7 Japanese Awakening Psychic King
products to English Fates Collide cards**. These are wrong-language/set links, not
recovered exact prints. For example, Japanese Burmy (XY10 002) now points to
`en:xy10-2` in Fates Collide.

The new `link_named_set_collectors` code in the working tree joins on the short
set ID, digit-only collector number, and name, without checking expansion/language.
It also strips suffixes and can assign multiple product variants to one card. This
reintroduces the collisions identified above. Those changes were left untouched
because they were made outside this audit.

The 72 concrete records are in
`exports/matching-audit/visual/live-links-since-snapshot.json` and flagged as
`live_wrong_language_link` in the visual review. The other 392 newly linked
products have not been individually validated here. Current database counts must
not be treated as verified-match counts until these links are corrected.
