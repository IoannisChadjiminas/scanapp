# Stage 0 simulation and a stage 1 gate

Date: 2026-10-21. Branch `cursor/stage0-simulation`, from `origin/main` at `7c93c41`. Local only. Nothing was deployed or merged. Staging was read to copy the public catalogue export and the reference images. No credentials were copied.

The phone is simulated on a Mac: Apple Vision `.accurate` for text, and Core ML 8-bit for the image vector (`2ddf6ec79e37/coreml-pal8`). On one panel crop that vector's cosine against the server ONNX model is 0.998. The position-embedding resize inside the converted model is linear, because Core ML's PyTorch converter has no bicubic upsample; that change alone is 0.9995 cosine before palettization.

## Result

157 photos: the frozen 155 (100 raw, 50 slab, 5 phone) plus the Lugia and Charmander screenshots.

Stage 1 answers when the phone vector's top card and the catalogue card for the phone's name and number are the same card. A slab that has a label name and a label number uses those, and the label's language when the label names one. The margin is the cosine gap to the next different card (`en:sv01-210` and `sv01-210` count as the same card).

| Rule | Answered | Correct | Wrong | Share of the panel |
|---|---:|---:|---:|---:|
| Same card, margin > 0 | 17 | 17 | **0** | 10.8% |
| **Proposed gate: same card, margin ≥ 0.02** | **13** | **13** | **0** | **8.3%** |

No confidence cut and no quality cut. Vision's confidence is often 1.0 on a wrong read, so it does not separate the panel. The correct answers include a soft crop (sharpness 463) and a little glare (0.066). A sharpness floor or a glare cap would only drop correct answers.

The four answers the 0.02 gate leaves for the full pipeline are near ties, all correct on this panel:

| Photo | Card | Margin |
|---|---|---:|
| `freshextra_6_1736995038` | `en:sv03-209` Lechonk | 0.0006 |
| `holdout3_002` | `en:swsh5-155` Tyranitar V | 0.005 |
| `holdout3_005` | `en:sv03-205` Scizor | 0.007 |
| `fresh100_307061782471` | `en:xy9-115` Gyarados, from the slab label | 0.007 |

The 13 the gate keeps are 11 raw and 2 slab (`freshimg_0_1142638013` Pikachu `en:swshp-SWSH020`, `fresh100_406359778998` Dragonite `ja:SM9-065`). Margins run from 0.021 to 0.130.

By photo kind, under the wider rule (margin > 0):

| Kind | Photos | Answered | Correct | Wrong |
|---|---:|---:|---:|---:|
| Raw | 100 | 14 | 14 | 0 |
| Slab | 50 | 3 | 3 | 0 |
| Phone | 5 | 0 | 0 | 0 |
| Screenshot | 2 | 0 | 0 | 0 |

Sharpness tertiles (cuts at 1318 and 2104) each contain correct answers and no wrong ones. Quality does not mark the safe set on this panel.

**Slabs stay on the same gate.** Three slab photos agreed and all three were right. Skipping every slab would drop those and would not have removed a wrong answer, because there were none. The two screenshots did not agree, and the full pipeline got both:

- Lugia: the label read `LUGIA EX` and Japanese, and the card window read `#17 HOLO` and `017/012`. The vector's top card was `ja:CP3-018`. Stage 1 abstained. The pipeline returned `ja:CLF-017`.
- Charmander: the label read Charmander `18a/147` and that is exactly `en:sm3-18a`. The vector's top card was `ja:S12-070`. Stage 1 abstained. The pipeline returned `en:sm3-18a`.

## What the simulated phone sent

145 photos got corners, a quality reading and an embedding. 140 got name or number text. 19 slabs got label fields. 12 photos had no rectangle, so they sent nothing. The server logged a `stage0` line for all 157 scans, with `vector_top=off` on every one. Embedding and quality were accepted and not used to pick a card. Production flags were on, including phone text as a footer hint (`CLIENT_TEXT_OCR=footer`). `APP_CLIENT_EMBEDDING` stayed off.

