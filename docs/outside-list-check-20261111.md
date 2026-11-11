# Check against outside lists, step 6 of the remaining-cards plan (2026-11-11)

Step 6 of `docs/remaining-cards-plan-20261111.md`: compare our catalogue with card lists kept
by others, to find sets and cards we do not hold at all. Read-only. Nothing in the catalogue,
on staging or in production was changed.

Our side is the staging catalogue (`pokesingle_completion_20261111_jarec18`): English 240 sets
and 25,638 cards, Japanese 488 sets and 28,024 cards.

## Result in short

| | Missing sets | Cards in them | Missing cards in sets we hold | Uncertain |
|---|---|---|---|---|
| English | 2 | 153 | 7 | up to 38 more, known by count only |
| Japanese | 11 products | 262 | 331, plus 72 basic energies that came in a product | 5 |

So the outside lists show about **160 English and 665 Japanese cards** that have no row in our
catalogue. Most of the Japanese ones sit in four places: Start Deck 100 (128), the new
30th Celebration set (94), the Starter Set V and VMAX starter decks (184) and the Sword & Shield
promos (52).

## What was compared

| List | Covers | Used for |
|---|---|---|
| TCGdex | English 221 sets, Japanese 202 sets, card by card | Sets, counts and numbers |
| Limitless (Japanese cards) | 264 sets from Black & White onward, card by card, with images | Numbers and names, set by set |
| Official Japanese card search (pokemon-card.com) | 23,530 entries in 331 product folders, with thumbnails | Which Pokémon and energies a product holds. It has no collector numbers and repeats cards, so it is not used for counts |
| Bulbapedia | Set lists for both languages; 186 Japanese set pages with 467 card tables | Set presence, set counts, and card names for the older Japanese sets |
| pokemontcg.io | 39 English sets | A second check on English numbers |

How a difference was accepted as a gap: a card counts as missing only when the outside list has
it under a number or name that no row of ours in that set (or its companion sets) can be paired
with. Promo series were paired by hand. Differences that are only another spelling or another
language of the same name were dropped.

## English

### Missing sets

| Set | Cards | Row source | Image source |
|---|---|---|---|
| Delta Reign (`me06`, released 6 November 2026) | 141 (103 + 38 secret) | TCGdex `me06`; also on Bulbapedia's list (DLR) | None yet: TCGdex has the rows and no art so far. The normal mirror job picks the art up when TCGdex publishes it |
| McDonald's Collection 2013 | 12 | Bulbapedia, `McDonald's_Collection_2013_(TCG)`. Not on TCGdex and not on pokemontcg.io | Bulbagarden Archives (browser sitting) |

### Missing cards in sets we hold

| Set | Card | Row source | Image source |
|---|---|---|---|
| 30th Celebration (`30th`) | Mew `B`, Mew `G`, Mew `R` (the three RGB cards) | TCGdex; Bulbapedia counts them too | `https://assets.tcgdex.net/en/me/30th/<B, G or R>/high.webp` |
| MEP Black Star Promos (`mep`) | 099 Greninja ex, 100 Sylveon ex, 120 Celebratory Fanfare | TCGdex | None on TCGdex yet |
| Detective Pikachu (`det1`) | 25 Lt. Yoshida | TCGdex | None on TCGdex |

### Known by count only

Bulbapedia's count is higher than ours and no outside list names the cards.

| Set | Ours | Bulbapedia |
|---|---|---|
| Prize Pack Series One | 158 | 170 |
| Prize Pack Series Two | 139 | 154 |
| Prize Pack Series Three | 155 | 163 |
| Prize Pack Series Eight | 90 | 91 |
| Prize Pack Series Nine | 79 | 80 |
| Trick or Trade 2022 | 29 | 30 |

### Checked and fine

- 174 of Bulbapedia's 183 English sets matched one of ours by name. Of the other nine, two are
  the missing sets above and seven are ours under another name: Expedition (`ecard1`),
  McDonald's Collection 2011 (`2011bw`), SVE and MEE Basic Energies (`sve` 24, `mee` 16),
  Southern Islands (`si1` 18), Pokémon Futsal (`fut2020` 5), Pokémon TCG Classic (102: our
  three decks, their companion rows and one row filed under a lower-case set id).
- TCGdex: 216 sets compared, every other set agrees by number.

