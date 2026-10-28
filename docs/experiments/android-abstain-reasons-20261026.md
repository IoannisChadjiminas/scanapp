# Why Android early answers still abstain (11 scans, 2026-10-26)

Read-only analysis of the 11 manual Galaxy A55 scans taken with the footer-read test build (PokeSingle #175 draft: `ANDROID_FOOTER_FULLRES=true`, `ANDROID_FULL_RES_CROP=true`, embedding on, 900 ms text budget). Sources: the phone log (`scan-diagnostics` events), the staging `stage0` lines for the same traces, and the stored case files. No code or staging change. Scan ids are the first 8 characters of the server scan id.

## Result in four lines

1. **2 early answers, both correct** (Zorua `30th-095` by `same`, Pikachu `xy12-35` by `artwork`; background checks agreed). 0 wrong, 0 disagreements.
2. **The phone's number is no longer the limit here:** it agreed with the server on 10 of 11 scans.
3. **The biggest cause is the phone's card outline on manual photos.** On 5 of the 9 abstaining scans the outline covers only 16 to 42% of the photo while the card fills about 90% of it. The detector picked an inner rectangle (the artwork window), so the phone's embedding described the artwork box, not the card. This explains all 3 `visual_contradiction` scans and 2 `no_unique_text` scans (the inner rectangle also triggered the holder/label path, which dropped the name).
4. **The other abstentions are delivery problems:** the embedding was late on 2 scans (the footer read runs at the same time), no outline on 1, and the server's own frame finder failed on all three of those, which gives `no_server_frame`. One Toxel scan had no text fields at all.

## Per scan

| Scan | Card | Reason | Phone outline share | Phone vector top (score) | Text candidates | Would an early answer have been right? |
|---|---|---|---|---|---|---|
| 861cffb2 | Zorua 095 | answered `same` | 0.73 | en:30th-095 (0.80) | 30th-095 | yes (answered, agreed) |
| a1f1642b | Pikachu 35/108 | answered `artwork` | 0.75 | ja:PMCG1-035 (0.89) | xy12-35 | yes (answered, agreed) |
| 96ab2efb | Charmeleon 24/102 | `visual_contradiction` (gap 0.24) | **0.38** | en:base1-27 (0.59) | base1-24 | yes: text names the right card |
| 98125ac9 | Charmander 9/108 | `visual_contradiction` (gap 0.24) | **0.32** | ja:PMCG4-026 (0.62) | xy12-9 | yes: text names the right card |
| 7e2b69f4 | Zorua 095 | `visual_contradiction` (gap 0.20) | **0.42** | ja:PCG2-068 (0.62) | 30th-095 | yes: text names the right card |
| c042395e | Comfey 077 | `no_unique_text` | **0.30**, `holder=true`, label sent | en:A3b-102 (0.51) | none (name not sent) | number only; would need the name |
| 5a00ba55 | Charmander 9/108 | `no_unique_text` | **0.16**, `holder=true`, label sent | ja:PMCG5-095 (0.37) | none (name not sent) | number only; would need the name |
| eef7c042 | Toxel MEP 078 | `no_unique_text` | 0.67 | en:mep-078 (0.85, margin 0.045) | none: phone found no text fields | the vector was right; the full pipeline matched it |
| 415dfe26 | Capsule 159 | `no_server_frame` | 0.27 | none (embedding late) | name + number agree | no: Paradox Rift / Prize Pack twins, the twin guard would stop it |
| a885af87 | Brute Bonnet 123 | `no_server_frame` | none (`rejected_small`) | none (no outline) | name + number agree | no: twins, same as above |
| 15cd41ec | Comfey 077 | `no_server_frame` | 0.64 | none (embedding late) | name + number agree | yes, if the embedding or a frame had arrived |

The server's own visual search found the right card on the scans where the phone vector was wrong (for example Charmander 0.87 and Charmeleon 0.87 against the phone's 0.62 and 0.59), so the photo is fine; the phone's crop is the problem. I checked one stored photo by eye (98125ac9): the card fills about 90% of the upload, while the phone's outline share is 0.32, the size of the artwork window.

## Causes, ranked

| Rank | Cause | Scans | Where | Is the rule protecting against something here? |
|---|---|---|---|---|
| 1 | Manual outline picks the artwork window (inner rectangle) | 5 (3 `visual_contradiction`, 2 `no_unique_text` via the holder path) | App, `manual.quad` on Android | The rule is right to refuse: the vector really is wrong. The input is the bug |
| 2 | Embedding late, the footer read competing for the CPU | 2 (`no_server_frame`) | App, footer build only | No. Before the footer build the embedding was late on 1 of 11 |
| 3 | Server frame finder fails on uploads where the card fills the frame (`image_stats.detected=false`) | 3 (with 2 above and the no-outline scan) | Server, stage 1b fallback | Partly: two of the three are twins that the twin guard blocks anyway |
| 4 | No text fields on one Toxel scan | 1 | App, ML Kit | Correct stop; the full pipeline matched it |

