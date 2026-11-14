# Second batch B: official-list-only rows (2026-11-12): not added

**Nothing was switched for batch B.** Staging was not changed. All 125 rows stay out, for the reasons below.

## What was built and measured

A release of the 87 rows that can be built without a usable image (`PS-CATALOGUE-EN-JA-REC27-B-20261111`, schema `..._jarec27`,
never served) was replayed against the 1,891 stored photos on top of A4. The numeric gates passed (right -> wrong 0, right
card always offered, no cell lower, upper bounds 1.5% / 1.6% / 0.4%), but eight stored answers changed in ways the table of
section 4 does not allow:

| Photo | Step-1 / A4 | With batch B |
|---|---|---|
| `dev-ja-vintage-existing-021`, `-022` (`PMCG3-009`), `dev-ja-vintage-040` (`web1-043`) | matched, right card | uncertain, same right card |
| `dev-ja-vintage-025` (`neo2-012`) | matched, right card | uncertain, same right card |
| `sealedF-ja-modern-025`, `sealed-ja-older-020`, `sealedF-ja-older-001` | uncertain, right card | printing ambiguous, right card |

"Matched -> uncertain on the right card" is not in the table, so it is never accepted. Trial builds that left out one group
of rows each (replaying these eight photos only) found the cause:

- the 45 `M6a` rows without art (104-158, Mew B/G/R): leaving them out restores matched on `021`, `022`, `040` and `SM2L-025`;
- the 40 rows of the two LEGEND-era decks: leaving them out restores matched on `025`.

Image-less rows that carry the Japanese name of cards we already hold make those cards less certain. Leaving out the two Vending
Series 3 rows (Kadabra, Haunter) changed nothing, but without an image they could not be checked by eye either, so they were left out with the rest.

## Rows left out

| Rows | Count | Reason |
|---|---:|---|
| `M6a` 104-158 and Mew B/G/R | 45 | no full-size image; as display-only rows they lower the confidence of stored answers (above). Add them when full-size art exists |
| `L2-Sb` Tyranitar Constructed Standard Deck (product name established: Bulbapedia) | 20 | official search gives a 162 x 226 thumbnail (under the 180 px gate): display-only; same effect on stored answers |
| `L2-Sh` Steelix Constructed Standard Deck | 20 | same |
| Folder `MG` | 38 | product not established; thumbnails also under the gate |
| Vending Machine Series 3 Kadabra, Haunter | 2 | Bulbagarden image needs the owner's Chrome; row on the worklist |

## Going back
Nothing to roll back. Inactive schemas `..._jarec23` and `..._jarec27` are unused and can be dropped.