### Rows to tidy (not gaps)

- 564 English rows whose id has no `en:` prefix: `sv01` 258, `swsh3` 201, `base1` 102, and one
  each in `clc`, `mcd22`, `sv03.5-upc`. The first three look like second copies of whole sets.
- The single `clc` row (Pikachu 008/034) belongs to `CLC`; it is the 34th card of that deck.

## Japanese

### Missing products

| Product | Cards | Row source | Image source |
|---|---|---|---|
| Starter Set V, five decks (29 November 2019): `SAf` Fighting 25, `SAg` Grass 24, `SAl` Lightning 25, `SAr` Fire 24, `SAw` Water 24 | 122 | Limitless set pages; official folder `SA` (122 entries) | Limitless, `…/tpc/SAf/SAf_<number>_R_JP.png` |
| VMAX starter sets (27 March 2020): `SCr` Charizard 21, `SCd` Grimmsnarl 20 | 41 | Limitless; official folder `SCS` (41 entries) | Limitless, same pattern |
| Charizard VMAX Starter Set 2 (`SC2`, 4 December 2020) | 21 | Limitless; official folder `SC2` | Limitless, same pattern |
| Official folder `MG` (Mega-era decks; product name not established) | 38 | Official card search | Official card search, folder `MG` |
| Official folder `L2-Sb` (LEGEND-era Tyranitar deck) | 20 | Official card search | Official card search, folder `L2-Sb` |
| Official folder `L2-Sh` (LEGEND-era Steelix deck) | 20 | Official card search | Official card search, folder `L2-Sh` |

`MG` holds: ワニノコ, アリゲイツ, メガオーダイルex, マンタイン, サシカマス, カマスジョー, ブリザポス,
オーガポン いどのめん, エモンガ, ワンパチ, パルスワン, ゴース, ゴースト, メガゲンガーex, ヤミラミ, ハブネーク,
ヤブクロン, ダストダス, モルペコ, ミニリュウ, ハクリュー, メガカイリューex, チラーミィ, チラチーノ, トルネロス
and 12 trainers and one energy. The closest set of ours shares 13% of its names.

`L2-Sb` holds: サワムラー, エビワラー, ヨーギラス, サナギラス, ヤミカラス, ドンカラス, デルビル, ヘルガー,
バンギラス (2), スカンプー, スカタンク, trainers and 特殊悪エネルギー. `L2-Sh` holds: ストライク, カイロス,
クヌギダマ, トロピウス, イワーク, フォレトス, ハガネール (2), ハッサム, ココドラ, コドラ, trainers and
特殊鋼エネルギー.

Not gaps: Aura Seeker (78 cards) is released on 27 November 2026. The official folders
`DPs-S`, `MG_pcgbw`, `HSt/HSm`, `HSP*`, `HSZ*`, `BGS*`, `CS1*` are halves of products we hold,
and `BW`, `SM-XY`, `XY`, `ENE`, `?` are catch-all folders.

### Missing cards in sets we hold

Image patterns: Limitless is
`https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpc/<SET>/<SET>_<number>_R_JP.png`;
the official card search is
`https://www.pokemon-card.com/assets/images/card_images/large/<folder>/<file>.jpg` (the file
name comes from the search result, not from the number).

#### 30th Celebration (`M6a`): 94 missing

Ours 82, TCGdex 176, Bulbapedia's Japanese table 176. Row source: TCGdex `M6a`.

With an image on Limitless (numbers up to 103 and the eight energies):

003 バルビート, 004 イルミーゼ, 007 ホウオウ, 011 ラプラス, 013 カイオーガ, 019 ピカチュウ, 020 ピカチュウ,
023 ピカチュウ, 024 ピカチュウ, 030 ピカチュウ, 031 ピカチュウ, 032 ピカチュウ, 034 ピカチュウ, 036 ピカチュウ,
037 ピカチュウ, 038 ピカチュウ, 041 ピカチュウ, 042 ピカチュウ, 045 ピカチュウ, 046 ピカチュウ, 051 ストリンダー,
060 アンノーン, 066 ルナアーラ, 067 コレクレー, 069 ルカリオ, 070 ガマゲロゲ, 072 コライドン, 078 ズルッグ,
081 ジラーチex, 084 ソルガレオ, 088 ボーマンダex, 089 ジャラコ, 090 ジャランゴ, 091 ジャラランガ, 092 ニャース,
095 カビゴン, 096 ププリン, 099 ヒスイ ゾロアーク, 100 イッカネズミ, 102 ポケパッド, 103 ポケモンいれかえ,
and the basic energies 草, 炎, 水, 雷, 超, 闘, 悪, 鋼.

