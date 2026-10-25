# Android fast path: labeled OCR error analysis

A55 run `a55_fastpath_ocr_20261024`, exact 157-photo frozen panel. The phone used the gallery still-photo pipeline and uploaded all 157 scans to staging; 157/157 completed, 0 upload failures. OCR captures were stored locally in `/tmp/a55-fastpath-ocr-157.json` and contain 2,833 ML Kit lines with confidence and normalized boxes. No OCR text was sent as telemetry.

## Ranked recoverable causes

| Rank | Cause | Photos | Interpretation |
|---:|---|---:|---|
| 1 | `name_missing_or_nonexact` | 48 | Name absent or not an exact normalized string match to frozen label |
| 2 | `no_corners` | 34 | Gallery pipeline did not send card corners |
| 3 | `number_missing_or_nonexact` | 16 | Collector number absent or not an exact digit-sequence match |

Other buckets: `ocr_no_read` 0; `text_read_but_fast_gate_abstained` 43; early answers 16. Classifications are first-failure buckets; the name and number checks are deliberately conservative exact comparisons, so OCR confusions and layout parsing require visual review before treating those counts as recoverable gains.

## Examples for manual review

### name_missing_or_nonexact

| Photo | Label | OCR lines (first six) |
|---|---|---|
| `fresh100_388751795697` | Dragonite 065/095 | x2 / 1 / ERAKNO.149 FIDEI B22m a 2100kg / lys Megumi Mizutani / SM9C o65/095 R / HP 160 |
| `fresh100_135663917530` | Scizor 205/197 | STAGE / Seizor / Punishing Sdssors / egponenth Pokiman th pkyy cat hes an Abliys / 140 / 10 |
| `fresh100_396269138140` | Kirlia 212/198 | Rrdia / Magic.i Shot / Psychic / L90 / Thteack dotsi0othmfosh ER / 00ue oppettAu Pokimen |
| `freshraw_4_123815526` | Drowzee 210/198 | BASIG / DrowzZee / weakness( / Forced Sleep / Your epponent chooses I ef their Benched Pokémen and / switehes. itwich thetr Active Rokenon:The new Actİve |
| `freshraw_0_1807925107` | Marill 204/193 | Mavill / Bubble Dratn / Fal 20 damage fem hts Pokenien. / 204/19) / 7O / CanydrveventpayvirV |
| `fresh100_397747206164` | Gengar & Mimikyu GX 038/095 | 2018 P.M. JPN. SUN & MOON / GENGAR & MIMIK YU GX / TAG BOLT / TAG TEAM / x2 / llus.Mitsohiro Arito |
| `fresh100_168302185613` | Pikachu & Zekrom GX 041/173 | PIKACHU& ZEKROM GX / 2019 POKÉMON SUN & MOON JPN / TAG TEAM GX A/S - RR #041/173 / TAG TEAM / x2 / TAG |
| `holdout4_005` | ?  | BẠSIC / Suicune / Abiliy / Fleet-Footed / Once during your turn, if this Pokémon is in the Active / Spot, you may drawa card |
| `holdout4_009` | ?  | VMAX Zeraora AX / Evolves from Zeraora V / Dynamax / Reactive / Pulse / O |
| `holdout4_016` | ?  | KMAX HattereneVaX 320 / Evolves from Hatterene V / GiganLaMax / Ability / Once during your tun, you may meve up to 2 damage / GOUnters firom your Pokémon to your opponent's Active |

### no_corners

