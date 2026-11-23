"""The era of every expansion, stored with its release date.

`set_releases.era` is worked out once per set and kept in the database, so
the set list, the era filter and any later screen agree. In order:

1. [ERA_TABLE]: sets whose code and date mislead (a deck sold before its era's
   first booster, a code that reads as another era, a reprint collection).
2. The set's code, where it names its era (`sv10`, `SM9`, `XY7`).
3. The release date: TCGdex's, else [RELEASE_DATES], researched for sets
   TCGdex has none for.
4. `other` when none applies, logged so it can be looked at.

A row whose `era_source` is `manual` was set by hand and is never replaced.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Newest first; the app names them.
ERAS = (
    "mega_evolution",
    "scarlet_violet",
    "sword_shield",
    "sun_moon",
    "xy",
    "black_white",
    "heartgold_soulsilver",
    "platinum",
    "diamond_pearl",
    "ex",
    "e_card",
    "neo",
    "original",
    "other",
)

# Sets the code and date rules would place wrongly, with the reason.
ERA_TABLE: dict[tuple[str, str], str] = {
    # Codes starting with M that are not Mega Evolution: a 2012 and two 2015
    # deck boxes.
    ("ja", "MDB"): "black_white",  # Master Deck Build Box EX, Sep 2012
    ("ja", "MMBP"): "xy",  # M Master Deck Build Box Power Style, Aug 2015
    ("ja", "MMBS"): "xy",  # M Master Deck Build Box Speed Style, Aug 2015
    # Sword & Shield products sold before the first Japanese Sword & Shield
    # booster (6 Dec 2019).
    ("ja", "SP"): "sword_shield",  # Sword & Shield Promos, Nov 2019
    ("ja", "SAf"): "sword_shield",  # Starter Set V, Nov 2019
    ("ja", "SAr"): "sword_shield",
    ("ja", "SAg"): "sword_shield",
    ("ja", "SAl"): "sword_shield",
    ("ja", "SAw"): "sword_shield",
    # XY Beginning Set, Nov 2013, before the first XY booster (Dec 2013).
    ("ja", "HXY"): "xy",
    # Reprint collections of every era.
    ("ja", "CLK"): "other",
    ("ja", "CLL"): "other",
    ("ja", "CLF"): "other",
    ("ja", "cll"): "other",
    ("ja", "pooka-clk"): "other",
    ("ja", "pooka-cll"): "other",
    ("ja", "pooka-clf"): "other",
    ("en", "CLB"): "other",
    ("en", "CLC"): "other",
    ("en", "clc"): "other",
    ("en", "CLV"): "other",
    ("en", "pooka-clb"): "other",
    ("en", "pooka-clc"): "other",
    ("en", "pooka-clv"): "other",
    # Catch-all groups, not products.
    ("ja", "jr-miscellaneous-decks"): "other",
    ("ja", "jr-miscellaneous-promos"): "other",
    ("en", "miscp"): "other",
    # English promotions TCGdex has no date for.
    ("en", "BKPR"): "diamond_pearl",  # Burger King DP Promos, 2008
    ("en", "BKPPR"): "platinum",  # Burger King Platinum Promos, 2009
    ("en", "tot22"): "sword_shield",  # Trick or Trade 2022
    ("en", "tot23"): "scarlet_violet",  # Trick or Trade 2023
    ("en", "tot24"): "scarlet_violet",  # Trick or Trade 2024
}

# Release dates of Japanese sets TCGdex has none for, from TCG Collector's
# Japanese set list (tcgcollector.com/sets/jp), read 23 November 2026.
RELEASE_DATES: dict[tuple[str, str], str] = {
    ("ja", key): value
    for key, value in {
    "jr-miscellaneous-decks": "1996-10-15",
    "jr-miscellaneous-promos": "1996-10-15",
    "jr-vending-machine-series-1-blue": "1998-03-23",
    "jr-hanada-city-gym-deck": "1998-04-26",
    "jr-nivi-city-gym-deck": "1998-04-26",
    "jr-vending-machine-series-2-red": "1998-06-17",
    "jr-kuchiba-city-gym-deck": "1998-07-25",
    "jr-tamamushi-city-gym-deck": "1998-07-25",
    "jr-vending-machine-series-3-green": "1998-11-24",
    "jr-quick-starter-gift-set-green": "1998-12-04",
    "jr-quick-starter-gift-set-red": "1998-12-04",
    "jr-guren-town-gym-deck": "1999-02-26",
    "jr-yamabuki-city-gym-deck": "1999-02-26",
    "jr-southern-islands": "1999-07-17",
    "jr-intro-pack-bulbasaur": "1999-07-30",
    "jr-intro-pack-squirtle": "1999-07-30",
    "jr-neo-premium-file-1": "1999-12-10",
    "jr-neo-premium-file-2": "2000-07-07",
    "jr-neo-premium-file-3": "2000-11-23",
    "jr-intro-pack-neo-chikorita": "2001-04-06",
    "jr-intro-pack-neo-totodile": "2001-04-06",
    "jr-p-promos": "2001-07-01",
    "jr-leaders-pokemon-movie-limited-edition": "2001-07-07",
    "jr-j-promos": "2001-08-01",
    "jr-tropical-mega-battle": "2001-08-26",
    "jr-pokemon-e-starter-deck": "2001-12-01",
    "jr-t-promos": "2002-01-01",
    "jr-mcdonald-s-pokemon-e-minimum-pack": "2002-01-26",
    "jr-theater-limited-vs-pack": "2002-07-13",
    "jr-adv-promos": "2003-01-01",
    "jr-play-promos": "2003-01-01",
    "jr-adv-expansion-pack": "2003-01-31",
    "jr-mudkip-constructed-starter-deck": "2003-01-31",
    "jr-torchic-constructed-starter-deck": "2003-01-31",
    "jr-treecko-constructed-starter-deck": "2003-01-31",
    "pooka-adv-expansion-pack": "2003-01-31",
    "jr-miracle-of-the-desert": "2003-04-18",
    "pooka-miracle-of-the-desert": "2003-04-18",
    "jr-flygon-constructed-starter-deck": "2003-06-25",
    "jr-rulers-of-the-heavens": "2003-06-25",
    "jr-salamence-constructed-starter-deck": "2003-06-25",
    "pooka-rulers-of-the-heavens": "2003-06-25",
    "jr-movie-commemoration-vs-pack": "2003-07-19",
    "jr-aqua-deck-kit": "2003-10-24",
    "jr-magma-deck-kit": "2003-10-24",
    "jr-magma-vs-aqua-two-ambitions": "2003-10-24",
    "jr-gift-box-latias": "2003-11-17",
    "jr-gift-box-latios": "2003-11-17",
    "jr-metagross-constructed-starter-deck": "2004-01-16",
    "jr-undone-seal": "2004-01-16",
    "pooka-undone-seal": "2004-01-16",
    "jr-pcg-promos": "2004-02-01",
    "jr-venusaur-charizard-blastoise-random-constructed-starter-decks": "2004-03-19",
    "jr-deoxys-constructed-starter-deck": "2004-07-01",
    "jr-rayquaza-constructed-starter-deck": "2004-07-01",
    "jr-movie-commemoration-vs-pack-sky-splitting-deoxys": "2004-07-17",
    "jr-black-deck-kit": "2004-10-15",
    "jr-silver-deck-kit": "2004-10-15",
    "jr-emerald-gift-box-deoxys": "2004-11-19",
    "jr-emerald-gift-box-rayquaza": "2004-11-19",
    "jr-fighting-quick-construction-pack": "2005-01-16",
    "jr-fire-quick-construction-pack": "2005-01-16",
    "jr-grass-quick-construction-pack": "2005-01-16",
    "jr-lightning-quick-construction-pack": "2005-01-16",
    "jr-psychic-quick-construction-pack": "2005-01-16",
    "jr-water-quick-construction-pack": "2005-01-16",
    "jr-feraligatr-constructed-starter-deck": "2005-03-05",
    "jr-meganium-constructed-starter-deck": "2005-03-05",
    "jr-typhlosion-constructed-starter-deck": "2005-03-05",
    "jr-pokepark-blue": "2005-03-18",
    "jr-pokepark-forest": "2005-03-18",
    "jr-mirage-s-mew-constructed-starter-deck": "2005-06-30",
    "jr-master-kit-bulbasaur": "2005-07-15",
    "jr-master-kit-side-deck": "2005-07-15",
    "jr-master-kit-torchic": "2005-07-15",
    "jr-movie-commemoration-vs-pack-aura-s-lucario": "2005-07-16",
    "jr-holon-research-tower-fire-quarter-deck": "2005-09-30",
    "jr-holon-research-tower-lightning-quarter-deck": "2005-09-30",
    "jr-holon-research-tower-water-quarter-deck": "2005-09-30",
    "jr-mew-lucario-gift-box-crawdaunt": "2005-11-16",
    "jr-mew-lucario-gift-box-lucario": "2005-11-16",
    "jr-mew-lucario-gift-box-mew": "2005-11-16",
    "jr-mew-lucario-gift-box-mightyena": "2005-11-16",
    "jr-mew-lucario-gift-box-pokemon": "2005-11-16",
    "jr-earth-s-groudon-ex-constructed-starter-deck": "2006-03-03",
    "jr-ocean-s-kyogre-ex-constructed-starter-deck": "2006-03-03",
    "jr-imprison-gardevoir-ex-constructed-standard-deck": "2006-06-29",
    "jr-shockwave-tyranitar-ex-constructed-standard-deck": "2006-06-29",
    "jr-movie-commemoration-vs-pack-sea-s-manaphy": "2006-07-15",
    "EN06": "2006-10-27",
    "jr-entry-pack": "2006-10-27",
    "DP1": "2006-11-30",
    "DPP": "2006-12-01",
    "jr-10th-movie-commemoration-set": "2007-01-14",
    "DP2": "2007-03-02",
    "jr-bastiodon-the-defender-constructed-half-deck": "2007-03-02",
    "jr-bastiodon-the-defender-rampardos-the-attacker-constructed-half-decks": "2007-03-02",
    "jr-rampardos-the-attacker-constructed-half-deck": "2007-03-02",
    "PPP": "2007-05-01",
    "DP3": "2007-07-05",
    "jr-dialga-lv-x-constructed-standard-deck": "2007-07-05",
    "jr-dialga-palkia-lv-x-constructed-standard-decks": "2007-07-05",
    "jr-palkia-lv-x-constructed-standard-deck": "2007-07-05",
    "pooka-wcp": "2007-07-05",
    "WCP": "2007-07-05",
    "jr-dawn-dash": "2007-10-26",
    "jr-magmortar-vs-electivire-deck-kit": "2007-10-26",
    "jr-magmortar-vs-electivire-deck-kit-electivire": "2007-10-26",
    "jr-magmortar-vs-electivire-deck-kit-magmortar": "2007-10-26",
    "jr-moonlit-pursuit": "2007-10-26",
    "jr-entry-pack-08": "2007-11-30",
    "jr-cry-from-the-mysterious": "2008-03-14",
    "jr-heatran-vs-regigigas-deck-kit": "2008-03-14",
    "jr-heatran-vs-regigigas-deck-kit-heatran": "2008-03-14",
    "jr-heatran-vs-regigigas-deck-kit-regigigas": "2008-03-14",
    "jr-temple-of-anger": "2008-03-14",
    "DPS": "2008-07-10",
    "jr-giratina-vs-dialga-deck-kit-dialga": "2008-07-10",
    "jr-giratina-vs-dialga-deck-kit-giratina": "2008-07-10",
    "jr-11th-movie-commemoration-set": "2008-07-19",
    "DPtP": "2008-10-01",
    "DPt1": "2008-10-10",
    "jr-dpt-entry-pack-dialga": "2008-10-10",
    "jr-dpt-entry-pack-giratina": "2008-10-10",
    "jr-dpt-entry-pack-palkia": "2008-10-10",
    "jr-dpt-gift-box-chimchar": "2008-11-20",
    "jr-dpt-gift-box-pikachu": "2008-11-20",
    "jr-dpt-gift-box-piplup": "2008-11-20",
    "jr-dpt-gift-box-turtwig": "2008-11-20",
    "DPt2": "2008-12-26",
    "jr-infernape-vs-gallade-sp-deck-kit-gallade": "2008-12-26",
    "jr-infernape-vs-gallade-sp-deck-kit-infernape": "2008-12-26",
    "DPt3": "2009-03-06",
    "jr-garchomp-vs-charizard-sp-deck-kit-charizard": "2009-03-06",
    "jr-garchomp-vs-charizard-sp-deck-kit-garchomp": "2009-03-06",
    "DPtM": "2009-04-18",
    "DPtR": "2009-04-18",
    "DPtS": "2009-04-18",
    "DPt4": "2009-07-08",
    "DPt4-Sgf": "2009-07-08",
    "DPt4-Slp": "2009-07-08",
    "jr-melee-pokemon-scramble": "2009-07-10",
    "jr-movie-commemoration-random-pack": "2009-07-18",
    "LP": "2009-09-01",
    "EN09": "2009-10-09",
    "L1HG": "2009-10-09",
    "L1SS": "2009-10-09",
    "jr-battle-starter-deck-blastoise": "2009-11-20",
    "jr-battle-starter-deck-magmortar": "2009-11-20",
    "jr-battle-starter-deck-raichu": "2009-11-20",
    "jr-battle-starter-deck-torterra": "2009-11-20",
    "jr-leafeon-vs-metagross-expert-deck-leafeon": "2009-11-20",
    "jr-leafeon-vs-metagross-expert-deck-metagross": "2009-11-20",
    "jr-steelix-constructed-standard-deck": "2010-02-11",
    "jr-tyranitar-constructed-standard-deck": "2010-02-11",
    "pc-reviving-legends": "2010-02-11",
    "pooka-l2": "2010-02-11",
    "pc-lost-link": "2010-04-16",
    "pc-clash-at-the-summit": "2010-07-08",
    "PW": "2010-07-08",
    "CS1": "2010-09-18",
    "HS": "2010-10-29",
    "BWP": "2010-12-01",
    "BW1-Bb": "2010-12-17",
    "BW1-Bw": "2010-12-17",
    "BKc": "2011-03-18",
    "BKt": "2011-03-18",
    "BKv": "2011-03-18",
    "BTV": "2011-06-17",
    "pc-red-collection": "2011-07-15",
    "HSp": "2011-08-05",
    "BW3-Bh": "2011-09-16",
    "BW3-Bp": "2011-09-16",
    "BKR": "2011-10-21",
    "BKZ": "2011-10-21",
    "pooka-bkr": "2011-10-21",
    "BGS": "2011-11-18",
    "HSP": "2011-11-18",
    "pc-dark-rush": "2011-12-16",
    "pc-dragon-selection": "2012-01-27",
    "BW5-Brn": "2012-03-16",
    "BW5-Brz": "2012-03-16",
    "GBR": "2012-03-16",
    "SZD": "2012-03-16",
    "HSZ": "2012-04-20",
    "KLD": "2012-04-20",
    "BW6-Bc": "2012-07-13",
    "BW6-Bf": "2012-07-13",
    "EN12": "2012-09-14",
    "MDB": "2012-09-14",
    "pc-plasma-gale": "2012-09-14",
    "pooka-mdb": "2012-09-14",
    "PPD": "2012-09-14",
    "BKB": "2012-10-19",
    "BKW": "2012-10-19",
    "pooka-bkb": "2012-10-19",
    "PBG": "2012-11-16",
    "pooka-wak": "2012-11-16",
    "WAK": "2012-11-16",
    "BW8-Brf": "2012-12-14",
    "BW8-Brn": "2012-12-14",
    "pc-shiny-collection": "2013-02-01",
    "KpK": "2013-03-15",
    "pc-megalo-cannon": "2013-03-15",
    "jr-mewtwo-vs-genesect-deck-kit-genesect": "2013-07-13",
    "jr-mewtwo-vs-genesect-deck-kit-mewtwo": "2013-07-13",
    "XYP": "2013-08-01",
    "HXY": "2013-11-08",
    "pc-xy-beginning-set": "2013-11-08",
    "EN13": "2013-12-13",
    "XY1-Bx": "2013-12-13",
    "XY1-By": "2013-12-13",
    "X30": "2014-01-31",
    "Y30": "2014-01-31",
    "pc-wild-blaze": "2014-03-15",
    "XYA": "2014-03-15",
    "pc-rising-fist": "2014-06-14",
    "pc-phantom-gate": "2014-09-13",
    "XYB": "2014-09-13",
    "XYC": "2014-11-14",
    "XY5-Bg": "2014-12-13",
    "XY5-Bt": "2014-12-13",
    "pc-emerald-break": "2015-03-14",
    "XYD": "2015-03-14",
    "XYE": "2015-07-18",
    "MMBP": "2015-08-07",
    "MMBS": "2015-08-07",
    "EN15": "2015-09-26",
    "SNPo": "2015-09-26",
    "SNPr": "2015-09-26",
    "XY8-Bb": "2015-09-26",
    "XY8-Br": "2015-09-26",
    "XYF": "2015-10-09",
    "pc-rage-of-the-broken-sky": "2015-12-11",
    "pooka-cp3": "2016-01-29",
    "20th": "2016-02-27",
    "XYG": "2016-03-18",
    "XYH": "2016-03-18",
    "XY11-Bb": "2016-06-17",
    "XY11-Br": "2016-06-17",
    "pooka-cp5": "2016-07-16",
    "SMP": "2016-11-01",
    "EN16": "2016-12-09",
    "SMA": "2016-12-09",
    "SMB": "2016-12-09",
    "SMP1": "2016-12-15",
    "SMC": "2017-03-17",
    "SMD": "2017-04-21",
    "XY": "2017-04-21",
    "SME": "2017-11-10",
    "SMF": "2017-12-08",
    "SMG": "2018-02-16",
    "SMH": "2018-07-13",
    "EN18": "2018-11-23",
    "SMI": "2018-11-23",
    "SMJ": "2018-12-07",
    "SMK": "2019-01-25",
    "SMN": "2019-03-01",
    "SML": "2019-03-15",
    "SMM": "2019-05-31",
    "jr-extra-regulation-box": "2019-10-04",
    "SP": "2019-11-01",
    "EN19": "2019-11-29",
    "SAf": "2019-11-29",
    "SAg": "2019-11-29",
    "SAl": "2019-11-29",
    "SAr": "2019-11-29",
    "SAw": "2019-11-29",
    "SB": "2019-12-06",
    "SP1": "2019-12-27",
    "jr-grimmsnarl-vmax-starter-set": "2020-03-27",
    "SCr": "2020-03-27",
    "pc-explosive-flame-walker": "2020-04-24",
    "SD": "2020-07-10",
    "SP2": "2020-10-23",
    "SC2": "2020-12-04",
    "SEF": "2020-12-04",
    "SEK": "2020-12-04",
    "SF": "2021-01-22",
    "SP3": "2021-04-23",
    "SGG": "2021-05-28",
    "SGI": "2021-05-28",
    "SP4": "2021-05-28",
    "SH": "2021-07-09",
    "SP5": "2021-08-20",
    "S8a-P": "2021-10-22",
    "SJ": "2021-11-05",
    "S8a-G": "2021-12-01",
    "EN21": "2021-12-17",
    "SI": "2021-12-17",
    "SK": "2022-01-14",
    "SLD": "2022-02-25",
    "SLL": "2022-02-25",
    "SN": "2022-03-01",
    "SPD": "2022-07-15",
    "SPZ": "2022-07-15",
    "SP6": "2022-08-05",
    "SO": "2022-11-04",
    "jr-scarlet-violet-energies": "2023-01-20",
    "SVAL": "2023-01-20",
    "SVAM": "2023-01-20",
    "SVAW": "2023-01-20",
    "SVB": "2023-01-20",
    "SVC": "2023-03-24",
    "SVP1": "2023-05-19",
    "SVD": "2023-07-07",
    "pooka-wcs23": "2023-07-28",
    "SVF": "2023-07-28",
    "SVEL": "2023-09-22",
    "SVEM": "2023-09-22",
    "CLF": "2023-10-31",
    "CLK": "2023-10-31",
    "CLL": "2023-10-31",
    "cll": "2023-10-31",
    "pooka-clf": "2023-10-31",
    "pooka-clk": "2023-10-31",
    "pooka-cll": "2023-10-31",
    "SVG": "2023-11-10",
    "SVHK": "2024-01-26",
    "SVHM": "2024-01-26",
    "SVI": "2024-03-08",
    "SVJL": "2024-05-17",
    "SVJP": "2024-05-17",
    "SVM": "2024-11-22",
    "SVN": "2025-01-24",
    "SVOD": "2025-02-21",
    "SVOM": "2025-02-21",
    "jr-mega-evolution-energies": "2025-08-01",
    "MA": "2025-08-01",
    "MBD": "2025-09-05",
    "MBG": "2025-09-05",
    "MP1": "2025-12-19",
    "MEE": "2026-07-31",
    "MEM": "2026-07-31",
    "MEZ": "2026-07-31",
    "MG": "2026-11-13",
    }.items()
}

# English codes that name their era, the longer first. The letter after the
# code must be a number, a dot or p/e/a, so `mfb` is not Mega Evolution's.
_ENGLISH_CODES = (
    ("me", "mega_evolution"),
    ("swsh", "sword_shield"),
    ("sv", "scarlet_violet"),
    ("sm", "sun_moon"),
    ("xy", "xy"),
    ("bw", "black_white"),
    ("hgss", "heartgold_soulsilver"),
    ("pl", "platinum"),
    ("dp", "diamond_pearl"),
    ("ex", "ex"),
    ("ecard", "e_card"),
    ("neo", "neo"),
    ("gym", "original"),
    ("base", "original"),
)
_ENGLISH_NEXT = re.compile(r"[\d.pea]")

# Japanese and Chinese codes: the era's code, then a number, a dash or the
# end, or the longer codes of that era's decks and promos.
_ASIAN_CODES = (
    (re.compile(r"^M(\d|-|[A-Z]{1,3}$|[A-Z]\d)"), "mega_evolution"),
    (re.compile(r"^SV"), "scarlet_violet"),
    (re.compile(r"^SM"), "sun_moon"),
    (re.compile(r"^S\d"), "sword_shield"),
    (re.compile(r"^(XY|X\d|Y\d|CP\d)"), "xy"),
    (re.compile(r"^BW"), "black_white"),
    (re.compile(r"^(L\d|LL|HS)"), "heartgold_soulsilver"),
    (re.compile(r"^DPt"), "platinum"),
    (re.compile(r"^DP"), "diamond_pearl"),
    (re.compile(r"^(PCG|ADV)"), "ex"),
    (re.compile(r"^E\d"), "e_card"),
    (re.compile(r"^neo"), "neo"),
    (re.compile(r"^PMCG"), "original"),
)

# The first release of each era, newest first. Japanese sets came out months
# before their English counterparts.
_ENGLISH_STARTS = (
    ("2025-09-25", "mega_evolution"),
    ("2023-03-31", "scarlet_violet"),
    ("2019-11-15", "sword_shield"),
    ("2017-02-03", "sun_moon"),
    ("2014-02-05", "xy"),
    ("2011-04-25", "black_white"),
    ("2010-02-10", "heartgold_soulsilver"),
    ("2009-02-11", "platinum"),
    ("2007-05-01", "diamond_pearl"),
    ("2003-06-18", "ex"),
    ("2002-09-15", "e_card"),
    ("2000-12-16", "neo"),
    ("0000-00-00", "original"),
)
_ASIAN_STARTS = (
    ("2025-07-01", "mega_evolution"),
    ("2023-01-20", "scarlet_violet"),
    ("2019-12-06", "sword_shield"),
    ("2016-11-01", "sun_moon"),
    ("2013-12-01", "xy"),
    ("2010-09-18", "black_white"),
    ("2009-07-10", "heartgold_soulsilver"),
    ("2008-09-01", "platinum"),
    ("2006-09-28", "diamond_pearl"),
    ("2003-01-01", "ex"),
    ("2001-12-01", "e_card"),
    ("2000-02-01", "neo"),
    ("0000-00-00", "original"),
)


def _code_era(language: str, set_id: str) -> str | None:
    if language == "en":
        lowered = set_id.lower()
        for code, era in _ENGLISH_CODES:
            if lowered.startswith(code) and (
                len(lowered) == len(code) or _ENGLISH_NEXT.match(lowered[len(code)])
            ):
                return era
        return None
    for pattern, era in _ASIAN_CODES:
        if pattern.match(set_id):
            return era
    return None


def _date_era(language: str, release_date: str | None) -> str | None:
    if not release_date:
        return None
    for start, era in _ENGLISH_STARTS if language == "en" else _ASIAN_STARTS:
        if release_date >= start:
            return era
    return None


def set_era(language: str, set_id: str, release_date: str | None) -> tuple[str, str]:
    """The era of one set and how it was found: `table`, `code`, `date` or
    `none`."""
    key = (language, set_id)
    if key in ERA_TABLE:
        return ERA_TABLE[key], "table"
    if era := _code_era(language, set_id):
        return era, "code"
    if era := _date_era(language, release_date or RELEASE_DATES.get(key)):
        return era, "date"
    return "other", "none"


def refresh_set_eras(conn: sqlite3.Connection, *, catalog: sqlite3.Connection | None = None) -> int:
    """Store the era, and a researched release date where TCGdex has none, of
    every set the catalogue holds. Rows set by hand (`era_source = 'manual'`)
    are kept. Returns how many rows changed."""
    source = catalog if catalog is not None else conn
    sets = {
        (str(row[0] or "en").lower(), str(row[1]))
        for row in source.execute("SELECT DISTINCT language, set_id FROM cards")
    }
    stored = {
        (str(row[0]), str(row[1])): (row[2], row[3], row[4])
        for row in conn.execute("SELECT language, set_id, release_date, era, era_source FROM set_releases")
    }
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = 0
    unplaced = []
    with conn:
        for language, set_id in sorted(sets):
            date, era_now, source_now = stored.get((language, set_id), (None, None, None))
            if source_now == "manual":
                continue
            release_date = date or RELEASE_DATES.get((language, set_id))
            era, how = set_era(language, set_id, release_date)
            if how == "none":
                unplaced.append(f"{language}:{set_id}")
            if (date, era_now, source_now) == (release_date, era, how):
                continue
            conn.execute(
                """INSERT INTO set_releases (language, set_id, release_date, fetched_at, era, era_source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (language, set_id) DO UPDATE SET
                  release_date = COALESCE(set_releases.release_date, excluded.release_date),
                  era = excluded.era, era_source = excluded.era_source""",
                (language, set_id, release_date, now, era, how),
            )
            changed += 1
    log.info("set eras refreshed changed=%s sets=%s unplaced=%s", changed, len(sets), len(unplaced))
    if unplaced:
        log.info("set eras unplaced %s", " ".join(unplaced[:80]))
    return changed
