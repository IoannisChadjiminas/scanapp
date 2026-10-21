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

Round 2, below, keeps that same margin and raises the gate to **36 of 157 (22.9%)**, still with 0 wrong. Round 3, the footer read, raises it again to **40 of 157 (25.5%)**.

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

## Round 2

Same phone fields, same replay. Two changes in the stage 1 estimate only. The catalogue file is unchanged.

### Fix A: one card for a duplicated id

561 English cards are stored twice, as `sv01-210` and `en:sv01-210`, with the same name, set, number and language. Both ids are in the embedding index, and both have a Cardmarket id. The stage 1 lookup now keeps the `en:` id when a candidate list contains both. That list is `docs/experiments/stage0-duplicate-pairs-20261021.csv`, for a later catalogue cleanup. Two pairs have different Cardmarket product ids (`sv01-015` Meowscarada 702311 and 800836, `sv01-023` Arboliva 702319 and 749045). The price tables in this export are empty, so this run cannot say which id a price is attached to.

`ambiguous_text` fell from 42 photos to 18. The 18 that remain:

- **5 are the same artwork in both languages, with the same printed number.** Nidoking `174` and Tangela `178` each match `en:sv03.5-…` and `ja:SV2a-…`. The Japanese row's English title is "Nidoking" or "Tangela", so the English read hits both rows. The text is not one card, so the twin rule does not fire.
- **3 are the same name and number in different sets.** Vulpix `68/102` (`en:base1-68` and `en:hgss2-68`), Charmeleon `24/102` (`en:base1-24` and `en:swsh4-24`), Ancient Booster Energy Capsule `159` (`en:PPS5-PAR-159` and `en:sv04-159`).
- **10 match several printings**, or a loose name. The phone Pikachu `35/108` is in this group, and so is a Gyarados read that also hits Ariados.

### Fix B: same-artwork language twins

The vector's card and the text's card agree when their reference vectors have cosine at least **0.84**, they are different languages, and the twin does not repeat the text's number with a different set total. The text's card is the answer, and the margin is the gap from that pair to the next other card.

0.98, the first guess, accepts nothing on this panel. Duplicate ids are cosine 1.0. Same-artwork language pairs sit lower, from 0.848 (Roxanne) to 0.951 (Marill). The plan's Dragonair pair, `en:sv03.5-181` and `ja:SV2a-182`, is 0.870. The next different-language pair that is not the same artwork is 0.774 (`en:sv08-247` Pikachu ex against `ja:M2a-246` メガカイリューex). Charmander's vector, `ja:S12-070` ミニリュウ, is 0.772 against `en:sm3-18a`. One real pair, Blastoise ex `en:sv03.5-200` and `ja:SV2a-202`, is 0.752 and sits on that same side of the gap, so the cut leaves it out. Same-language reprints stay out too: Sandshrew `en:base4-91` against `en:base1-62` is 0.941, and Electabuzz `en:base4-24` against `en:base1-20` is 0.907. No photo on the panel was a language twin with a conflicting set total.

| Reference cosine | Margin > 0, correct / wrong | Margin ≥ 0.02, correct / wrong |
|---|---:|---:|
| 0.75 | 53 / 0 | 37 / 0 |
| 0.80 and 0.84 | 50 / 0 | 36 / 0 |
| 0.90 | 45 / 0 | 31 / 0 |
| 0.95 | 34 / 0 | 21 / 0 |
| 0.98 | 31 / 0 | 18 / 0 |

0.75 is still 0 wrong on this panel because the text happened to be the right card. It would also treat Charmander and the Pikachu ex / メガカイリューex pair as twins. The gate uses 0.84.

### Round 1 against round 2

The margin gate is unchanged: same card, margin ≥ 0.02. Every column is correct / wrong.

| Run | Margin > 0 | Margin ≥ 0.02 | Share at the gate |
|---|---:|---:|---:|
| Round 1 | 17 / 0 | 13 / 0 | 8.3% |
| A only, duplicate ids collapsed | 31 / 0 | 18 / 0 | 11.5% |
| B only, language twins | 30 / 0 | 26 / 0 | 16.6% |
| **A and B** | **50 / 0** | **36 / 0** | **22.9%** |