| Photo | Label | OCR lines (first six) |
|---|---|---|
| `fresh100_227232802112` | Armarouge 203/198 | STAGE / Armarouge / Evolves from Charcadet / AbilityFire Off / As often as you like during your turn, you may move a / SEnergytrom l ofyour BenchedPokémen to your Acte |
| `fresh100_387647223051` | Parasect TG01/TG30 | STAGEl Parasect / Evolves from Paras / When you play this Pokemon from your hand to evolve / of your Pokemon duringyour turn, you may make both / Active Pokémon Asleep and Poisoned. / weakness x2 |
| `fresh100_127125641244` | Kirlia 212/198 | STAGET / Kirlia / Evolves from Ralts / Magieal Shot / Illus, Jiro Sasumo / Paychic |
| `fresh100_197071758287` | Nidoking 174/165 | STAGEEB / Nidoking / Evolves from Nidorino / AbIlİEyEnthusiastic King / A70 / If you haveNidoqueen in playsignore all Energy in the costS |
| `fresh100_167884982800` | Lechonk 209/197 | BASIG / Lechonk / Tackle / weakness2resistance / llus, Narumi Sato / G0BFEn 209/197 |
| `fresh100_186598235842` | Scizor 205/197 | STAGEJ / Scizor / llus, Oo / Evolves Irom Scyther / Punishing Sissors / /OBF um 205197 |
| `fresh100_356618307865` | Kirlia 212/198 | STAGEJ / Kirlia / Evobves from Ralts / luss io Sasumo / Magical Shot / Psychic |
| `freshraw_7_795209806` | Parasect TG01/TG30 | STAGEl Parasect / Evolves from Paras / Ability / When you play this Pokémon from your hand to evolve / 1 ofyour Pokémon.during your turn, youmay make both / Active Pokémon Asleep and Poisoned. |
| `fresh100_236504673185` | Armarouge 203/198 | STAGE1 / Armarouge / Evolves from Charcadet / Ability Fire Off / As often as you like durtng your turn you may move a / GEnergy from I ofyour Benched Pokêmen to your Astive |
| `freshraw_4_1318482242` | Drowzee 210/198 | BASIG / DroWzee / Forced Sleep / Your epponent chooses I of their Benched Pokémon and / Switches ft with their Active Pokémon. The new Aetive / Pokémon is now Asleep. |

### number_missing_or_nonexact

| Photo | Label | OCR lines (first six) |
|---|---|---|
| `fresh100_116249576361` | Nidoking 174/165 | STAGE / Nidoking / Evolves from Nidorino / Ability / A170 / DEnthusiastie King |
| `fresh100_316758938735` | Marill 204/193 | BASIG / Marill / Bubble Drain / Heal 20 damage rem ts Pokenon / Canm 2 stanc / C PALs 2o4193- |
| `fresh100_226992725275` | Drowzee 210/198 | BẠSIG / Drowzee / Your opponent chooses I of their Benched Pokémon and / Switchesit wich their Active Pokémon:The new Active / Polkémon is now Aseep. / weakncss (O2 |
| `fresh100_336501773626` | Tangela 178/165 | BASIG / Tangela / wrOatncsx2 / Tactful Tangling / illos, Oswoldo KATO / GMEWEN 178/16 |
| `fresh100_125514764134` | Parasect TG01/TG30 | STAGE1 / Parasect / Evolves from Paras / Ability Lethargý Spores / When you play this Pokemon from your hand to evolve / lof your Pokémen durtng your turn, you may make both |
| `fresh100_334557743755` | Parasect TG01/TG30 | STAGE L Parasect / Evolves from Paras / Abiiey / When you play this Pokemon fromyour hand to evolve / Tof your Pokémon during your turn. you may make both / Active Pokémon Asleep and Poisoned. |
| `freshimg_0_995976121` | Blastoise ex 200/165 | 2023 POKEMON MEW EN / BLASTOISE ex / SPECIAL ILLUSTRATION RARE / STAGE2 / Blastoise ex / Evolves lrom Wartorte |
| `freshimg_0_1212241946` | Charizard ex 199/165 | 2023 POKEMON MEW EN / CHARIZARD ex / SPECIAL LLUSTRATION RARE / RA / W / 199 |
| `fresh100_326075712447` | Shaymin V 013/172 | LCGC / CERTIED GUABANTY cOMPANY / Shaymin V / Pokamon (2022) / Briliant Stars013T2 / ShayminV |
| `freshextra_5_636235657` | Gardevoir TG05/TG30 | GARDEVOIR / 2022 POKÉMON SWORD & SHIELD / SILVER TEMPEST #TGO5 / TRAINER GALLERY - HOLO / STAGED Gardevoir / Evolves from Kirlia |

## Scope and next step

This completes the label-linked first pass before recognition code changes. The report does not yet include cropped image examples or per-cause device/set buckets. Review the listed OCR examples and source photos, then fix the highest-yield confirmed cause in isolation; require 0 wrong early answers and 0 background-check disagreements after each change.