With no image found on TCGdex or Limitless (the official folder `M6a` has thumbnails; a
full-size image needs the browser sitting):

104 アローラ ナッシー, 105 ファイヤー, 106 ラプラス, 107 フリーザー, 108 サンダー, 109 ストリンダー, 110 モルペコ,
111 フワンテ, 112 シャンデラ, 113 ルガルガン, 114 ニドリーナ, 115 アローラ ニャース, 116 ズルッグ,
117 ガラル ニャース, 118 サーフゴー, 119 ジャラランガ, 120 ニャース, 121 メタモン, 122 ヒスイ ゾロア,
123 イッカネズミ, 124 ホゲータex, 125 ゲッコウガex, 126 ピカチュウex, 127 ピカチュウex, 128 ミュウツーex,
129 ミュウex, 130 ニンフィアex, 131 ゲンガーex, 132 ジラーチex, 133 ボーマンダex, 134 ミュウツーex,
135 ミュウex, 140 ニューラ, 141 ひかるセレビィ, 142 ルギア, 146 メタグロス, 150 ゲンガー,
151 ダークライ＆クレセリアLEGEND, 152 ダークライ＆クレセリアLEGEND, 154 レックウザEX, 155 ゲノセクトEX,
158 ソルガレオGX, and ミュウ `B`, `G`, `R`.

#### Start Deck 100 (`SI`): 128 missing

Ours 300, Limitless 427. Row and image source: Limitless `SI`. The official folder confirms 86
of these Pokémon and energies are not in our set under any number.

3 トランセル, 6 メガヤンマ, 7 ヘラクロス, 13 トロピウス, 37 ゴリランダー, 38 ヒメンカ, 40 ワタシラガ, 54 マグカルゴ,
55 エンテイ, 58 コータス, 59 ビクティニV, 66 シシコ, 67 カエンジシ, 68 ヤトウモリ, 69 エンニュート, 90 オクタン,
91 マンタイン, 101 ブイゼル, 102 フローゼル, 109 ブロスター, 116 メッソン, 120 カムカメ, 121 カジリガメ,
128 ライチュウ, 138 プラスル, 139 マイナン, 145 エモンガ, 148 エレザード, 153 ワンパチ, 154 パルスワン,
159 モルペコ, 164 ガラル ヤドン, 169 ガラル フリーザーV, 174 グランブルV, 180 ヤジロン, 182 クレセリア,
184 ココロモリ, 185 シンボラー, 186 ゴビット, 195 スナバァ, 199 ミブリム, 200 テブリム, 201 ブリムオン,
208 マンキー, 209 オコリザル, 218 カポエラー, 232 ランドロス, 236 ヌイコグマ, 237 キテルグマ,
242 サダイジャVMAX, 243 タタッコ, 244 オトスパス, 251 クロバット, 252 ガラル ヤドラン, 257 ガラル ヤドキング,
260 ハリーセン, 264 ガラル ジグザグマ, 268 グレッグル, 274 フシデ, 275 ホイーガ, 276 ペンドラー, 277 ズルッグ,
278 ズルズキン, 279 ヤブクロン, 284 ゴロンダ, 286 ベロバー, 287 ギモー, 300 ボスゴドラVMAX, 301 メタグロスV,
310 アーマーガアVMAX, 311 ゾウドウ, 312 ダイオウドウ, 318 オノンド, 319 オノノクス, 328 オニスズメ,
329 オニドリル, 343 オドシシ, 344 ナマケロ, 345 ヤルキモノ, 346 ケッキング, 353 ヤヤコマ, 354 ヒノヤコマ,
355 ファイアロー, 356 トリミアン, 365 エネルギー回収, 368 エネルギーリサイクル, 371 霧の水晶, 373 スーパーボール,
374 すりかえカップ, 376 ふしぎなアメ, 377 ポケモンいれかえ, 378 ポケモンキャッチャー, 382 いかついメット,
383 学習装置, 388 エール団の応援, 389 カリンの信念, 390 キクコ, 392 クララ, 394 コルニの気合い, 395 サナ,
396 シバ, 397 シャクヤ, 398 ジャッジマン, 399 ジュン, 401 スクールボーイ, 402 ズミ, 403 博士の研究,
404 ピオニー, 405 ヒガナの決意, 406 ボスの指令, 407 マクワ, 408 マリィのプライド, 409 メロン,
410 モノマネむすめ, 411 モミ, 412 いちげきエネルギー, 413 ラッキーエネルギー, 414 れんげきエネルギー,
415 ピカチュウV, 418 ジュン, 419 マリィのプライド, and the unnumbered basic energies 草, 炎, 水, 雷, 超, 闘, 鋼.

