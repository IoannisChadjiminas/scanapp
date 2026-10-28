# Missing-vector review (2026-10-28)

The read-only staging snapshot has 43,695 picture vectors and 326 additional
card rows with images. A local experiment embedded those 326 reference images
using the same DINO model and pad preprocessing. This is not a proposed
release: earlier catalogue decisions intentionally excluded these cards.

Of the 313 Japanese cards, 310 have cosine at least 0.95 to an existing or
another missing Japanese reference. The catalogue handover describes the
look-alike policy: keep the indexed reference and offer close reprints as
printing alternatives. The other three were explicitly removed after the
vintage panel regressed. The 13 English cards comprise ten display-only cards
and three printing alternatives. See `catalogue-completion-handoff-20261016.md`
§4.9 and `data/catalogue-completion/20261004-01/PROCESS-AND-PENDING.md`.

## Three Japanese exclusions

The saved 17 October full-pipeline results for two independent photos labelled
`ja:PMCG1-021` show the following best-card transitions. These are historical
replays, not fresh results with the current staging flags.

| Snapshot | Photo 1 | Photo 2 |
| --- | --- | --- |
| JASETS, all three indexed | `ja:S5R-006` (uncertain) | `ja:S3a-030` (uncertain) |
| JASETH, first two removed | `ja:CP6-011` (uncertain) | `ja:S10P-030` (uncertain) |
| JASETH3, all three removed | `ja:M6a-137` (printing ambiguous) | `ja:S10P-030` (uncertain) |

Neither baseline answer is the labelled original card. Removing these three
preserved the previous baseline but did not solve recognition of these photos.
The JASETS Cherrim and Diancie candidates were admitted through full-card
retrieval and lacked artwork scores in the saved response. The CP6 Charizard
candidate had both full-card and artwork scores. Therefore one blanket vector
similarity cutoff is not established as a safe fix. A future change needs
paired full-pipeline tests on these two photos, independent photos of all three
excluded cards, and the full existing panels, including alternative lists.
Every changed answer must be reviewed; no change may create a wrong answer.

The 134-photo local vector replay with all 326 additions had no top-one changes
and ten top-20 changes, but it did not include these vintage cases and cannot
validate their full-pipeline behavior. The generated files remain an
experimental local artifact and must not be published.

## Current-code isolated replay

Replayed the two saved photos with current server code and staging's exported
43,695-vector snapshot, OCR and DINO model files, artwork bundle, feature bundle
and recognition settings in a network-disabled x86 container. The feature bundle
passed the normal loader's architecture, catalogue and file checksum checks.
Grading and persistence were disabled. For the comparison, appended only the
three excluded full-card vectors in memory; the existing artwork bundle and
feature records stayed unchanged. No staging scan or catalogue write occurred.

| Photo | Current snapshot | With the three vectors |
| --- | --- | --- |
| `ja_PMCG1-021-1` | `ja:M6a-137`, printing ambiguous | `ja:S5R-006`, uncertain |
| `ja_PMCG1-021-2` | `ja:S10P-030`, uncertain | `ja:S3a-030`, uncertain |

The labelled card for both is `ja:PMCG1-021`; all four outcomes require user
confirmation and all four first cards are wrong. Adding the three vectors alone
reproduces the previous bad change. Both new first cards lack artwork scores,
and both have lower full-card scores than another visual candidate, but these
two observations alone do not establish a generally safe ranking rule. This is
a two-photo diagnostic, not a release gate. Independent photos of the excluded
cards and a full panel remain necessary before changing recognition or index
membership.

## Name-conflict investigation

The excluded Japanese rows for Cherrim, Diancie and the CP6 Charizard store
English names, while the expected base-set Charizard row stores a Japanese
name. `name_evidence_comparable` deliberately treats Japanese OCR versus a
Latin-only name on a Japanese row as unknown. This avoids declaring a false
conflict across scripts, but it also means those candidate names cannot veto
the erroneous selections. Other Japanese catalogue rows do contain Japanese
names associated with the corresponding English view titles, suggesting a
possible source for a separately reviewed localized-name mapping.

However, the saved OCR name in each Charizard result also fails the current
`name_match` test against the expected Japanese Charizard name. The names for
Cherrim and Diancie fail it as well. A hard veto based solely on that OCR would
therefore also reject the correct card. The saved OCR is not copied here.
No ranking rule was changed: a safe approach requires reliable localized name
data and independent positive/negative photo tests, including real photos of
the three excluded printings. The full stored-scan replay and individual review
remain required before merging a ranking change.

## Additional OCR evidence

In the saved JASETS responses, both photos contain an OCR line exactly matching
the Japanese Charizard name, although the selected `name_text` does not. The
saved response's plain lines do not establish that line's confidence or where
it appeared in the image. It could be card text, a holder label or surrounding
content; its presence alone is not safe evidence for changing the first card.
The staging setting `text_identity_candidates` is already enabled and considers
confident OCR lines, but requires a reliable printed fraction and further
artwork verification. The current replay still does not select the expected
card. A next experiment should capture the exact line's region and confidence
and evaluate whether it has independent identity or artwork support; do not
promote it solely because it matches a catalogue name.

An instrumented current-code replay then found the exact name in OCR hits
classified as `name`: photo 1 had confidence 0.99954 and 0.99948 in separate
reads; photo 2 had 0.99964, 0.99917 and 0.99946. These are OCR scores, not
proof of identity; the name region can include holder or surrounding text.
Despite these hits the selected answers were unchanged. The next experiment
should test using an independently supported, unselected name hit to propose
review candidates, with the full stored-scan and photo regression gates. No
new ranking behavior is enabled by this diagnostic.

