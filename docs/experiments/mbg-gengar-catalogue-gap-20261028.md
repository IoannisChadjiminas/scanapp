# Japanese Mega Gengar ex MBG catalogue gap — 2026-10-28

Read-only investigation of the owner’s latest scans. No recognition settings,
card rows, vectors, phone index or service configuration changed.

The photographed card is Mega Gengar ex, MBG 003/021, confirmed against the
official entry: https://www.pokemon-card.com/card-search/details.php/card/48264/regu/all

The active `pokesingle_completion_20261028_neo2057` catalogue has zero card rows
whose ID matches `ja:MBG-%` (checked case-insensitively on the primary). The paired
catalogue export agrees. This is an absent set/card gap, not an existing row
missing its image or vector. The recent Ruin Wall release did not remove it.

Three completed scans retrieved English Mega Gengar references but presented
Japanese MCharizard EX `ja:XY2-055`, with `ja:XY2-089` as another printing choice.
The saved response reports a collector conflict and printing ambiguity. Server
OCR correctly read the Japanese Gengar title and the printed fraction with high
confidence; the latest crop was detected and passed blur/size gates. The wrong
Charizard presentation is a separate guard problem: unrelated candidates should
not be offered as printing alternatives to an absent identity.

One Android attempt also received HTTP 502 during API startup and never produced
a recognition response. That transient failure does not explain the subsequent
completed scans returning unrelated suggestions.

Required follow-up: audit the full MBG set against the official checklist, add
reviewed card rows/images/vectors/features and matching phone index through the
normal release process, and separately reproduce/test the conflicting-identity
presentation guard behind a switch. Retain the current photos outside Git as
regression cases. Replay stored scans and the full photo panel before enabling
any recognition-rule change.

Coverage correction: 16,319/16,319 Japanese images means every Japanese row
already in this catalogue has its own image. It does not establish that all
printed Japanese cards or sets are in the catalogue. A set-level completeness
audit is still required.