A on its own adds 5 answers at the gate. B on its own adds 13. Together they add 23: the 5 from A, the 13 from B, and 5 that need both. Those last five were ambiguous until the duplicate id was collapsed, and the vector is the Japanese twin (Armarouge `en:sv01-203` on four photos, Kirlia `en:sv01-212` on `fresh100_365490414711`).

By kind, A and B together:

| Kind | Photos | Margin > 0 | Margin ≥ 0.02 | Wrong |
|---|---:|---:|---:|---:|
| Raw | 100 | 44 | 31 | 0 |
| Slab | 50 | 6 | 5 | 0 |
| Phone | 5 | 0 | 0 | 0 |
| Screenshot | 2 | 0 | 0 | 0 |

There is no wrong stage 1 answer at either margin. Fourteen further photos agree and are correct, with margins from 0.0006 to 0.017, and the 0.02 gate leaves them for the full pipeline. Ten of those fourteen are new in round 2. Four were already the round 1 near ties.

### New answers at the gate

Five from collapsing the duplicate id. The vector and the text were already the same card.

| Photo | Card | Margin |
|---|---|---:|
| `freshraw_4_343408992` | `en:sv01-210` Drowzee | 0.072 |
| `fresh100_235971735451` | `en:sv01-210` Drowzee | 0.030 |
| `freshraw_3_1376470916` | `en:sv01-212` Kirlia | 0.024 |
| `fresh100_226992725275` | `en:sv01-210` Drowzee | 0.024 |
| `freshraw_4_1318482242` | `en:sv01-210` Drowzee | 0.020 |

Eighteen from a language twin. The card named here is the text's card.

| Photo | Card | Vector | Cosine | Margin |
|---|---|---|---:|---:|
| `freshraw_0_1861309623` | `en:sv02-204` Marill | `ja:SV2P-073` | 0.951 | 0.168 |
| `freshraw_0_299404800` | `en:sv02-204` Marill | `ja:SV2P-073` | 0.951 | 0.136 |
| `fresh100_316758938735` | `en:sv02-204` Marill | `ja:SV2P-073` | 0.951 | 0.022 |
| `holdout4_024` | `en:swsh12.5gg-GG64` Melony | `ja:S12a-244` | 0.895 | 0.163 |
| `fresh100_116219612870` | `en:sv03.5-181` Dragonair | `ja:SV2a-182` | 0.870 | 0.140 |
| `fresh100_167884982800` | `en:sv03-209` Lechonk | `ja:SV3-120` | 0.938 | 0.137 |
| `fresh100_365490414711` | `en:sv01-212` Kirlia | `ja:SV1S-084` | 0.945 | 0.093 |
| `holdout4_029` | `en:swsh12.5gg-GG66` Roxanne | `ja:S12a-242` | 0.848 | 0.081 |
| `fresh100_286467766284` | `en:sv01-203` Armarouge | `ja:SV1S-080` | 0.911 | 0.080 |
| `fresh100_235982624286` | `en:sv01-203` Armarouge | `ja:SV1S-080` | 0.911 | 0.078 |
| `freshraw_2_1235899331` | `en:sv03-205` Scizor | `ja:SV3-116` | 0.894 | 0.076 |
| `holdout4_028` | `en:swsh12.5gg-GG66` Roxanne | `ja:S12a-242` | 0.848 | 0.058 |
| `holdout4_005` | `en:swsh12.5gg-GG38` Suicune V | `ja:S12a-215` | 0.937 | 0.056 |
| `freshraw_1_2051404991` | `en:sv01-203` Armarouge | `ja:SV1S-080` | 0.911 | 0.049 |
| `fresh100_227232802112` | `en:sv01-203` Armarouge | `ja:SV1S-080` | 0.911 | 0.045 |
| `fresh100_205408031074` | `en:sv06-188` Eevee | `ja:SV5a-078` | 0.930 | 0.040 |
| `fresh100_376009575543` | `en:sv06-188` Eevee | `ja:SV5a-078` | 0.930 | 0.032 |
| `fresh100_168302185613` | `ja:SM12a-041` ピカチュウ&ゼクロムGX | `en:sm9-33` | 0.925 | 0.022 |

### What still does not agree

107 photos still do not agree. Counts:

| Reason | Photos |
|---|---:|
| `no_text` | 35 |
| `text_misread` | 23 |
| `ambiguous_text` | 18 |
| `no_embedding` | 12 |
| `vector_wrong` | 9 |
| `no_catalogue_hit` | 7 |
| `number_misread` | 3 |

**Phone reading.** Of the 35 with no text, 30 have no number and 11 have no name. The number is the gap: without it the lookup does not start. One of the five phone photos is here, Toxel, with the name read and the number missing. The other four phone photos are not a missed word. Three match more than one printing (Charmeleon `24/102`, Pikachu `35/108`, Ancient Booster Energy Capsule `159`). Comfey matched `en:30th-077` and the vector picked a different Comfey, `en:A3-080`.

The 23 misreads are 19 slabs, 3 raw photos and the Lugia screenshot. The three raw photos have the right number and a name that is not a name (`HP7OC` and `HZO` for Marill, `ТИР 100 C` for Dragonair). On those three the vector is already the Japanese twin, so a real name would be a stage 1 answer under the twin rule. The slab misses are the label or the holder being read as the card: `CENTERING`, `EDGES`, `1999 POKEMON GAME`, a grader line, or a number with the wrong total. Lugia is that last case. The card window read `#17 HOLO` and `017/012`, and the printed number is `017/032`. The label had the name and no number, so the lookup used the card window.

The 9 `vector_wrong` rows are the ones the twin cut leaves out: the same-language reprints (Sandshrew twice, Electabuzz), Scizor `en:sv10-188` against `en:sv03-205`, Armarouge's vector `en:me02-095`, Blastoise ex at cosine 0.752, Pikachu ex against メガカイリューex at 0.774, Comfey, and Charmander. The 7 catalogue misses are a number with a name that matches nothing (`DOBOAD`, `FEEID`, and similar). The 3 number misreads are slabs whose digits are wrong (`21/99` for `71/99`, `SWSH267` for `SWSH261`, `06/108` for `106/108`). Twelve photos still have no rectangle.

## Round 3

Same catalogue, same gate (margin ≥ 0.02), same Fix A and Fix B. The only change is the simulated phone's collector-number read. The full-card Vision pass stays. After it, the phone reads the bottom 14% of the straightened card at 2×, then the bottom-left and bottom-right corners (35% × 15%) if that strip has no catalogue number, then the strip once more with a contrast boost. `minimumTextHeight` on those crops is 0.015, and language correction stays off. Digit swaps (`O→0`, `I→1`, `S→5`, `B→8`, `Z→2`) apply only inside a number. A number is kept when the catalogue has that printed number, or that collector number in a set of the same total. `017/012` fails that check. On a slab, label words are dropped from the card name, and the label number is used when the footer has nothing.

2× is the scale that stays inside the time budget. On this Mac the extra reads add a median **52 ms** and a p90 of **138 ms** (mean 74 ms, 145 photos that have a crop).

### Number-read rate

Photos whose `client_text` has a collector number.

| Kind | Photos | Round 2 | Round 3 |
|---|---:|---:|---:|
| Raw | 100 | 70 | 74 |
| Slab | 50 | 22 | 33 |
| Phone | 5 | 4 | 4 |
| Screenshot | 2 | 1 | 2 |
| **All** | **157** | **97 (61.8%)** | **113 (72.0%)** |

Lugia's contrast retry now reads `017/032`, and the name is the label's `LUGIA EX`. Charmander keeps the label number `18a/147`. Neither becomes a stage 1 answer: Lugia's vector is still `ja:CP3-018`, and Charmander's vector is still below the twin cut.

### Stage 1

| | Margin > 0 | Wrong | Margin ≥ 0.02 | Wrong | Share |
|---|---:|---:|---:|---:|---:|
| Round 2 | 50 | 0 | 36 | 0 | 22.9% |
| **Round 3** | **57** | **0** | **40** | **0** | **25.5%** |

By kind at the gate: raw 33 of 100, slab 7 of 50, phone 0 of 5, screenshot 0 of 2. At any positive margin: raw 48, slab 9, phone 0, screenshot 0.

Each row adds one change on top of the row above. Stage 1 is the margin ≥ 0.02 gate.