## Smallest fix per cause

| # | Fix | Scans | Wrong-answer risk | How to prove it |
|---|---|---|---|---|
| 1 | **Android manual outline: pick the card, not an inner rectangle.** Prefer the largest card-shaped quad (portrait aspect about 0.66 to 0.78, the artwork window is landscape), and reject a quad whose area is under about half the guide when a larger card-shaped candidate exists. Do not take the holder/label path from an inner rectangle | 5 | None directly: it only improves what the phone sends; the server still gates every answer | Rescan the same cards: phone outline share should sit near the server's card size (about 0.8 to 0.9), phone vector top scores near the server's (0.8+), `visual_contradiction` and holder misfires on raw cards should drop to near 0, and wrong answers stay 0 |
| 2 | **Footer read after the embedding,** or at a lower priority, so the embedding keeps its 600 ms budget | 2 | None | Embedding sent rate back to about 10 of 11 with the footer read on |
| 3 | **Stage 1b frame fallback:** when the server's frame finder fails and the phone outline passes the server's card-shape check, use the phone outline (or the whole upload when the card fills it) | up to 1 here (the twins stay blocked) | Low to medium: a bad phone outline could give a bad frame. Only with the shape check | Replay the 157 panel and the 29, 53 and 11 staging scans: 0 wrong, count of `no_server_frame` |
| 4 | Toxel no text: nothing to do now | 0 | none | none |

## Ranked proposal

1. **Fix 1 (outline on manual photos).** It is the largest cause (5 of 9 abstentions) and the safest change. With a correct outline, 3 of these scans had the right card named by the text and would very likely have answered early.
2. **Fix 2 (footer timing)** before anyone measures the footer read again. On these cards the footer read never added a number the normal read lacked (8 `agreed`, 3 `none`, 0 `added`), so today it costs embedding time for no gain.
3. **Fix 3 (frame fallback)** only after 1 and 2 are measured.
4. Keep the twin guard and the contradiction rule as they are.

## Not verified

- I checked one stored photo by eye; the other outline shares are from the logs, not from looking at each photo.
- Two scans (861cffb2, a1f1642b) have no case file, so their server-side detail is from the `stage0` line only.
- That the inner rectangle is the artwork window is my reading of the outline share and the one photo; the phone does not log which rectangle it picked.
- The cards on this run were mostly modern with clear footers, so the footer read's value on old cards is still unmeasured.

## Offline replay of the outline fix (no phone)

The A55 was not available, so the fix was checked offline. Each stored upload was embedded with the server's DINOv2-small model (the phone's LiteRT model matches it at cosine 0.998) on a whole-card crop, which is what the fixed outline gives on a manual photo (the card fills the guide crop), and the result was put through the stage 1 vector rules against the server index (fp32, `data/android-embedding-research-20261023`). Script: session scratchpad `outline_replay.py`, not in git. The "artwork window" row is a rough guess at the old crop, not the phone's exact quad (that quad is not logged), so only the whole-card rows are evidence.

| Scan | Card | Reason today | Whole-card vector | Stage 1 rule with it |
|---|---|---|---|---|
| 96ab2efb | Charmeleon 24/102 | visual_contradiction | top is the right card, 0.820, margin 0.037 | **stage 1 can answer** |
| 98125ac9 | Charmander 9/108 | visual_contradiction | Base Set Charmander 46 leads by 0.031 | no contradiction (under 0.05): stage 1b can try the artwork check |
| 7e2b69f4 | Zorua 095 | visual_contradiction | Stunky (ja) leads by 0.006 | no contradiction: stage 1b can try |
| c042395e | Comfey 077 | no_unique_text (holder path) | top is the right card, margin 0.051 | stage 1 can answer if the name is sent (the fix also stops the holder path) |
| 5a00ba55 | Charmander 9/108 | no_unique_text (holder path) | Base Set leads by 0.025 | stage 1b can try if the name is sent |
| eef7c042 | Toxel 078 | no_unique_text (no text) | right card, margin 0.097 | still no text, so no answer |
| 15cd41ec | Comfey 077 | no_server_frame (embedding late) | Comfey's Japanese print leads by 0.081 | would be visual_contradiction |
| a885af87 | Brute Bonnet 123 | no_server_frame (no outline) | Omastar (ja) leads by 0.103 | visual_contradiction: correct stop |
| 415dfe26 | Capsule 159 | no_server_frame (embedding late) | Japanese Capsule leads by 0.044 | twins: the twin guard stops it |