The full pipeline, on this Mac, was right on 153 of 157. The four misses are slabs (`freshimg_0_1212241946`, `fresh100_326075712447`, `fresh100_407246892266`, `fresh100_377526701873`). Mean server CPU was 5.7 s, median 3.7 s. The Lugia screenshot took 39 s and pulls the mean up.

Stage 1's brute-force cosine over the 44,021-card index plus the catalogue lookup averaged **1.9 ms** per photo on this M4 Pro. That is about three thousand times less CPU than the pipeline mean, and inside the 0.1–0.5 s budget with room to spare. A search of this size costs about the same on x86. The 1.9 ms is the search and the lookup. It does not include reading the JPEG.

## Why the other photos did not agree

There is no wrong stage 1 answer to list. Every photo that did not agree is below. Reasons:

- `no_embedding` — no card rectangle.
- `no_text` — the name or the number was missing, so there was nothing to look up.
- `no_catalogue_hit` — the name and number matched no card.
- `ambiguous_text` — they matched more than one card.
- `text_misread` — the read does not match the photo's truth.
- `number_misread` — the number does not match.
- `vector_wrong` — the text points at the expected card and the vector's top card is a different one. On 15 frozen-panel photos that different card is the other language of the same artwork (an English read, a Japanese vector, or the reverse). Two are a different card in the same language: `fresh100_186598235842` (Scizor `en:sv10-188` against `en:sv03-205`) and `phone_ed6e6f2e-a6eb-4100-861d-810fa2f65a5b` (Comfey `en:A3-080` against `en:30th-077`). Charmander is the same shape of miss: the label is `en:sm3-18a` and the vector is `ja:S12-070`.

