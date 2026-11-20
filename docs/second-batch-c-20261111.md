# Second batch C: basic energies that came in a product (2026-11-12)

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC34-C-20261111`, schema `pokesingle_completion_20261111_jarec34` |
| Parent | `PS-CATALOGUE-EN-JA-REC26-A4-20261111` (batch B was not added, so C sits directly on A4) |
| Code staging runs | main `a916be4` |
| Artifacts | features and artwork `20261111-second-batch-c2`, images `/data/reference-images/ja-20261111-second-batch-c` (not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-c-20261111` |
| Switch | `prepare` + `forward`, FORWARD OK, healthy, restarts 0, OOM false |

## Rows
All 76 rows (72 + the four S12a `check` rows), images from Limitless and the official card search, each looked at by eye.
Catalogue 62,515 cards (was 62,439). 6 scannable, 52 printing alternatives (all with an existing twin), 18 display-only.

- Sets: MMBP 9, MMBS 9, SMA 9, SMB 9, SVI 8, HXY 6, SML 6, MDB 5, S12a 4, SM1p 4, SP4 4, WCS23 2, SGG 1. Unnumbered energies get `uNN` ids.
- **S12a, the four `check` rows:** the official images print 251/172 to 254/172 SR (草, 炎, 水, 雷). We held 248-250 and 255-262 and nothing at 251-254,
  so they are added as `ja:S12a-251` to `254` with those numbers.
- **18 display-only rows:** their image file is byte-identical to another row's file in this batch (the same energy printed in two products,
  e.g. the MEGA Power and Speed Style boxes). One file is never given to two cards, so the second row of each pair is display-only:
  `ja:MMBS-u01`, `ja:MMBS-u02`, `ja:MMBS-u03`, `ja:MMBS-u04`, `ja:MMBS-u05`, `ja:MMBS-u06`, `ja:MMBS-u07`, `ja:MMBS-u08`, `ja:MMBS-u09`, `ja:SMB-u01`, `ja:SMB-u02`, `ja:SMB-u03`, `ja:SMB-u04`, `ja:SMB-u05`, `ja:SMB-u06`, `ja:SMB-u07`, `ja:SMB-u08`, `ja:SMB-u09`.

## Gate (1,891 photos, against the step-1 stored run)

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. The 14 changed answers are exactly those of A4 (judged in that record); C adds none.
A first C build on top of batch B was not used, because B was not added.

## Not measured
As in A1; Cardmarket links.

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-c-20261111 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