#### Sword & Shield promos (`SP`, S-P): 52 missing

Ours 269, Limitless 300, Bulbapedia 350. Paired by hand against Limitless. Row and image source:
Limitless `SP`.

- 15 Pokémon: 34 ヒバニー, 35 モルペコ, 50 メッソン, 68 モルペコ, 75 イーブイ, 131 メッソン,
  160 ガラル バリヤード, 176 キノガッサV, 186 ブースターVMAX, 187 シャワーズVMAX, 188 サンダースVMAX,
  243 ビクティニV, 324 ルギアV, 326 シェイミ, 327 アーケオス.
- 17 basic energies: 83, 90 to 97, 246 to 253.
- 12 trainers with no row of ours: 102 ジムトレーナー, 120 ローズ, 127 プレイヤーズセレモニー, 183 モミ,
  223 クララ, 241 ピオニー, 245 あなぬけのヒモ, 264 キバナ, 285 ハマナのバックアップ, 301 シマボシ,
  317 ネジキ, 328 ダブルターボエネルギー.
- 6 second prints where we hold one row of two: ホップ (5 and 58), きずぐすり (17 and 51),
  モンスターボール (19 and 54), ビート (27 and 56), げんきのハチマキ (55 and 136), マオ&スイレン (89 and
  256). Our row has no number, so which of the two we lack is not known.
- 2 of the 3 unnumbered 勝利の証.

Limitless stops near number 328 and Bulbapedia counts 350, so there may be more above that.

#### Other promo series

| Series | Missing | Row source | Image source |
|---|---|---|---|
| Mega promos (`M-P`) | 10 Pokémon: アイアント, ビリジオン, ニャローテ, マスカーニャ, エモンガ, ワンパチ, パルスワン, ズピカ, ハラバリー, カビゴン | Official card search, folder `M-P` | Same folder |
| Mega promos (`M-P`) | 6 unnumbered 勝利のしるし | Limitless `MP` | None on Limitless |
| Black & White promos (`BWP`) | 16 unnumbered: ビクトリーカップ (9), トロピカルビーチ (2), ヘビーボール, レベルボール, 改造ハンマー, まんたんのくすり, プラズマ団バッジ. We hold a numbered Heavy Ball and a Plasma Badge under `PBG`, so those two need a look first | Limitless `BWP` | None on Limitless |
| Scarlet & Violet promos (`SV-P`) | 12 unnumbered: 勝利のしるし (9), パラダイスリゾート (3) | Limitless `SVP` | Limitless, `…/tpc/SVP/SVP_NAN<1–12>_R_JP.png` |
| XY promos (`XYP`) | 3 unnumbered basic energies: 炎, 闘, フェアリー | Limitless `XYP` | Limitless |
| Sun & Moon promos (`SMP`) | none | | |

#### Decks and older sets

| Set | Missing | Row source | Image source |
|---|---|---|---|
| Virizion deck (`BKv`) | 1 クルミル, 2 クルマユ, 13 ビリジオン, 8 エネルギー転送 | Limitless; the Pokémon confirmed by the official list | Limitless |
| Terrakion deck (`BKt`) | 1 バチュル, 2 デンチュラ, 8 エネルギー転送 | Limitless | Limitless |
| Cobalion deck (`BKc`) | 8 エネルギー転送 | Limitless | Limitless |
| Vending Machine Series 3 (Green) | Kadabra, Haunter (ours 51, Bulbapedia 53) | Bulbapedia | Bulbagarden Archives (browser sitting) |

#### Basic energies that came in a product: 72, low priority