| After this change | Photos with a number | Stage 1 | Wrong |
|---|---:|---:|---:|
| Round 2 | 97 | 36 | 0 |
| Footer strip at 2× | 103 | 39 | 0 |
| Bottom corners, when the strip misses | 105 | 40 | 0 |
| Number cleanup and the extra formats | 107 | 41 | 0 |
| Catalogue check | 102 | 40 | 0 |
| Contrast retry | 103 | 40 | 0 |
| Slab label filter and label number | 113 | 40 | 0 |

The catalogue check is the step that drops a number. It removed `TG01/80` on `fresh100_387647223051` (Parasect, the real total is 30). That read had been a correct stage 1 answer, and it is not one after the check. The gate stays at 0 wrong. The contrast retry recovered Lugia's `017/032` and one other number, and neither is a new stage 1 answer. The slab rules add nine numbers, mostly the label number, and those photos still do not agree with the vector.

### New answers at the gate

| Photo | Card | Margin |
|---|---|---:|
| `holdout3_008` | `en:swsh12.5gg-GG05` Lapras | 0.100 |
| `fresh100_336576388984` | `en:swshp-SWSH261` Charizard VMAX | 0.037 |
| `fresh100_146314372000` | `en:xy12-106` Dragonite | 0.025 |
| `holdout3_012` | `en:swsh12.5gg-GG46` Deoxys | 0.022 |

Three more agree and are correct, with margins just under 0.02, so the gate leaves them: `holdout4_017` (`en:swsh12.5gg-GG47`, 0.020), `freshraw_0_1807925107` (`en:sv02-204`, 0.011), `fresh100_145701209354` (`en:swsh7-29`, 0.006).

### Still no number

44 photos. Twelve have no rectangle. Four crops are tiny, three are cut off, five footers came back empty. Sixteen have footer text and no number pattern: the line is copyright, a weakness line, or a gallery number whose slash was lost (`GG41GG70`). Four were read and rejected: `TG01/80`, `210/109`, `RC29/32`, `GG46/20`. The one phone photo still missing a number is Toxel (`reported:5f743be8-…`): the footer sentence contains `078` and no fraction.

| Photo | Kind | Why |
|---|---|---|
| `fresh100_135663917530` | raw | no rectangle |
| `fresh100_396269138140` | raw | tiny crop |
| `fresh100_387647223051` | raw | read `TG01/80`, rejected |
| `fresh100_336501773626` | raw | footer text, no number |
| `fresh100_125514764134` | raw | footer text, no number |
| `fresh100_205836607918` | raw | no rectangle |
| `fresh100_267406776028` | raw | read `210/109`, rejected |
| `freshimg_0_1212241946` | slab | tiny crop |
| `freshimg_0_967558432` | slab | read `RC29/32`, rejected |
| `freshimg_1_113190404` | slab | no rectangle |
| `fresh100_157312218315` | slab | tiny crop |
| `fresh100_206285662050` | slab | footer empty |
| `fresh100_126873299285` | slab | footer text, no number |
| `fresh100_135116047131` | slab | no rectangle |
| `fresh100_326075712447` | slab | tiny crop |
| `fresh100_287247791643` | slab | footer text, no number |
| `fresh100_177390016065` | slab | no rectangle |
| `fresh100_407246892266` | slab | footer empty |
| `fresh100_197768683572` | slab | footer text, no number |
| `fresh100_407246154199` | slab | footer text, no number |
| `fresh100_287264323565` | slab | footer text, no number |
| `freshextra_1_1957211138` | slab | footer empty |
| `fresh100_146365926690` | slab | no rectangle |
| `fresh100_205148259527` | slab | footer text, no number |
| `holdout4_004` | raw | footer text, no number |
| `holdout4_006` | raw | no rectangle |
| `holdout4_009` | raw | footer text, no number |
| `holdout4_011` | raw | footer empty |
| `holdout4_013` | raw | no rectangle |
| `holdout4_016` | raw | footer text, no number |
| `holdout4_027` | raw | footer text, no number |
| `holdout4_046` | raw | no rectangle |
| `holdout4_047` | raw | card cut off |
| `holdout4_050` | raw | footer empty |
| `holdout4_058` | raw | no rectangle |
| `holdout4_070` | raw | card cut off |
| `holdout4_078` | raw | card cut off |
| `holdout4_105` | raw | no rectangle |
| `holdout3_009` | raw | no rectangle |
| `holdout3_014` | raw | read `GG46/20`, rejected |
| `holdout3_016` | raw | footer text, no number |
| `holdout3_017` | raw | footer text, no number |
| `holdout3_018` | raw | footer text, no number |
| `reported:5f743be8-6e58-4a77-9263-6a5fae525291` | phone | footer text, no number |