| Photo | Kind | Reason | Vector top | Text card | Expected |
|---|---|---|---|---|---|
| `fresh100_388751795697` | raw | no_text | ja:SM9-065 | - | ja:SM9-065 |
| `freshraw_0_299404800` | raw | vector_wrong | ja:SV2P-073 | en:sv02-204 | en:sv02-204 |
| `fresh100_227232802112` | raw | ambiguous_text | ja:SV1S-080 | - | en:sv01-203 |
| `fresh100_135663917530` | raw | no_embedding | - | - | en:sv03-205 |
| `fresh100_396269138140` | raw | no_text | ja:SV4M-077 | - | en:sv01-212 |
| `fresh100_167458253135` | raw | ambiguous_text | sv01-210 | - | en:sv01-210 |
| `fresh100_116249576361` | raw | ambiguous_text | en:sv03.5-174 | - | en:sv03.5-174 |
| `fresh100_116219612870` | raw | vector_wrong | ja:SV2a-182 | en:sv03.5-181 | en:sv03.5-181 |
| `fresh100_387647223051` | raw | no_text | en:swsh11tg-TG01 | - | en:swsh11tg-TG01 |
| `fresh100_127005898900` | raw | ambiguous_text | ja:SV2a-178 | - | en:sv03.5-178 |
| `fresh100_316758938735` | raw | vector_wrong | ja:SV2P-073 | en:sv02-204 | en:sv02-204 |
| `freshraw_1_925085473` | raw | ambiguous_text | sv01-203 | - | en:sv01-203 |
| `freshraw_2_1235899331` | raw | vector_wrong | ja:SV3-116 | en:sv03-205 | en:sv03-205 |
| `fresh100_127125641244` | raw | ambiguous_text | en:sv01-212 | - | en:sv01-212 |
| `fresh100_226992725275` | raw | ambiguous_text | sv01-210 | - | en:sv01-210 |
| `fresh100_197071758287` | raw | ambiguous_text | ja:SV2a-174 | - | en:sv03.5-174 |
| `fresh100_186821197401` | raw | text_misread | ja:SV2a-182 | - | en:sv03.5-181 |
| `fresh100_167884982800` | raw | vector_wrong | ja:SV3-120 | en:sv03-209 | en:sv03-209 |
| `fresh100_134878995437` | raw | ambiguous_text | en:sv03.5-178 | - | en:sv03.5-178 |
| `fresh100_177223455994` | raw | text_misread | ja:SV2P-073 | - | en:sv02-204 |
| `fresh100_185962385461` | raw | ambiguous_text | en:me02-095 | - | en:sv01-203 |
| `fresh100_186598235842` | raw | vector_wrong | en:sv10-188 | en:sv03-205 | en:sv03-205 |
| `fresh100_356618307865` | raw | ambiguous_text | ja:SV1S-084 | - | en:sv01-212 |
| `fresh100_235971735451` | raw | ambiguous_text | sv01-210 | - | en:sv01-210 |
| `fresh100_397434208029` | raw | ambiguous_text | ja:SV2a-174 | - | en:sv03.5-174 |
| `fresh100_336501773626` | raw | no_text | en:swsh6-185 | - | en:sv03.5-178 |
| `freshraw_0_1109460011` | raw | text_misread | ja:SV6a-067 | - | en:sv02-204 |
| `fresh100_236504673185` | raw | ambiguous_text | sv01-203 | - | en:sv01-203 |
| `fresh100_396170517118` | raw | ambiguous_text | sv01-212 | - | en:sv01-212 |
| `freshraw_4_1318482242` | raw | ambiguous_text | en:sv01-210 | - | en:sv01-210 |
| `fresh100_125514764134` | raw | no_text | en:swsh11tg-TG01 | - | en:swsh11tg-TG01 |
| `fresh100_205836607918` | raw | no_embedding | - | - | en:sv02-204 |
| `fresh100_235982624286` | raw | ambiguous_text | ja:SV1S-080 | - | en:sv01-203 |
| `fresh100_135586143350` | raw | ambiguous_text | en:sv01-212 | - | en:sv01-212 |
| `fresh100_267406776028` | raw | no_text | ja:SV1V-086 | - | en:sv01-210 |
| `freshraw_0_1861309623` | raw | vector_wrong | ja:SV2P-073 | en:sv02-204 | en:sv02-204 |
| `freshraw_1_2051404991` | raw | ambiguous_text | ja:SV1S-080 | - | en:sv01-203 |
| `freshraw_3_1376470916` | raw | ambiguous_text | en:sv01-212 | - | en:sv01-212 |
| `freshraw_4_123815526` | raw | ambiguous_text | sv01-210 | - | en:sv01-210 |
| `freshraw_0_1807925107` | raw | no_text | ja:SV2P-073 | - | en:sv02-204 |
| `fresh100_286467766284` | raw | ambiguous_text | ja:SV1S-080 | - | en:sv01-203 |
| `fresh100_365490414711` | raw | ambiguous_text | ja:SV1S-084 | - | en:sv01-212 |
| `freshraw_4_343408992` | raw | ambiguous_text | en:sv01-210 | - | en:sv01-210 |
| `fresh100_397747206164` | slab | text_misread | en:sm9-53 | - | ja:SM9-038 |
| `fresh100_277613285848` | slab | ambiguous_text | en:svp-053 | - | en:svp-053 |
| `freshimg_0_995976121` | slab | vector_wrong | ja:SV2a-202 | en:sv03.5-200 | en:sv03.5-200 |
| `freshimg_0_1677673688` | slab | text_misread | en:me01-141 | - | en:svp-052 |
| `freshimg_0_1212241946` | slab | text_misread | ja:SV2a-201 | - | en:sv03.5-199 |
| `freshimg_0_967558432` | slab | no_text | en:B1-277 | - | en:g1-RC29 |
| `fresh100_137339181702` | slab | text_misread | en:lc-18 | - | en:base1-15 |
| `fresh100_336762686851` | slab | ambiguous_text | en:swsh10.5-055 | - | en:swsh10.5-055 |
| `freshimg_1_113190404` | slab | no_embedding | - | - | en:sv04.5-232 |
| `fresh100_277888034880` | slab | text_misread | ja:SV2a-201 | - | en:sv03.5-199 |
| `fresh100_157312218315` | slab | no_text | en:sv05-051 | - | en:sv05-051 |
| `fresh100_196431506881` | slab | ambiguous_text | en:pop9-15 | - | en:pop9-15 |
| `fresh100_276983335602` | slab | vector_wrong | ja:M2a-246 | en:sv08-247 | en:sv08-247 |
| `fresh100_116749113357` | slab | text_misread | en:sv10.5b-166 | - | en:sv10.5b-166 |
| `fresh100_206285662050` | slab | text_misread | ja:M2a-223 | - | en:mep-023 |
| `fresh100_126873299285` | slab | text_misread | ja:S8a-P-002 | - | en:base1-15 |
| `fresh100_305430906935` | slab | text_misread | ja:XY6-081 | - | en:swsh3.5-16 |
| `fresh100_326079637741` | slab | text_misread | ja:SM7-002 | - | en:sm7-8 |
| `fresh100_135116047131` | slab | no_embedding | - | - | ja:CLF-026 |
| `fresh100_326160477186` | slab | text_misread | ja:SV2a-063 | - | en:sv03.5-063 |
| `fresh100_326075712447` | slab | no_text | en:PPS2-BRS-013 | - | en:swsh9-013 |
| `fresh100_287247791643` | slab | text_misread | en:svp-085 | - | en:svp-085 |
| `fresh100_177390016065` | slab | no_embedding | - | - | en:sma-SV59 |
| `fresh100_407246892266` | slab | text_misread | en:2015xy-1 | - | - |
| `fresh100_377526701873` | slab | text_misread | ja:S10P-085 | - | ja:SM12a-083 |
| `fresh100_298706855994` | slab | text_misread | en:xy12-38 | - | en:base1-9 |
| `fresh100_336794948594` | slab | text_misread | ja:SV6-109 | - | ja:SV6-109 |
| `fresh100_168302185613` | slab | vector_wrong | en:sm9-33 | ja:SM12a-041 | ja:SM12a-041 |
| `freshextra_0_70889495` | slab | no_text | ja:SV11W-169 | - | en:sv08.5-075 |
| `fresh100_127464063628` | slab | no_text | en:tk-hs-r-21 | - | en:sv01-245 |
| `freshextra_5_636235657` | slab | text_misread | ja:S11a-072 | - | en:swsh12tg-TG05 |
| `fresh100_197768683572` | slab | no_text | en:tk-hs-g-30 | - | en:sv04.5-233 |
| `fresh100_178061679870` | slab | number_misread | en:pl4-71 | ja:M6a-021 | en:pl4-71 |
| `fresh100_205408031074` | slab | vector_wrong | ja:SV5a-078 | en:sv06-188 | en:sv06-188 |
| `fresh100_407246154199` | slab | no_text | en:svp-174 | - | en:svp-174 |
| `fresh100_227337115305` | slab | ambiguous_text | en:base5-21 | - | en:base5-21 |
| `fresh100_287264323565` | slab | no_text | en:ex9-9 | - | en:ex9-9 |
| `fresh100_336576388984` | slab | number_misread | en:swshp-SWSH261 | - | en:swshp-SWSH261 |
| `fresh100_145662665211` | slab | ambiguous_text | ja:M6-092 | - | en:sm115-16 |
| `fresh100_198196929850` | slab | ambiguous_text | en:cel25cc-CC005 | - | en:base5-25 |
| `fresh100_376009575543` | slab | vector_wrong | ja:SV5a-078 | en:sv06-188 | en:sv06-188 |
| `freshextra_1_1957211138` | slab | text_misread | ja:PCG6-058 | - | en:base5-68 |
| `fresh100_146365926690` | slab | no_embedding | - | - | en:sv04.5-132 |
| `fresh100_196323744191` | slab | ambiguous_text | ja:PMCG1-034 | - | en:base1-6 |
| `fresh100_145701209354` | slab | no_text | en:swsh7-29 | - | en:swsh7-29 |
| `fresh100_205148259527` | slab | text_misread | ja:PCG9-045 | - | en:CLB-007 |
| `fresh100_146314372000` | slab | number_misread | en:xy12-106 | - | en:xy12-106 |
| `holdout4_004` | raw | no_text | en:swsh12.5gg-GG38 | - | en:swsh12.5gg-GG38 |
| `holdout4_005` | raw | vector_wrong | ja:S12a-215 | en:swsh12.5gg-GG38 | en:swsh12.5gg-GG38 |
| `holdout4_006` | raw | no_embedding | - | - | en:swsh12.5gg-GG38 |
| `holdout4_009` | raw | no_text | en:swsh12.5gg-GG42 | - | en:swsh12.5gg-GG42 |
| `holdout4_011` | raw | no_text | ja:SV8a-222 | - | en:swsh12.5gg-GG42 |
| `holdout4_013` | raw | no_embedding | - | - | en:swsh12.5gg-GG54 |
| `holdout4_016` | raw | no_text | ja:S12a-224 | - | en:swsh12.5gg-GG47 |
| `holdout4_017` | raw | no_text | ja:S12a-224 | - | en:swsh12.5gg-GG47 |
| `holdout4_024` | raw | vector_wrong | ja:S12a-244 | en:swsh12.5gg-GG64 | en:swsh12.5gg-GG64 |
| `holdout4_027` | raw | no_text | ja:S12a-242 | - | en:swsh12.5gg-GG66 |
| `holdout4_028` | raw | vector_wrong | ja:S12a-242 | en:swsh12.5gg-GG66 | en:swsh12.5gg-GG66 |
| `holdout4_029` | raw | vector_wrong | ja:S12a-242 | en:swsh12.5gg-GG66 | en:swsh12.5gg-GG66 |
| `holdout4_031` | raw | no_text | ja:S12a-242 | - | en:swsh12.5gg-GG66 |
| `holdout4_046` | raw | no_embedding | - | - | en:swsh12.5gg-GG31 |
| `holdout4_047` | raw | no_text | en:swsh12.5gg-GG31 | - | en:swsh12.5gg-GG31 |
| `holdout4_049` | raw | ambiguous_text | en:base4-24 | - | en:base1-20 |
| `holdout4_050` | raw | no_text | en:ecard2-H02 | - | en:base1-20 |
| `holdout4_051` | raw | ambiguous_text | base1-20 | - | en:base1-20 |
| `holdout4_058` | raw | no_embedding | - | - | en:base1-65 |
| `holdout4_060` | raw | ambiguous_text | en:base1-65 | - | en:base1-65 |
| `holdout4_063` | raw | ambiguous_text | base1-43 | - | en:base1-43 |
| `holdout4_064` | raw | ambiguous_text | en:base4-65 | - | en:base1-43 |
| `holdout4_070` | raw | no_text | en:base2-58 | - | en:base2-58 |
| `holdout4_072` | raw | no_catalogue_hit | en:pl2-75 | - | en:base2-58 |
| `holdout4_078` | raw | no_text | ja:PMCG1-015 | - | en:base1-68 |
| `holdout4_080` | raw | ambiguous_text | en:base4-99 | - | en:base1-68 |
| `holdout4_084` | raw | ambiguous_text | en:base4-91 | - | en:base1-62 |
| `holdout4_085` | raw | ambiguous_text | en:base4-91 | - | en:base1-62 |
| `holdout4_086` | raw | no_catalogue_hit | ja:SV5a-090 | - | ja:SV5a-090 |
| `holdout4_090` | raw | no_catalogue_hit | ja:SV5a-090 | - | ja:SV5a-090 |
| `holdout4_097` | raw | no_catalogue_hit | ja:SV4M-088 | - | ja:SV4M-088 |
| `holdout4_099` | raw | no_catalogue_hit | ja:SV5M-094 | - | ja:SV5M-094 |
| `holdout4_105` | raw | no_embedding | - | - | ja:SV5M-094 |
| `holdout4_111` | raw | no_catalogue_hit | en:sv05-204 | - | ja:SV5K-093 |
| `holdout4_112` | raw | no_catalogue_hit | en:sv05-204 | - | ja:SV5K-093 |
| `holdout3_004` | raw | no_text | ja:SV3-116 | - | en:sv03-205 |
| `holdout3_008` | raw | no_text | ja:S12a-177 | - | en:swsh12.5gg-GG05 |
| `holdout3_009` | raw | no_embedding | - | - | en:swsh12.5gg-GG05 |
| `holdout3_012` | raw | no_text | en:swsh12.5gg-GG46 | - | en:swsh12.5gg-GG46 |
| `holdout3_014` | raw | no_text | en:swsh12.5gg-GG46 | - | en:swsh12.5gg-GG46 |
| `holdout3_016` | raw | no_text | ja:S12a-218 | - | en:swsh12.5gg-GG41 |
| `holdout3_017` | raw | no_text | ja:S12a-218 | - | en:swsh12.5gg-GG41 |
| `holdout3_018` | raw | no_text | ja:S12a-218 | - | en:swsh12.5gg-GG41 |
| `phone_5085926a-1afb-4505-88a9-c2f23fae34ba` | phone | ambiguous_text | ja:PMCG1-017 | - | en:base1-24 |
| `phone_42d6de99-1ff8-4243-a728-214052715726` | phone | ambiguous_text | ja:PCG6-030 | - | en:xy12-35 |
| `phone_ed6e6f2e-a6eb-4100-861d-810fa2f65a5b` | phone | vector_wrong | en:A3-080 | en:30th-077 | en:30th-077 |
| `reported:ea69f453-102f-48d9-84fb-d7d5b4a34f90` | phone | ambiguous_text | en:PPS5-PAR-159 | - | en:sv04-159 |
| `reported:5f743be8-6e58-4a77-9263-6a5fae525291` | phone | no_text | en:mep-078 | - | en:mep-078 |
| `lugia-screenshot` | screenshot | text_misread | ja:CP3-018 | - | ja:CLF-017 |
| `charmander-screenshot` | screenshot | vector_wrong | ja:S12-070 | en:sm3-18a | en:sm3-18a |