Reading:

- With a whole-card outline, all 3 `visual_contradiction` scans lose the contradiction (leads of 0.006 to 0.031, under the 0.05 rule). One can answer at stage 1, two can go to the stage 1b artwork check. Two holder-path scans become answerable once the name is sent.
- Estimate: from 2 early answers of 11 to about 4 to 7, depending on how many stage 1b artwork checks pass. In every case where an answer becomes possible, the vector-led or text-named card is the right card; no case in this replay would lead to a wrong card being answered. This is an offline estimate on 9 photos, not a phone measurement.
- A second, separate issue shows up: on one Comfey scan the Japanese print of the same card leads (0.081), which the contradiction rule counts against it. A same-name, other-language twin should probably not count as a contradiction. That is a server change for later, and it needs its own replay.

## On-device check of the outline fix (Galaxy A55, no camera)

The 9 stored uploads were fed through the phone's own still-photo detector (`detectCardInPhoto(manual: true)`, the real native detector) in a temporary integration test, once with `ANDROID_MANUAL_OUTLINE_FIX` off and once on. Share = the chosen outline's area as a share of the photo; holder = whether the app took the holder/label path.

| Scan | Fix off: share / holder | Fix on: share / holder |
|---|---|---|
| 96ab2efb | 0.384 / no | 1.000 / no |
| 98125ac9 | 0.311 / no | 1.000 / no |
| 7e2b69f4 | 0.287 / **yes** | 1.000 / no |
| c042395e | 0.314 / **yes** | 1.000 / no |
| 5a00ba55 | 0.167 / **yes** | 1.000 / no |
| eef7c042 | 0.667 / no | 0.667 / no |
| 415dfe26 | 0.438 / no | 1.000 / no |
| a885af87 | 0.094 / no | 1.000 / no |
| 15cd41ec | 0.622 / no | 0.633 / no |

- With the fix off, the phone reproduces the bug exactly: outline shares of 0.09 to 0.44 on the scans that abstained, and the holder path on 3 raw cards.
- With the fix on, 7 of 9 use the whole guide crop (share 1.000), because the detector never returned the card's own rectangle and no inner rectangle is accepted any more; that is the intended fallback, and the card fills about 90% of the guide crop. The two scans where the detector did find a card-shaped rectangle (0.63 to 0.67) keep it. The holder path is gone on all 9.
- The whole-guide outline is what the offline replay above embedded (it used a 98% crop), so the replay's estimate applies to this outline.
- Not run on the device: the embedding and the server answer for these outlines (that needs a real scan through the camera).

## Wider check: every stored Android manual upload (25–26 October)

Staging held 226 Android manual uploads from 25–26 October (142 at 1363 x 1904 or 1432 x 2000, 80 at 641 x 896, 4 others). Both checks were rerun on them.

**On the A55's own detector** (same temporary integration test; 197 photos with the fix off and 194 with it on before the run stopped on an unlogged error):

| Outline share | Fix off | Fix on |
|---|---:|---:|
| under 0.5 (inner rectangle) | 109 | 26 |
| 0.5 to 0.8 | 61 | 48 |
| 0.8 or more (the card or the guide) | 24 | 117 |
| none | 3 | 3 |
| holder path on a raw card | 27 | 0 |

83 photos move from an inner rectangle to the card or guide; 3 move the other way (0.8+ to 0.5–0.8). The holder path on raw cards goes from 27 to 0. 26 photos still get an outline under 0.5 with the fix: a card-shaped rectangle smaller than half the photo was still accepted, which may be the card held far away or a remaining mis-pick; not checked by eye.

**Offline replay of the whole-card embedding** (201 uploads whose card is known from the owner's list; server model, stage 1 vector rules):

| Result with a whole-card outline | Uploads |
|---|---:|
| Vector agrees with the right card, margin 0.02 or more (stage 1 can answer if the text names it) | 57 |
| Vector agrees, margin under 0.02 | 33 |
| Another card leads by under 0.05 (no contradiction; stage 1b can try the artwork check) | 61 |
| Another card leads by 0.05 or more (`visual_contradiction`) | 50 |

The remaining contradictions sit almost all on two cards: Pikachu Evolutions 35/108 (24 of 33 uploads; 15 of them led by another Pikachu printing, the Base Set reprint tie) and Comfey 30th Celebration (10 of 24; led by its Japanese print). Toxel (25 of 27 agree), Zorua (17 of 19) and Charmeleon (12 of 22) do well. These are uploads, not phone vectors, so they say what a correct outline makes possible, not what the phone sent.