## Known-name diagnostic

In another isolated replay, the correct Japanese name was selected in memory
only when an existing name-region OCR hit exactly matched that known label at
confidence at least 0.99. This is an oracle experiment using the test label,
not a general selection rule. The first result remained `ja:M6a-137` with
printing ambiguous for photo 1 and `ja:S10P-030` with uncertain status for
photo 2. The identity evidence reported for the first wrong printing changed
from conflicting to supported; it still required confirmation. Thus simply
choosing the correct name does not solve these cases and can make a wrong
printing appear more strongly supported. The test does not evaluate every
review alternative, and it cannot justify a rollout.

## Ranking trace

A current-code trace confirms that both photos pass bare numeric collector
hints corresponding to 006 and 30 into ranking. Their original printed roles
are not established by the parsed tokens alone. The expected base Charizard
is present in the ranking input: position 3 for photo 1, position 21 for photo
2. It falls to positions 5 and 26 respectively after ranking. With the three
experimental vectors added, its positions become 4 to 7 and 21 to 26.
Cherrim 006 and Diancie 030 avoid collector-conflict penalties that the expected
card receives. The expected row's catalogue number is 021 with no separate
printed collector number; the photo's No.006 must not simply be copied into
that field, since a Pokedex number is not collector identity.

This establishes a number-ranking failure in addition to the name-selection
issue. The next local ablation removes bare numeric hints while retaining
prefixed identifiers and fractions. It is a diagnostic only: legitimate cards
also print bare collector numbers, so globally dropping them is not a proposed
release rule.

The bare-number ablation completed on both photos with and without the three
experimental vectors. With the current snapshot, photo 1 stayed printing
ambiguous on `ja:M6a-137`; photo 2 became `no_match`. With the three added
vectors, both became `no_match`, eliminating the Cherrim/Diancie first results
without recovering the expected card. This is evidence against treating these
bare numbers as sufficient identity, not evidence for a global production ban.

## Manual-boundary picture-search probe

A separate vector-only probe used manually chosen card corners and the same
server DINO model and pad preprocessing. The expected card ranked first for
photo 1 after warping (cosine 0.8750). For photo 2 it ranked 80th (0.7760), with
anniversary Charizard `ja:S8a-P-001` first. These searches cover all stored vector
rows without the full pipeline's language filters, artwork search, crop
selection or OCR. The uncropped photo 2 ranked the expected card 6,039th, so
removing background helps substantially but does not distinguish the printing.
Manual corners are diagnostic inputs, not a proposed detector implementation.

The evidence now separates two problems: numeric hints can promote unrelated
cards, while holo/printing similarity can still prevent correct retrieval or
selection even after better framing. No one of the tested name, number or crop
interventions establishes a safe complete fix.

## RANK_PRINTED_NUMBER_ONLY: rejected

The first switch made unnumbered PMCG/neo cards ignore every number read, and
gave no bonus for a bare number on a card printing a fraction. The stored-scan
replay (8,106 scans) changed 103 first cards and 52 choice lists, and the full
scanner turned a user-confirmed Gengar `ja:VS1-021` (bare 021 read) into
Sabrina's Mr. Mime `ja:PMCG6-046`, and Charizard photo 1 into Aipom. Both rules
were wrong: unnumbered cards lost real conflicts, and numbered cards lost real
agreement when the total was not read. A holder-label path also kept the bonus.
The switch is removed.

## RANK_POKEDEX_NUMBER (default off)

What an unnumbered PMCG/neo card prints is its Pokedex number. A bare read equal
to that number (006 on Charizard) is no longer a conflict with the card's
catalogue number; it gives no bonus. Any other number still conflicts, so
Mr. Mime (122) and Aipom (190) keep their conflicts, and numbered cards are
unchanged. Species come from `api/app/recognition/assets/pokedex_gen1_2.json`
(PokeAPI, Gen 1-2, English and Japanese), matched as the longest species name in
the card name (わるいリザードン, Erika's Oddish, アンノーンK).

Expected effect is limited: Cherrim keeps up to +0.08 for the bare 006, so it
still wins when its picture is within about that margin of Charizard. Photo 2 is
mainly a picture problem (below).

## PRINTING_FAMILY_SPECIES (default off)

The printing family behind a review list (same artwork, beyond the retrieved top
K, artwork correlation >= 0.84) was found by exact catalogue name. Japanese rows
mix scripts (`ja:CP6-011` "Charizard", `ja:PMCG1-021` "リザードン"), so a
same-artwork reprint stored in the other script was never offered. With the
switch, Gen 1-2 Pokemon are grouped by species, and the artwork floor still
decides membership. It only adds choices. It cannot help when the shown card has
different artwork (e.g. a Mega Charizard), or when the expected card is not in
any retrieved card's family.

`api/scripts/printing_family_probe.py` measures this before any replay: for a
saved response's retrieved cards it prints the artwork correlation with the
expected card and whether the family by name or by species reaches it.

## Before enabling either switch

1. Probe both Charizard photos' retrieved cards with `--expected ja:PMCG1-021`.
2. Stored-scan replay with `--flag rank_pokedex_number` (ranking only; the
   replay does not build printing families, so it cannot test the second switch).
3. Full-scanner runs with each switch on: the vintage panel, the four review
   negatives (including Gengar `ja:VS1-021`), and both Charizard photos.
   0 moves to a wrong card; record changed choice lists and latency, since the
   species family can load more reference images for common species.