## How to run it again

The catalogue export and the reference images are gitignored, under `data/latency/stage0-simulation-20261021/kit/`:

- `catalog.sqlite` and `vectors/pad/` from `auctaro-staging:/root/bench/export` (50,270 cards, 44,021 indexed, import `PS-CATALOGUE-EN-JA-ENID2-20261019`)
- `reference-images/` from the staging data volume (45,659 files)

Core ML tools, once:

```
python3.13 -m venv /tmp/coreml-stage0
/tmp/coreml-stage0/bin/pip install 'coremltools==9.0' 'torch==2.7.0' onnx onnx2torch pillow numpy
```

Then:

```
api/scripts/stage0_simulation.sh
```

That compiles `vision_text`, simulates corners, text, slab labels, quality and the embedding, converts the palettized model if it is missing, replays the panel against a local API with the production flags, and writes `data/latency/stage0-simulation-20261021/stage1.json`. The API virtualenv needs `uvicorn`, `psutil` and `rapidocr`, which are in `api/requirements.txt`.

Full API suite on this branch: 883 passed, 4 skipped.

## Limits

- The simulated phone is a Mac. Vision and Core ML stand in for an iPhone. Real camera corners differ. The two screenshots use the gallery detector's recorded slab outline, because the server detector finds no rectangle in the browser chrome around them. Other photos use the server detector, moved by at most 0.5% of the short side. A card-shaped photo with no rectangle is read as the phone's own crop.
- The panel is small and hand-picked: 155 photos, about 100 raw, 50 slab and 5 phone, plus 2 screenshots.
- Android is not covered. The embedding here is the iOS Core ML model.
- Local CPU is an M4 Pro. The pipeline times are not x86 times. The search ratio is the part that carries over.
