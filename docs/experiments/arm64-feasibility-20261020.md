# Arm64 (Hetzner CAX, Ampere Neoverse-N1) against staging x86 (AMD EPYC Genoa)

Date: 2026-10-19/20. Branch `claude/vigorous-heisenberg-7c4a86`. Runbook:
`docs/arm64-feasibility.md`. Raw rows: `data/latency/arm64-feasibility-20261020/`.

Nothing was deployed. Staging was only read: the bench export, public card data, the
x86 feature manifest, two selector lines, and the allowlisted recognition settings.
Production was not touched.

## Result

| | Staging x86 baseline (2 vCPU Genoa) | Arm, 2 cores (`--cpus 2`) | Arm, 4 cores (`--cpuset-cpus 0-3`, CAX21 size) |
|---|---|---|---|
| Photos | 155 | 155 | 155 |
| Correct (expected card) | 150/154 | 150/154 | 150/154 |
| card_id/status changes vs staging | - | 1 (an improvement) | 1 (same photo) |
| Lost answers (regressions) | - | **0** | **0** |
| CPU-seconds per scan: mean / p50 / p90 | 12.2 / 10.4 / 19.9 | 31.5 / 27.1 / 48.8 | 29.8 / 25.6 / 46.3 |
| CPU-s mean, without the local-backend artifact (below) | 12.2 | 28.4 | 26.8 |
| Latency p50 / p90 (s) | 5.2 / 9.7 | 14.9 / 24.7 | 10.4 / 17.4 |
| Peak RSS of the API process (MB) | not recorded | 2,344 | 2,371 |
| Container memory.peak (MB) | not recorded | 2,258 | 2,280 |

- **The one answer change** is `fresh100_196431506881` (slab, expected `en:pop9-15`): status
  `uncertain` becomes `matched` on the expected card, with printing `unconfirmed` becoming
  `metadata_supported`. This is not a loss.
- **The other differences** are the grading flag going between unset and `false`: 16 photos
  in run 1, 15 in run 2. This is the same grading-deadline timing effect seen between
  staging runs.
- **The two Arm runs agree with each other**: 0 answer changes, 3 grading-flag differences.
- **Compared with the earlier Mac run** without reference features (27 changes, 7
  regressions), native Arm features remove the drift.
- **Local-backend artifact.** On the local catalogue backend, every scan rebuilds the
  Cardmarket listing groups (`cardmarket_ms` mean 3.1 s, against 14 ms on staging's
  read-only cloud catalogue). The adjusted row subtracts this. It is not an Arm cost.
- **Why CPU is 2.2-2.3× higher.** Every stage (DINOv2 embed, OCR, grading OCR, frame
  proposal) is about 2.3-3× slower per core. ONNX Runtime and OpenCV run on NEON on
  Neoverse-N1, against AVX-512 on Genoa.
- **Thread spinning ruled out.** Pinning to 2 cores gave the same CPU as `--cpus 2`.

## Reference features on Arm

- **Rebuild:** a native rebuild of all 50,270 cards with 8 workers took 1,560 s wall
  (12,234 CPU-s, peak RSS 1.1 GB). It gave 3.98 GB of features for 44,011 cards.
- **Strict comparison with staging's x86 bundle `20261017-ja-sets`:** only `architecture`
  and `opencv_build_sha256` differ. Catalogue signature, coverage, image mapping, art
  boxes, availability and source checksums are equal.
- **Native check:** on 200 re-extracted cards, 0 deltas.
- **The first comparison refused the bundle**, because staging marks 10 cards
  `display_only_no_vectors` (`en:mfb-8/16/24/32/33` with their `-blue` variants, and
  `en:svp-500`). That is a release curation step outside the builder. The new
  `--mirror-unavailable display_only_no_vectors` flag carries over exactly that decision.

## Box and capacity

- **Test box:** CAX31 (8 Neoverse-N1 cores). The test pinned the API to 2 and 4 cores.
- **Throughput:** with one recognition worker, a 4-vCPU Arm box sustains about 3,600 /
  26.8 ≈ 130 CPU-bound scans per vCPU-hour. A Genoa vCPU sustains about 295. For the same
  scan capacity, Arm needs about 2.2× the vCPUs.
- **Per-scan latency** at 4 Arm cores, minus the artifact, is roughly 7.4 s p50. Staging
  gives 5.2 s p50 on 2 Genoa vCPUs.
- **RAM:** about 2.3 GB peak, which fits the 3 GiB compose limit and the 8 GB box.

## Conclusion

Arm is **safe for answers**: no lost answers, and the Arm runs match each other and
staging. It is **not equal in speed**: about 2.2× the CPU per scan and noticeably slower
scans on the same core count. Whether €12.48/month at about 1.4-2× slower scans beats
€42.23/month is a product decision. On raw scan capacity per euro, CAX21 still wins.
