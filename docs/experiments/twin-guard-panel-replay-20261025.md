# STAGE1_TWIN_GUARD on the frozen 157-photo panel — 25 October 2026

**Result: the guard costs no early answer on this panel (27 with it off, 27 with it on), and there are 0 wrong early answers in every run.** The guard never fires here: no stage 1b answer names a printing twin, and the Capsule photo that motivated it never reaches the guard in either run. So the replay shows the guard is harmless on this panel. It does not show the guard fixes the Capsule scan.

## Runs

Same panel, same captured ML Kit lines (`/tmp/a55-fastpath-ocr-157.json`), same stand-in gallery-quad vectors (one cache, shared by all runs), `OCR_SET_CODE_PREFIX=true` in the environment. Only the switches differ.

| Run | Switches (on top of the fixed shipped stage 1 flags) | Early answers | Stage 1 / 1b | Wrong |
|---|---|---:|---|---:|
| Baseline | none | 25 | 15 / 10 | 0 |
| Staging set, guard **off** | `--number-repair --server-frame` | 27 | 15 / 12 | 0 |
| Staging set, guard **on** | `--number-repair --server-frame --twin-guard` | 27 | 15 / 12 | 0 |
| App candidates, guard off | staging set + `--whatif-raw-number` | 29 | 16 / 13 | 0 |
| App candidates, guard on | staging set + `--whatif-raw-number --twin-guard` | 29 | 16 / 13 | 0 |

- **Lost with the guard on: 0 of 27** (0 of 29 with app candidates). No photo changes its answer or its card in either pair (checked per photo, both `decisions` maps).
- **`printing_twins` decisions: 0** in every guard-on run.
- **Reproduction of the earlier figure:** the no-flag baseline gives **25** (15 + 10), the number in `android-fastpath-fixes-20261024.md`. The staging set gives **27**, the step-4 figure in that doc. Both reproduce exactly. The 21 live answers differ because of ML Kit and phone-vector noise, as that doc already records; this replay is not the live run.
- **`OCR_SET_CODE_PREFIX`:** a staging-set run with the variable unset also gives 27 with no photo changed, so the flag has no effect on this panel.

## Twin cases

- **Stage 1b answers (12 with the staging set, guard off):** all 12 name one card with no twin rows (`text_candidates` has one entry). None goes through `printing_twins`, so none can lose its answer. The cards: `en:sv01-210` (2), `en:sv01-203` (1), `en:sv01-212` (3), `en:base1-20` (2), `en:base1-65` (1), `en:base1-68` (2), `en:base1-62` (1).
- **Capsule photo (`reported:ea69f453…`, expected `en:sv04-159`):** the rebuilt text names "Ancient Booster Energy Capsule", number 159/182. The replay returns `no_server_frame` in both runs, before stage 1b reaches the guard. So the guard had nothing to abstain on, and the photo is not answered in either run. The printing-twin pair (`en:sv04-159`, `en:PPS5-PAR-159`) does not reach the guard in this replay.
- **Stage 1 answers (15, guard off):** 9 by the `twin` rule (same name and number, different language, vector picks the other language's row), 6 by `same`. The guard only touches stage 1b (`stage1_gate.decide`, `if options.twin_guard and twins`), so these are unchanged by design. The 9 `twin` answers are the closest panel analogue to the Capsule case; they are stage 1, so the guard cannot change them.
- **Stage 1b answer reasons (guard off):** 10 `artwork`, 2 `server_frame_artwork`.

## Background disagreement

Not measured. The replay script does not run the background check (`evaluate_stage1` answers only). The "wrong" count (0 in every run) is a proxy for wrong answers, not a background-check result. The live background check is still needed.

## Changes made to the replay script

`api/scripts/android_fastpath_replay.py` had no switch for the twin guard, and the flag set was hard-coded in `run()`. Without a change the "on" run could not be done. The change:

- `--twin-guard` switch, which sets `stage1_twin_guard` in the settings the run uses.
- `replay_extra(args)` helper that maps every optional switch to its flag. `main()` now calls it. No behaviour change for the other switches.
- `api/tests/test_android_fastpath_replay.py`: 3 tests (no switch, twin guard alone, the staging set). They pass.

No threshold or gate code changed.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 OCR_SET_CODE_PREFIX=true .venv/bin/python api/scripts/android_fastpath_replay.py \
  --ocr /path/to/a55-fastpath-ocr-157.json --output /path/to/out.json \
  --vector-cache /path/to/gallery-quad-vectors.json --number-repair --server-frame --twin-guard
```

Inputs are local only (the OCR capture, the parity data under `data/`, the DINO teacher model, `~/StudioProjects/PokeSingle/lib/data/set_totals.dart`). Nothing photo-level or OCR text is committed.

## What this does not verify

- **The motivating Capsule case.** The replay never reaches the guard for that photo. Whether the guard picks the right printing on a live Capsule scan is not tested here.
- **Background-check disagreement** (must be 0): not measured by this replay.
- **Live A55 behaviour, CPU and ML Kit determinism:** unchanged from the earlier notes. Six photos in the earlier analysis do not replay, and this run inherits that.
- **Stand-in vectors:** the gallery-quad vectors are the server's DINO model on the phone's corners, not the phone's own embedding.
