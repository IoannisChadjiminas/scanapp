# CLIENT_TEXT_AGREE: phone text stands in for the footer read (2026-10-27)

Plan: `docs/full-pipeline-speed-plan-20261026.md` (steps 2a and 3). Builds on the top-20 flag from PR #81. Off by default in code and in both compose files (`compose.dokploy.yaml`, `compose.dokploy.production.yaml`). Draft; nothing merged, nothing enabled in staging.

## The rule (only with CLIENT_TEXT_AGREE on, and CLIENT_TEXT_OCR=footer)

1. The phone's name and collector number must name exactly one card among the 20 visual candidates. The name must match and the number must fit the card with its printed set total applied. A card counts once with its aliases. Two cards in the list refuse the skip (`several_in_top`). No confidence floor: the agreement is the test.
2. The catalogue must hold one printing of that name with that number (set totals applied, so a bare 9 no longer fits 9/108 for a 25-card promo).
3. The server still reads the title. It must agree with the phone's name at 0.85 or more, or the full path runs (`title_disagrees`). The title is read before the complete-frame probe, so a disagreeing title takes exactly the flag-off path.
4. Only then is the footer read replaced by the phone's number. The number enters the structured-identity check at footer confidence (0.85 floor, the same threshold the server's own footer read must reach). The complete-frame probe and the uncropped re-read are not run.
5. A result that used the phone's number is never `matched`. It is capped at `uncertain` (`phone_number_standin`).

Footer mode only. With `all` mode the flag does not take the path (tests cover it). CLIENT_TEXT_TOP20 (PR #81) is unchanged: it still has the 0.9 floor and no set totals.

## Offline measurement

Same 202 scans (phone-replay set, 165 with phone text, plus the real upload `0ba48988`). Runner `api/scripts/full_bench/run_full.py --phone --foreign-features`, staging environment, sequential runs on arm64. Off is the merged branch with origin/main (#83, #84) merged in. Agree is the final code.

Caveats, stated plainly:
- Stored review photos are 1600 px copies. The runner reproduces only 57 to 77 percent of stored answers. Use these numbers as relative effects, not as predictions for staging.
- The reference-feature bundle is loaded with `--foreign-features`: its processing contract is x86_64, this Mac is arm64. Approximate.

| Result | Off | Agree |
|---|---:|---:|
| First card changed | - | 0 |
| Results moved to `matched` | 3 | 3 (none new) |
| Results lost `matched` | - | 0 |
| Status changed | - | 1 (see below) |
| Eligible (phone number stood in) | 0 | 11 |
| Median total ms, eligible scans | 2809 | 1788 |
| p90 total ms, eligible scans | 4203 | 2096 |
| Median total ms, all 202 | 3284 | 3465 |

The all-scan median moved the wrong way by about 180 ms. OFF run against OFF run (pre-merge against merged, same scans) differs by about 190 ms in the median, so this is run-to-run noise, not a cost of the flag.

### Eligible scans (11)

Owner labels are from the runner's owner map (scan names). Right means the agree card equals the label.

| Scan | Label | OFF card (status) | AGREE card (status) |
|---|---|---|---|
| 29844d4d-48a5-46e5-9ff8-7a37e8bad02c | base1-24 | en:base1-24 (uncertain) | en:base1-24 (uncertain) |
| b00a5e2f-c474-45f4-beca-43aace1751fc | base1-24 | base1-24 (uncertain) | base1-24 (uncertain) |
| a13c9908-d54a-48f1-9197-bab219784067 | none | base1-24 (uncertain) | base1-24 (uncertain) |
| 527acab2-9dba-4355-90a5-67fcd5df1b94 | base1-24 | base1-24 (uncertain) | base1-24 (uncertain) |
| dcbff2c5-b7c7-4f6c-8764-32177509936f | base1-24 | base1-24 (uncertain) | base1-24 (uncertain) |
| e6e701f1-c173-4d11-bcef-84bb279eb73c | base1-24 | base1-24 (uncertain) | base1-24 (uncertain) |
| 58dad975-eb54-4ceb-a30b-9ec10754cef8 | base1-24 | en:base1-24 (uncertain) | en:base1-24 (uncertain) |
| 10c3d320-5e9b-4a34-81b1-8d07e4c37861 | base1-24 | base1-24 (uncertain) | base1-24 (uncertain) |
| 7f42e98d-a864-4c61-ba71-122982106854 | none | base1-24 (uncertain) | base1-24 (uncertain) |
| a77274f6-6397-4bc3-834c-9a6b133f8eca | en:xy12-35 | en:xy12-35 (uncertain) | en:xy12-35 (uncertain) |
| 0ba48988 (real upload) | en:xy12-9 | en:xy12-9 (printing_ambiguous) | en:xy12-9 (uncertain) |

Eligible scans with an owner label: 9 (two have no label). Right card with AGREE: 9 of 9. Wrong-card changes: 0.

### Status changes

One scan changed status, `0ba48988`, from `printing_ambiguous` to `uncertain`, on the same card. This is the opposite direction from the earlier uncertain-to-printing_ambiguous change, which is fixed (see below). OFF reasons: `finish_twins`, `local_artwork_used`, `geometry_verified`, `printing_not_proven`. AGREE reason: `conflict`. Once the phone's number counts as footer evidence, the printing is no longer reported as unproven. Neither status is `matched`.

Earlier in the work, 10 eligible scans went from `uncertain` to `printing_ambiguous` on the same card, and 7 non-eligible scans went through a title-disagree fallback that skipped the probe. Both were fixed (the title is read before the probe; the number counts as footer evidence). The final run shows neither.

### Ineligible reasons (AGREE, 202 scans)

| Reason | Scans |
|---|---:|
| No phone text | 37 |
| Incomplete (no number) | 86 |
| Not in top 20 | 34 |
| Several cards in top 20 | 22 |
| Title disagrees | 11 |
| Printings not unique | 1 |
| Eligible | 11 |

Several cards in top 20 (5 examined): the same name and number exist in two English printings. One is `PPS5-PAR-*` (its set total is not in the set-totals table, so a bare number fits) and one is `sv04-*` (total 182). Examples: 68da0fa4, c24acc4a, c0afce20, 61e0c160, 1298999b. The refusal is the intended conservative outcome. Adding the missing total would turn these into eligible scans, and is a catalogue task.

### CLIENT_TEXT_TOP20 (PR #81), same scans

0 eligible, 0 status or first-card changes, OCR passes unchanged. Still requires the 0.9 floor, so it does not skip footer passes on these scans.

## Gate

Offline gate (0 first cards moved to a wrong card; 0 results moved to `matched`; clear time saving): met on these 202 scans. First-card changes 0, `matched` moves 0, median time saved on the 11 eligible scans about 1.0 s (p90 about 2.1 s).

Not met as a UX-neutral change: the Charmander upload reports `uncertain` instead of `printing_ambiguous`, the opposite direction, with the same card. This is a visible status change, though not a wrong answer.

Recommendation: keep it draft and off. Staging needs a fresh replay on the 1600 px caveat set and an explicit decision from the owner. Not run here: any staging change.

## Reproduction of OFF

OFF against OFF (pre-merge against merged, same 202 scans): 0 status differences, 0 first-card differences, 3 matched in each.
