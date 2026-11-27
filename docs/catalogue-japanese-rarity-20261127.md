# Japanese rarities from Limitless: catalogue RAR3 (2026-11-27)

After RAR1 (Delta Reign) and RAR2 (English), 18,546 of 28,554 Japanese cards had no rarity:
TCGdex has almost none for Japanese sets (380 of 494 sets had none at all). RAR3 fills 3,908 of them
from Limitless's set lists and is served on staging. Production is not touched. Every one of the
18,546 decisions, with the Limitless row it used and its reason, is in
`docs/catalogue-japanese-rarity-20261127.json`.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-RAR3-20261127`, schema `pokesingle_completion_20261127_rar3` |
| Parent served before | `PS-CATALOGUE-EN-JA-RAR2-20261127` (unchanged) |
| Cards digest | `4bed9a1f8d8b8541a86c087b61b1ab72` → `6515177d4b23f3329d82409d5ca53ccd` (62,091 rows; the old value was reproduced first) |
| Reference features | `20261127-rar2` → `20261127-rar3`, manifest `91392d90…` → `73c3902991d709f53ecfe821169e858ea2c5c452290788e12ceffa035fb5c2ab` (664 rebuilt) |
| Artwork bundle, vectors | unchanged (`20261120-img2`) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/catalogue-rar3-20261127` (returns to RAR2) |
| Switch | FORWARD OK, healthy, restarts 0, OOM false, `catalogue corrections applied=0` |
| Run folder | `data/catalogue-gaps/rar3-ja-20261127` (Limitless pages, decisions, SQL, feature build, replay, score) |

## Source and rules

Limitless (`https://limitlesstcg.com/cards/jp/<set>?display=list`, robots.txt allows it) lists
every card of its 266 Japanese sets with a rarity column. All 266 lists were downloaded once, one
page every 1.5 s (`fetch_limitless_sets.py`, `parse_limitless_sets.py`: 20,317 rows). A card gets
a rarity (`decide_japanese_rarities.py`) only when all of these hold:

1. **Same card.** Exactly one Limitless row with the card's set code (or one of 20 listed aliases,
   `catalogue-japanese-rarity-set-aliases-20261127.json`, e.g. our `XY8-Br` is Limitless `XY8r`)
   and number.
2. **Names agree.** The same text; or, for an English row name, the same species through the
   catalogue's own table (`api/app/recognition/assets/ja_species_names.json`); or a Trainer or
   Energy whose Limitless type agrees. 2,252 same name, 1,420 same species, 236 Trainer/Energy.
3. **Limitless gives a rarity.** A blank is not taken as "no rarity": Limitless leaves some printed
   codes blank (ACE SPEC, Character Rare).
4. **The label maps without ambiguity.** Limitless's label is mapped to the catalogue's own label,
   learnt from Japanese cards that already have both: the same set first, then the same era
   (BW, XY, SM, S, SV, M), at least 90% one way; else a fixed table for unambiguous names
   (Common, Uncommon, Rare, Double Rare → Double rare, Art Rare → Illustration rare, Special Art
   Rare → Special illustration rare, Shiny Rare → Shiny rare, …). Limitless "Secret Rare" (the
   printed SR) maps to the catalogue's "Ultra Rare", as it does for Japanese cards already rated.
5. **Not Limitless "Holo Rare".** In S9–S12 Limitless uses "Holo Rare" for HR (Hyper Rare,
   rainbow): S9a-090 デンボク prints HR. Those 35 stay empty.

Printed codes checked on 12 card images: BW9 060 C, BW9 062 C, XY2 050 C, XY2 026 U, XY4 044 R,
SV3 130 SR, SV3 115 AR, SV1S 088 AR, SV2P 094 SAR, SV7a 089 SAR, SV4a 208 S all agree with the
filled rarity; S9a 090 HR is the case that led to rule 5.

Filled, 68 sets: Common 1,330, Uncommon 962, Rare 412, Ultra Rare 346, Double rare 253, Shiny rare
228, Illustration rare 160, Special illustration rare 109, Triple Rare 43, Shiny Ultra Rare 41,
Amazing Rare 9, Radiant Rare 7, Character Rare 6, Character Super Rare 2. The 664 with a full-art
rarity had their reference features rebuilt with the full-art box.

## Left empty (14,638)

| Cards | Reason |
|---:|---|
| 7,606 | Limitless shows no rarity (mostly cards that print none: high-class pack normals, starter decks, promos) |
| 6,711 | Not on Limitless: Diamond & Pearl, Platinum, LEGEND, older promos and most recovery-made `jr-` sets |
| 205 | The label is ambiguous for that set or era (mostly Limitless "Ultra Rare", the printed UR) or has no mapping |
| 77 | Names do not agree |
| 35 | Limitless "Holo Rare" (HR) |
| 4 | Several Limitless rows for one number |

## Gate (1,891 photos, against RAR2's run)

Same image, code, settings, shards and lanes as RAR1 and RAR2; scored with `score_gate.py` and the
corrected labels. 134 panel photos show a card whose rarity changed, 19 of them a card whose
features were rebuilt.

| Panel | Photos | Right first | Wrong first | Right offered | Upper bound |
|---|---:|---|---|---|---|
| dev | 681 | 636 → 636 | 3 → 3 | 663 → 663 | 1.3% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

No answer changed in any field.

## After the switch

`ja:SV3-115` Illustration rare, `ja:SV2P-094` Special illustration rare, `ja:SV4a-208` Shiny rare,
`ja:BW9-060` Common, `ja:SV3-130` Ultra Rare; `ja:S9a-090` stays empty. Shiny Treasure ex (`SV4a`)
now offers six rarities.

## Found, not changed

27 Japanese cards in S10a, S10P, S11 and S11a already carry "Holo Rare" from TCGdex, but they are
HR (Hyper Rare) cards, so their features use the normal box. A later release should relabel them
and rebuild their features.

## Going back

`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-rar3-20261127 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