Unnumbered basic energy cards listed with the product by Limitless and seen in the official
folder: Master Deck Build Box MEGA Power Style (`MMBP`) 9 and Speed Style (`MMBS`) 9, Starter
Set SM (`SMA`) 9, Premium Trainer Box (`SMB`) 9, Battle Academy (`SVI`) 8, Starting Set XY
(`HXY`) 6, Master Deck Build Box EX (`MDB`) 5, Sun & Moon plus (`SM1p`) 4, Eevee Heroes VMAX
Special Set (`SP4`) 4, World Championships 2023 deck (`WCS23`) 2, Gengar VMAX High-Class Deck
(`SGG`) 1. Family Pokémon Card Game (`SML`) 6 by the official folder only. Images: Limitless,
same pattern with the letter of the energy type as the number.

### Uncertain

| Item | What is known |
|---|---|
| VSTAR Universe (`S12a`) | Ours 258 equals TCGdex. Bulbapedia counts 262 and the official folder shows 草, 炎, 水, 雷 energies; we hold 超, 闘, 悪, 鋼 as 255 to 258. Possibly 4 missing |
| Pikachu World Collection (`PW`) | Ours 9, Bulbapedia 10. The page has no card table |
| XY promos, three Mega rows | アブソルEX, ラグラージEX, ガブリアスEX on Limitless pair with our M Absol-EX, M Swampert-EX, M Garchomp-EX rows. The label needs an eye check; not a gap |
| Set rows that look like doubles | `jr-moonlit-pursuit-dawn-dash` (135) beside `jr-moonlit-pursuit` (70) and `jr-dawn-dash` (70); the same pattern for the Bastiodon/Rampardos, Heatran vs Regigigas, Magmortar vs Electivire and Dialga & Palkia LV.X products. Not verified |
| Five single `extra-…` rows | Filed under lower-case set ids `cll`, `s8b`, `sm9`, `s-p`, `xy7` |

### Checked and fine

- TCGdex: 120 Japanese sets compared; only `M6a` differs. Limitless: 256 sets compared.
- Bulbapedia counts agree for the promo series P 47, J 2, T 24, ADV-P 63, PLAY 32, PCG-P 154,
  DP-P 127, PPP 7, DPt-P 51, the ADV Expansion Pack 55, and L-P (79 plus our 12 Design Contest
  rows).
- 27 older sets are identical to Bulbapedia's card table name by name (1,613 cards). Fourteen
  more differ only in the language or wording of names.
- Official card search: 257 of 331 folders match a set of ours with no Pokémon or energy absent.

## Not checked at card level

No outside card list was found for these, so a missing card in them would not show here.

- 128 Japanese products: decks, kits, gift boxes, quick construction packs, gym decks, intro
  packs, the yearly energy sets, the 298 miscellaneous promos and the three Classic decks.
- English Prize Pack, Trick or Trade, Classic and promo-pack sets (24 sets, 1,227 cards): set
  count only.
- Japanese sets before Black & White that have no card table on Bulbapedia.
- Cross-language name matching does not pair Mega-EX, V, ex and LV.X names reliably. Differences
  of that kind were looked at by hand and dropped; none is reported as a gap.

## What happens next

The missing rows go through steps 2 and 4 of the plan as a second batch: each row is built from
its source, each image is eye-checked against name, number and set, and the release is replayed
against the panels before staging is switched. Suggested order: Start Deck 100 and the starter
decks (rows and images both on Limitless), the lower numbers of 30th Celebration, the
Sword & Shield promos, then the rest. Delta Reign needs nothing from us until TCGdex publishes
its art. Images from the official card search are thumbnails; whether a source may be mirrored
to the CDN is decided per `docs/card-image-cdn.md` when the batch is built.

## Sources

- TCGdex: `https://api.tcgdex.net/v2/<en|ja>/sets`
- Limitless, Japanese cards: `https://limitlesstcg.com/cards/jp`
- Official Japanese card search: `https://www.pokemon-card.com/card-search/`
- Bulbapedia: `https://bulbapedia.bulbagarden.net/wiki/List_of_Japanese_Pokémon_Trading_Card_Game_expansions`
  and `…/wiki/List_of_Pokémon_Trading_Card_Game_expansions`
- pokemontcg.io: `https://api.pokemontcg.io/v2/sets`
- PokéAPI species names (to pair Japanese and English names): `https://pokeapi.co/api/v2/pokemon-species`