### Port to the app

The Mac run is the specification. Nothing in PokeSingle was changed.

- `ios/Runner/CardWarp.swift` `recognizeText`: add a second request for a crop. Bottom 14% of the straightened card, upscaled 2×, and the two bottom corners at 35% × 15%. Set `minimumTextHeight` to 0.015 and leave `usesLanguageCorrection` false. One contrast-boosted retry of the strip when the first reads have no catalogue number.
- `lib/data/text_pass.dart`: run that request after the full-card pass, corners only if the strip missed, and stop once a number is in hand. The extra work on this Mac was 52 ms median, 138 ms p90.
- `lib/data/card_text.dart` `pickCardNumber`: clean digits only inside a number, accept `18a/147`, `TG01/TG30`, `GG38/GG70`, `SWSH020`, `SVP 053` and `001/S-P`, and reject a line that sits above the bottom 10% of the card. A fused `GG41GG70`, with the slash missing, is the pattern that still fails here.
- The catalogue check needs set totals. The API already stores them in `set_totals`. Bundle that table, or let stage 1 reject a number whose denominator matches no set total, before the phone treats it as read.
- `lib/data/label_text.dart`: do not use a label word as the card name (the server's `grading_label_line` and `slab_label_field`: PRISTINE, GEM MINT, a dated Pokémon header, `#17HOLO`). When the footer has no valid number, send the label number and the label's language.

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

That compiles `vision_text`, simulates corners, text, the footer and corner number read, slab labels, quality and the embedding, converts the palettized model if it is missing, replays the panel against a local API with the production flags, and writes `data/latency/stage0-simulation-20261021/stage1.json` plus `docs/experiments/stage0-duplicate-pairs-20261021.csv`. Round 3's number read is `api/scripts/footer_numbers.py`, and it uses set totals from `data/catalogue-completion/staging-data-local-20261014/catalog.sqlite`. With the phone fields and the replay already on disk, rerun the number read and then the estimate:

```
.venv/bin/python api/scripts/footer_numbers.py \
  --stage0 data/latency/stage0-simulation-20261021/stage0.jsonl \
  --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \
  --totals data/catalogue-completion/staging-data-local-20261014/catalog.sqlite \
  --vision /tmp/vision_text \
  --ablation data/latency/stage0-simulation-20261021/footer-ablation.json
.venv/bin/python api/scripts/estimate_stage1.py \
  --panel data/latency/stage0-simulation-20261021/stage0.jsonl \
  --index data/latency/stage0-simulation-20261021/kit/vectors/pad \
  --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \
  --replay data/latency/stage0-simulation-20261021/replay.jsonl \
  --log data/latency/stage0-simulation-20261021/server.log \
  --out data/latency/stage0-simulation-20261021/stage1.json \
  --duplicates-out docs/experiments/stage0-duplicate-pairs-20261021.csv
```

The API virtualenv needs `uvicorn`, `psutil` and `rapidocr`, which are in `api/requirements.txt`.

Full API suite on this branch: 883 passed, 4 skipped.

## Limits

- The simulated phone is a Mac. Vision and Core ML stand in for an iPhone. Real camera corners differ. The two screenshots use the gallery detector's recorded slab outline, because the server detector finds no rectangle in the browser chrome around them. Other photos use the server detector, moved by at most 0.5% of the short side. A card-shaped photo with no rectangle is read as the phone's own crop.
- The panel is small and hand-picked: 155 photos, about 100 raw, 50 slab and 5 phone, plus 2 screenshots.
- Android is not covered. The embedding here is the iOS Core ML model.
- Local CPU is an M4 Pro. The pipeline times are not x86 times. The search ratio is the part that carries over.
