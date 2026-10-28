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
