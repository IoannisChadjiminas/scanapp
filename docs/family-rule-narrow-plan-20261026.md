# Narrow family rule: the footer excludes the leader (plan, 2026-10-26)

Follows `docs/experiments/stage1-bench-20261026.md`. The broad `STAGE1_FAMILY_VECTOR` rule gave +14 early answers on the server's own text with 0 wrong and 0 disagreements, but it breaks four stage 1b safety tests in `tests/test_stage1_gate.py`: a same-name card with another number that leads by 0.05 must be refused. All 14 gains are that case. This plan replaces the broad rule with one that keeps those tests unchanged.

## The rule

A catalogue row is **excluded by the footer** when all of these hold:

1. The phone's number is a full fraction with a set total (`9/108`), not a bare number.
2. The text names exactly one card (the existing lookup with set totals), and that card's set total, where known, equals the read total.
3. The row has the same normalized name as the text card, and is not the same card (duplicate ids collapse first).
4. The row's set total is known and differs from the read total.

Footer-excluded rows are removed from the vector race. The gate then runs as today on the remaining rows:

- **Stage 1:** answers only if the remaining leader is the text card and its margin over the next remaining card is at least 0.02.
- **Stage 1b:** contradiction is measured against the remaining leader, at the existing 0.05.

Nothing else changes: twins, the twin guard, printing groups, the language-twin rule and the artwork check all stay as they are.

What it does on the cases we know:

| Case | Read | Leader | Leader excluded? | Result |
|---|---|---|---|---|
| Charmander | `9/108` | Base Set 46 (102-card set) | yes, 102 is not 108 | can answer |
| Pikachu | `35/108` | Base Set 58 (102) | yes | can answer |
| Pikachu | `35/108` | promo 2015xy-6 (no total) | no | still refused |
| Safety test | `62/102` | Base Set 2 91 (test total 102) | no, same total | still refused |
| Bare number | `9` | anything | no (rule 1) | unchanged |

## Steps

1. **Staging back to off.** Set `STAGE1_FAMILY_VECTOR` to `false` in `compose.dokploy.yaml` until step 4 passes. Production stays off.
2. **Replace the broad rule** in `api/app/recognition/stage1_gate.py` with the footer-excluded set, behind the same flag (`STAGE1_FAMILY_VECTOR`, default off). Reuse `set_total_conflicts` and the set totals already loaded with `STAGE1_SET_TOTALS`.
3. **Tests.**
   - The four existing gate tests pass unchanged, with the flag on and off.
   - New: Charmander `9/108` with Base Set 46 leading → answered; Pikachu `35/108` with a promo leading → refused; bare number → unchanged; leader with unknown set total → not excluded; text card whose own total disagrees with the read → not used.
   - Full API suite green.
4. **Benchmark** (`api/scripts/stage1_bench/run_bench.py`, with `--candidates` and `--printing-from-text`). Run server and oracle text, each with the rule off, broad (for comparison) and narrow. Report early answers, wrong answers against the owner's card, disagreements with the full pipeline, and which gains are kept or lost.
5. **Gate.** On the server's own text: 0 wrong, 0 disagreements, and a gain over the rule off. If it passes, turn the flag on in the staging compose file. If not, it stays off and the report says why.
6. **Write-up and PR.** Add the results to `docs/experiments/stage1-bench-20261026.md`, push to draft ScanApp #78. Do not merge; the owner decides the code default after a live staging check.

## Expected

About 10 of the 14 broad-rule gains kept (the Base Set leaders), the promo-led Pikachu cases lost, and all four safety tests unchanged. This is an estimate until step 4.

## Not covered

The artwork check is not run offline, so stage 1b answers stay candidates. The phone's real text is between the server text (lower bound) and the oracle (upper bound). A live staging rescan is still needed before any production change.
