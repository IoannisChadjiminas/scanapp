# Raw number candidates from the phone (server side of PokeSingle #161)

When the app cannot validate a collector number it now sends up to five raw number-like reads as
`number_candidates` inside `client_text` (`{"text", "conf", "region"}` each). The server accepts them,
repairs them against the catalogue with `STAGE1_NUMBER_REPAIR` (PR #69), and uses the repaired number in the
stage 1 / 1b lookup. Both switches are on by default: `APP_CLIENT_NUMBER_CANDIDATES` (served as
`client_number_candidates` in `GET /config`) and `STAGE1_NUMBER_REPAIR`.

## Rules (all enforced in `stage1_gate.resolve_number`)

- A valid `number` from the phone always wins; candidates are looked at only when `number` is empty.
- A candidate is used only if, after the catalogue-constrained repair (`stage1_text_repair.number_variants`),
  it is a number the catalogue holds for a card whose name also agrees with the phone's name, **and** its set
  total matches a total the catalogue holds for that card (205/777 never passes). A prefixed code with no total
  (TG05) has nothing to compare.
- It cannot pick a card on its own: stage 1 still needs the vector, stage 1b the artwork check.
- Bad entries are dropped, not the whole hint. At most five, 16 characters each; `client_text` may now be up to
  1,280 bytes (was 768).
- The `stage0` log line gets `number_candidate=<raw read>` when one was used.

## Offline A55 replay (157-photo frozen panel, server's DINO as stand-in vectors, as in PR #69)

| | Early answers | Stage 1 / 1b | Wrong |
|---|---:|---|---:|
| Baseline (candidates off) | 25 | 15 / 10 | 0 |
| With the app's candidates + repair | 27 | 16 / 11 | 0 |

Two new answers, none lost: `fresh100_316758938735` (Marill, `2o4193`) and `holdout4_084`
(`en:base1-62`, `62)102`). A candidate was usable on only 3 photos; one of them stayed ambiguous.
The full scanner path is not touched (this only changes stage 1 / 1b decisions and `/config`).

The 70 photos with a readable name and no valid number mostly have no number-like footer read at all, so the
candidates cannot help them; that needs better footer reading on the phone.

Not measured: a real A55 rerun with PokeSingle #161 live, and a fresh holdout (the panel has been used for tuning).
