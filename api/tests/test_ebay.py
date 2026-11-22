"""eBay graded asking prices: which listings count, and what the app is sent.

The title rules are checked against titles eBay returned on 21 November 2026.
"""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import connect, init_catalog
from app.ebay import (
    Ebay, GradedCard, graded_listings, item_confirms, listing_is, name_from_listing, names_grade,
)
from app.routes.ebay import router

CHARIZARD = GradedCard("Charizard", "4", "PSA", "9", total=102, year=1999, set_name="Base Set")
UMBREON = GradedCard("Umbreon VMAX", "215", "PSA", "10", total=203, year=2021, set_name="Evolving Skies")
MEW_JA = GradedCard("Mew ex", "205", "PSA", "10", total=165, year=2023, japanese=True,
                    set_name="Pokemon Card 151")


_ids = iter(range(1, 10**6))


def _item(title, value, *, currency="USD", options=("FIXED_PRICE",), country="US"):
    return {
        "itemId": f"v1|{next(_ids)}|0",
        "title": title,
        "price": {"value": str(value), "currency": currency},
        "buyingOptions": list(options),
        "itemLocation": {"country": country},
        "itemWebUrl": "https://www.ebay.com/itm/1",
    }


def test_a_title_must_name_the_grader_and_the_exact_grade():
    assert names_grade("Charizard 4/102 Base Set PSA 10 GEM MINT", "PSA", "10")
    assert names_grade("charizard psa10", "PSA", "10")
    assert names_grade("Charizard PSA-9", "PSA", "9")
    assert names_grade("Charizard (PSA MINT 9) - Unlimited", "PSA", "9")
    assert names_grade("[PSA: 9] Charizard 4/102", "PSA", "9")
    assert names_grade("Pikachu CGC Gem Mint 10", "CGC", "10")
    assert names_grade("Charizard BGS 9.5 Gem", "BGS", "9.5")
    assert not names_grade("Charizard PSA 10", "PSA", "1")
    assert not names_grade("Charizard PSA 9.5", "PSA", "9")
    assert not names_grade("Charizard PSA 9", "PSA", "9.5")
    assert not names_grade("Charizard CGC 10", "PSA", "10")
    assert not names_grade("Charizard 10 HP", "PSA", "10")
    assert not names_grade("Venusaur 15/102 Light Play PSA 7+", "PSA", "7")
    # Another slab in the same title.
    assert not names_grade("[BGS 9.5] PIKACHU BASE SET PSA 10", "PSA", "10")
    assert not names_grade("Eevee 51/64 Jungle Regular CGC 9 Mint Psa 9", "PSA", "9")


def test_real_titles_of_the_card_count():
    for title in (
        "Charizard 4/102 Base Set Holo Rare 1999 English PSA 9 Cert 01462769",
        "PSA 9 1999 Pokémon TCG Base Set Charizard 4/102 Holo English",
        "Charizard (PSA MINT 9) - Unlimited - Holo - Pokemon Base Set 1999 #4/102",
    ):
        assert listing_is(title, CHARIZARD), title
    assert listing_is("UMBREON VMAX 2021 POKEMON EVOLVING SKIES 215/203 SEC RARE HOLO FA PSA 10", UMBREON)
    assert listing_is("Mew ex #205/165 Special Art Rare Pokemon Card 151 (JP) 2023 PSA 10", MEW_JA)


def test_real_titles_of_something_else_do_not():
    for title in (
        # A 2021 reprint that kept the number.
        "Pokemon 2021 Charizard 4/102 Holo Celebrations Classic Collection PSA 9",
        "PSA 9 Charizard Holo 4/102 Celebrations Classic Collection Pokemon TCG",
        # Another card that only mentions this one.
        "PSA 9 Articuno 074/070 No Charizard 4/102 Lugia 149/147 30th Anniversary BGS",
        # Other languages, another edition, another grade.
        "1999 Pokemon FRENCH Unlimited Base Set Charizard Holo 4/102 PSA 9 MINT",
        "Charizard Holo PSA 9 ITALIAN - Base Set - 4/102 - WOTC",
        "1999 Pokemon Base Set 1st Edition Charizard 4/102 PSA 9",
        "Wizards of the Coast 1999 Pokemon Base Set Charizard 4/102 Holo PSA 8",
        "Charizard 4/102 Base Set Shadowless PSA 9",
    ):
        assert not listing_is(title, CHARIZARD), title
    for title in (
        # Raw cards dressed as slabs.
        "Umbreon VMAX (Alternate Art) 215/203 SWSH07: Evolving Skies NOT PSA 10",
        "Umbreon VMAX (Alternate Art Secret) 215/203 PSA 10 WORTHY!",
        "Umbreon VMAX | 215/203 | Evolving Skies | Mint | Alt Art | PSA10 ?",
        "Pokemon Umbreon Vmax Evolving Skies 215/203 Full Alt Art PSA 10 Korean",
        "1 of 1 Signed Erica Schroeder on slab Umbreon Vmax Evolving skies 215/203 PSA 10",
        "PSA 10 Umbreon VMAX - 215/203 - Evolving Skies - Read Description",
        "PSA 10 Umbreon VMAX SEQUENTIAL Set ~ 214/203 & 215/203 Evolving Skies",
        "Umbreon V 215/203 Evolving Skies PSA 10",
    ):
        assert not listing_is(title, UMBREON), title
    # A Japanese card needs a title that says so; an English one must not.
    assert not listing_is("Pokemon 2023 Sv2a Card 151 Mew ex 205/165 Special Art Rare Holo PSA 10", MEW_JA)
    assert not listing_is("PSA 10 Mew ex 205/165 Ultra Premium Collection Metal Pokemon 151 Japanese", MEW_JA)
    english = GradedCard("Rayquaza VMAX", "218", "PSA", "9", total=203, year=2021)
    assert not listing_is("PSA 9 Rayquaza VMAX Alternate Art 218/203 Evolving Skies Japanese 2021", english)


def test_the_printing_follows_the_copy():
    reprint = GradedCard("Charizard", "4", "PSA", "10", total=102, year=2021,
                         set_name="Celebrations: Classic Collection")
    assert listing_is("PSA 10 Charizard Holo 4/102 - 2021 Pokemon Celebrations Classic Collection", reprint)
    assert not listing_is("Charizard 4/102 Base Set Holo Rare 1999 English PSA 10", reprint)
    eevee = GradedCard("Eevee", "51", "PSA", "9", total=64, year=1999, set_name="Jungle",
                       first_edition=True)
    assert listing_is("1999 Pokemon Jungle 1st Edition #51/64 Eevee PSA 9 MINT", eevee)
    assert not listing_is("Pokemon TCG Eevee 51/64 Jungle Rare PSA 9", eevee)
    reverse = GradedCard("Pikachu", "025", "CGC", "10", total=165, year=2023, reverse=True)
    assert listing_is("Pikachu Pokemon 151 25/165 Reverse Holo CGC Gem Mint 10", reverse)
    assert not listing_is("Pikachu Pokemon 151 25/165 Holo CGC Gem Mint 10", reverse)
    # A shop's stamped copy is another printing.
    bulbasaur = GradedCard("Bulbasaur", "001", "PSA", "10", total=165, year=2023, set_name="151")
    assert listing_is("Bulbasaur 001/165 Pokemon 151 PSA 10 GEM MINT", bulbasaur)
    assert not listing_is("Bulbasaur 001/165 Best Buy Exclusive 151 Pokemon PSA 10", bulbasaur)
    # CGC's Pristine 10 is a dearer slab than its Gem Mint 10.
    plain = GradedCard("Pikachu", "025", "CGC", "10", total=165, year=2023)
    assert not listing_is("Pikachu 2023 Pokemon 151 CGC PRISTINE 10 #25/165", plain)


def test_a_slab_label_title_is_matched_by_its_set():
    # The catalogue numbers this reprint 001 of 30; sellers write the "#4"
    # printed on it, and no "x/y" at all.
    classic = GradedCard("Charizard", "001", "PSA", "10", total=30, year=2026,
                         set_name="30th Classic Collection", set_code="30th-c", unique_name=True)
    label = "2026 Pokemon 30C EN-30th Celebration Classic Collection #4 Charizard PSA 10"
    assert classic.search == "Charizard 001/30 PSA 10"
    assert classic.set_search == "Charizard 30th classic collection PSA 10"
    assert listing_is(label, classic)
    # Several cards in one listing are not the card.
    base_charizard = GradedCard("Charizard", "4", "PSA", "9", total=102, year=1999,
                                set_name="Base Set", unique_name=True)
    assert not listing_is(
        "1999 Pokemon Base Set Unlimited Charizard Blastoise Venusaur PSA 9 - BIG THREE", base_charizard)
    assert not listing_is("1999 Pokemon Base Set Unlimited Charizard Holo PSA 9", base_charizard)
    assert listing_is("1999 POKEMON BASE SET UNLIMITED #4 CHARIZARD-HOLO PSA 9", base_charizard)
    # Not the 2021 reprint, nor the 1999 card.
    assert not listing_is("PSA 10 Charizard Holo 4/102 - 2021 Pokemon Celebrations Classic Collection", classic)
    assert not listing_is("Charizard 4/102 Base Set Holo Rare 1999 English PSA 10", classic)
    # A name that is not the only one in its set still needs its number.
    shared = GradedCard("Pikachu", "5", "PSA", "10", total=30, year=2026,
                        set_name="30th Classic Collection", set_code="30th-c")
    assert listing_is("2026 Pokemon 30th Celebration Classic Collection #5 Pikachu PSA 10", shared)
    assert not listing_is("2026 Pokemon 30th Celebration Classic Collection #9 Pikachu PSA 10", shared)
    # Without "x/y" the set must be named: a bare number is any card.
    lugia = GradedCard("Lugia V", "186", "PSA", "10", total=195, year=2022, set_name="Silver Tempest")
    assert listing_is("2022 POKEMON SWORD & SHIELD SILVER TEMPEST #186 LUGIA V PSA 10", lugia)
    assert not listing_is("2022 POKEMON #186 LUGIA V FULL ART PSA 10", lugia)
    # With no set total on file, "x/y" alone is not enough either.
    radiant = GradedCard("Charizard", "001", "PSA", "10", set_name="30th Classic Collection")
    assert not listing_is("PSA 10 Radiant Charizard - svF - 001/038 - Kouki Saitou", radiant)
    # A Japanese set is named by its code.
    mew = GradedCard("Mew ex", "205", "PSA", "10", total=165, year=2023, japanese=True,
                     set_name="ポケモンカード151", set_code="sv2a")
    assert mew.set_search == "Mew ex sv2a Japanese PSA 10"
    assert listing_is("2023 POKEMON JAPANESE SV2A-POKEMON CARD 151 #205 MEW EX PSA 10", mew)
    # The 151 set's labels read "MEW EN-151": another card of it holds
    # every word of "Mew ex" and the number 151, but says "#185".
    mew151 = GradedCard("Mew ex", "151", "PSA", "10", total=165, year=2023,
                        set_name="151", set_code="sv03.5")
    assert listing_is("2023 POKEMON MEW EN-151 #151 MEW EX PSA 10", mew151)
    assert not listing_is("2023 POKEMON MEW EN-151 #185 ARBOK ex ULTRA RARE PSA 10", mew151)
    assert not listing_is("2023 POKEMON MEW EN 151 ULTRA RARE #192 ZAPDOS EX PSA 10", mew151)
    # No "#" at all: the bare "151" is the set, not the card's number.
    assert not listing_is("Zapdos ex Ultra Rare Pokemon Scarlet & Violet 151 MEW PSA 10 GEM MT", mew151)
    assert not listing_is("Mew ex SR Pokemon Card 151 PSA 10", mew151)
    assert listing_is("MEW EX 151/165 Double Rare RR Pokemon EN 151 S&V English 2023 PSA 10 GEM", mew151)
    # A bare number that is not a set word still counts.
    umbreon = GradedCard("Umbreon VMAX", "215", "PSA", "10", total=203, year=2021,
                         set_name="Evolving Skies", set_code="swsh7")
    assert listing_is("Umbreon VMAX 215 Evolving Skies Secret Rare Holo 2021 PSA 10 67718943", umbreon)
    # Outside the reprint sets a name alone never stands in for the number.
    arbok = GradedCard("Arbok", "24", "PSA", "10", total=165, year=2023,
                       set_name="151", set_code="sv03.5", unique_name=True)
    assert not listing_is("2023 POKEMON MEW EN-151 #185 ARBOK ex ULTRA RARE PSA 10", arbok)
    # "Base Set 2" is another set.
    base = GradedCard("Charizard", "4", "PSA", "9", total=102, year=1999, set_name="Base Set")
    assert listing_is("1999 POKEMON GAME BASE SET #4 CHARIZARD HOLO PSA 9", base)
    assert not listing_is("2000 POKEMON BASE SET 2 #4 CHARIZARD HOLO PSA 9", base)


def test_a_promo_is_found_by_its_code():
    venusaur = GradedCard("Venusaur EX", "XY28", "PSA", "10", total=211, year=2014,
                          set_name="XY Black Star Promos", set_code="xyp")
    # Never "XY28/211": promos carry no total.
    assert venusaur.search == "Venusaur EX XY28 PSA 10"
    assert venusaur.set_search == "Venusaur EX xy promo PSA 10"
    for title in (
        "2014 POKEMON XY BLACK STAR PROMO #XY28 VENUSAUR EX PSA 10",
        "Venusaur EX XY28 Black Star Promo Holo PSA 10 GEM MINT",
        "Pokemon Venusaur EX XY28 PSA 10",
    ):
        assert listing_is(title, venusaur), title
    assert not listing_is("2014 POKEMON XY BLACK STAR PROMO #XY29 CHARIZARD EX PSA 10", venusaur)
    assert not listing_is("Venusaur EX XY123 Black Star Promo PSA 10", venusaur)
    assert not listing_is("Venusaur EX XY28 Jumbo Oversized Promo PSA 10", venusaur)
    # Merchandise a seller filed as a graded single card.
    jirachi = GradedCard("Jirachi", "XY67a", "PSA", "10", total=211,
                         set_name="XY Black Star Promos", set_code="xyp")
    assert listing_is("2017 POKEMON XY BLACK STAR PROMO #XY67A FULL ART/JIRACHI PSA 10", jirachi)
    assert not listing_is(
        "READ Jirachi 2017 Premium Trainer XY Collection Promo XY67a LARGE BLANKET 50x60",
        jirachi, graded=True)
    # A promo series runs for years: the title's year is not held against it.
    assert listing_is("2017 POKEMON XY BLACK STAR PROMO #XY28 FULL ART/VENUSAUR EX PSA 10", venusaur)
    # A numbered promo is named by its series and "promo".
    resort = GradedCard("Paradise Resort", "150", "PSA", "10", total=225, year=2024,
                        set_name="SVP Black Star Promos", set_code="svp")
    assert listing_is("2024 POKEMON SVP EN-SV BLACK STAR PROMO #150 PARADISE RESORT PSA 10", resort)
    assert not listing_is("2024 POKEMON SVP EN-SV BLACK STAR PROMO #151 PARADISE RESORT PSA 10", resort)
    # A trainer gallery number.
    mimikyu = GradedCard("Mimikyu V", "TG16", "PSA", "10", total=30, year=2022,
                         set_name="Brilliant Stars Trainer Gallery", set_code="swsh9tg")
    assert mimikyu.search == "Mimikyu V TG16 PSA 10"
    assert listing_is("PSA 10 Mimikyu V TG16/TG30 Pokemon Brilliant Stars Trainer Gallery", mimikyu)
    assert not listing_is("PSA 10 Mimikyu VMAX TG17/TG30 Pokemon Brilliant Stars", mimikyu)
    # A reprint set's card under the number it reprints.
    magikarp = GradedCard("Shining Magikarp", "CC010", "PSA", "10", total=25, year=2021,
                          set_name="Celebrations Classic Collection", set_code="cel25cc",
                          unique_name=True)
    assert listing_is("2021 Pokemon Celebrations Classic Collection Shining Magikarp 66/64 PSA 10", magikarp)
    assert not listing_is("2001 Pokemon Neo Revelation Shining Magikarp 66/64 PSA 10", magikarp)


def test_a_word_of_the_sets_own_name_does_not_rule_a_listing_out():
    zygarde = GradedCard("Mega Zygarde ex", "124", "PSA", "10", total=88, year=2026,
                         set_name="Perfect Order", set_code="me03")
    assert listing_is("2026 POKEMON PERFECT ORDER #124 MEGA ZYGARDE EX PSA 10", zygarde)
    assert listing_is("Mega Zygarde ex 124/088 Perfect Order SIR PSA 10 GEM MINT", zygarde)
    # "Perfect 10" and "Pristine 10" are still dearer slabs, for any set.
    cgc = GradedCard("Mega Zygarde ex", "124", "CGC", "10", total=88, year=2026,
                     set_name="Perfect Order", set_code="me03")
    assert listing_is("Mega Zygarde ex 124/088 Perfect Order CGC 10 Gem Mint", cgc)
    assert not listing_is("Mega Zygarde ex 124/088 Perfect Order CGC Perfect 10", cgc)
    assert not listing_is("Mega Zygarde ex 124/088 Perfect Order CGC Pristine 10", cgc)
    assert not listing_is("Mega Zygarde ex 124/088 Perfect Order booster box PSA 10", zygarde)


def test_a_japanese_promo_is_found_by_its_series_and_number():
    pikachu = GradedCard("Pikachu ex", "132", "PSA", "10", total=132, year=2025, japanese=True,
                         set_name="メガ プロモカード", set_code="m-p")
    assert pikachu.promo
    assert pikachu.search == "Pikachu ex 132 Japanese PSA 10"
    assert pikachu.set_search == "Pikachu ex m-p Japanese PSA 10"
    assert listing_is("2026 POKEMON JAPANESE M-P PROMO #132 PIKACHU EX PSA 10", pikachu)
    assert not listing_is("2026 POKEMON JAPANESE M-P PROMO #131 PIKACHU EX PSA 10", pikachu)
    assert not listing_is("PSA 10 Pikachu ex McDONALD'S PROMO 132/M-P Pokemon card Set of 3 Japanese", pikachu)
    eevee = GradedCard("Eevee", "196", "PSA", "8", total=288, year=2022, japanese=True,
                       set_name="スカーレット&バイオレット プロモカード", set_code="sv-p")
    assert listing_is("Pokemon TCG SV-P Promo Eevee 196/SV-P Holo JP 2024 PSA 8 Graded", eevee)
    assert listing_is("2024 POKEMON JPN SV-P PROMO LET'S START POKECA BATTLE CAMPAIGN #196 EEVEE PSA 8", eevee)
    # No number, or a grade that is only a guess.
    assert not listing_is("2024 POKEMON JAPANESE SV-P PROMO BATTLE CAMPAIGN EEVEE PSA 8", eevee)
    assert not listing_is("PSA 8 2024 Pokemon Eevee SV-P JP Promo Card #196 PSA 8 or lower", eevee)
    # A Japanese set's code says Japanese where the word is missing.
    flygon = GradedCard("Flygon GX", "098", "PSA", "10", total=95, year=2019, japanese=True,
                        set_name="オルタージェネシス", set_code="sm12")
    assert listing_is("Flygon GX SR SM12 Alter Genesis 098/095 PSA 10", flygon)
    assert not listing_is("Flygon GX SR Alter Genesis 098/095 PSA 10", flygon)


def test_more_raw_cards_other_languages_and_reverse_copies_are_left_out():
    mew = GradedCard("Mew ex", "158", "PSA", "10", total=128, year=2026,
                     set_name="30th Celebration", set_code="30th")
    assert listing_is("2026 POKEMON 30C EN-30TH CELEBRATION FUTURISTIC RARE #158 MEW EX PSA 10", mew)
    for title in (
        "Mew Ex 158/128 Futuristic Rare Pokémon TCG: 30th Celebration PSA 10 CONTENDOR",
        "Mew ex 158/128 30th Celebration Futuristic Rare NM/Mint – Strong PSA 10 Candidat",
        "Mew ex 158/128 30th Celebration PSA10 Equivalent",
    ):
        assert not listing_is(title, mew), title
    herdier = GradedCard("Herdier", "155", "PSA", "10", total=86, year=2025, set_name="White Flare")
    assert listing_is("2025 POKEMON WHT EN-WHITE FLARE ILLUSTRATION RARE #155 HERDIER PSA 10", herdier)
    assert not listing_is("Pokemon Terribark Herdier 155/086 PSA 10 DE White Flames White Flare IR", herdier)
    # A Japanese reverse holo is a "Mirror" or "Rev.Foil".
    pikachu = GradedCard("Pikachu", "014", "PSA", "9", total=71, year=2022, japanese=True,
                         set_name="ダークファンタズマ", set_code="s10a")
    assert listing_is("Pikachu C S10a 014/071 PSA 9 Japanese Pokémon", pikachu)
    assert not listing_is("PSA 9 Pikachu Mirror s10a 014/071 Pokemon Japanese", pikachu)
    assert not listing_is("PSA 9 Pikachu C 014/071 S10a Rev.Foil Dark Phantasma 2022 Pokemon Card Japanese", pikachu)
    mirror = GradedCard("Pikachu", "014", "PSA", "9", total=71, japanese=True,
                        set_name="ダークファンタズマ", set_code="s10a", reverse=True)
    assert listing_is("PSA 9 Pikachu Mirror s10a 014/071 Pokemon Japanese", mirror)
    # A number the grader does not give is not this grade.
    assert not names_grade("PSA 20 Seismitoad 105/086 Sv: Black Bolt Holo PSA 10", "PSA", "10")


def test_guessed_grades_and_dearer_slabs_are_left_out():
    zygarde = GradedCard("Mega Zygarde ex", "124", "PSA", "9", total=88, year=2026,
                         set_name="Perfect Order", set_code="me03")
    assert not listing_is(
        "Mega Zygarde EX Hyper Rare Gold Perfect Order 124/088 English (Likely PSA 9)",
        zygarde, graded=True)
    zacian = GradedCard("Zacian V", "GG48", "CGC", "10", total=70, year=2023,
                        set_name="Crown Zenith Galarian Gallery", set_code="swsh12.5gg")
    assert listing_is("Pokemon ZACIAN V Galarian Gallery Holo #GG48/GG70 Crown Zenith CGC 10 Gem Mint", zacian)
    assert not listing_is("2023 POKEMON CROWN ZENITH GALARIAN GALLERY - HOLO #GG48 ZACIAN V CGC 10 PERFECT", zacian)
    surfer = GradedCard("Surfer", "293", "CGC", "10", total=217, year=2026, set_name="Ascended Heroes")
    assert not listing_is("Surfer SIR Holo 293/217 2026 Pokemon Ascended Heroes CGC 10 Pristine BL", surfer)
    # A promo's own stamp belongs to it; a staff copy never does.
    charizard = GradedCard("Charizard", "SWSH066", "PSA", "10", total=307,
                           set_name="SWSH Black Star Promos", set_code="swshp")
    assert listing_is("2020 Pokemon TCG Charizard SWSH066 Promo Holo Prerelease PSA 10", charizard)
    assert not listing_is("2020 Pokemon TCG Charizard SWSH066 Promo Prerelease STAFF PSA 10", charizard)
    # Outside promos a stamp is another printing, wherever it comes in the title.
    plain = GradedCard("Charizard", "25", "PSA", "10", total=185, year=2020, set_name="Vivid Voltage")
    assert not listing_is("Charizard 25/185 Vivid Voltage Holo Prerelease Stamped PSA 10", plain)


def test_only_buy_it_now_listings_count_and_a_stray_cheap_one_is_left_out():
    items = [_item(f"Charizard 4/102 Base Set 1999 PSA 9 #{n}", n) for n in (3500, 3900, 4000, 4000, 4200)]
    items += [
        _item("Charizard 4/102 Base Set 1999 PSA 9", 900),
        _item("Charizard 4/102 Base Set 1999 PSA 9", 3000, options=("AUCTION",)),
        _item("Charizard 4/102 Base Set 1999 PSA 9", 3100, currency="EUR"),
        _item("Charizard 4/102 Base Set 1999 PSA 9", "free"),
    ]
    listings = graded_listings(items, CHARIZARD, currency="USD")
    # 900 is under half the middle price: a mislisting, not the market.
    assert [item["amount"] for item in listings] == [3500, 3900, 4000, 4000, 4200]


def test_a_japanese_cards_english_name_comes_from_its_cardmarket_address():
    base = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Pokemon-Card-151/"
    assert name_from_listing(base + "Mew-ex-V1-sv2a205") == "Mew ex"
    assert name_from_listing(base + "Mistys-Psyduck-sv9a022?language=7") == "Mistys Psyduck"
    assert name_from_listing(base + "Pikachu") == "Pikachu"
    assert name_from_listing(None) == ""


def _reader(calls, items, *, by_ebay=(), details=None):
    """[items] answer the searches by words, [by_ebay] the ones that ask for
    eBay's own grader and grade; [details] is what opening a listing shows."""
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/token"):
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["x-ebay-c-marketplace-id"] == "EBAY_US"
        if "/item/" in path:
            calls.append("open")
            item_id = path.rsplit("/", 1)[-1]
            if details is not None and item_id not in details:
                return httpx.Response(404)
            return httpx.Response(200, json=(details or {}).get(item_id, {}))
        assert request.url.params["category_ids"] == "183454"
        graded = "aspect_filter" in request.url.params
        assert request.url.params["filter"] == (
            "buyingOptions:{FIXED_PRICE},conditionIds:{2750}" if graded else "buyingOptions:{FIXED_PRICE}"
        )
        calls.append(("ebay:" if graded else "") + request.url.params["q"])
        if graded:
            calls.append(request.url.params["aspect_filter"])
        return httpx.Response(200, json={"itemSummaries": list(by_ebay) if graded else items})

    return Ebay("id", "secret", client=httpx.Client(
        base_url="https://ebay.test", transport=httpx.MockTransport(handle)))


PIKACHU = GradedCard("Pikachu", "58", "PSA", "10", total=102, year=1999, set_name="Base Set")


def test_the_cheapest_five_are_averaged_and_asked_once_a_day():
    calls: list[str] = []
    prices = [100, 110, 120, 130, 140, 900, 1500]
    reader = _reader(calls, [_item(f"Pikachu 58/102 Base Set PSA 10 #{n}", n) for n in prices])
    first = reader.graded(PIKACHU)
    assert first["average"] == 120.0
    assert first["count"] == 7
    assert [item["amount"] for item in first["listings"]] == [100, 110, 120, 130, 140]
    assert "id" not in first["listings"][0]
    assert first["observed_at"].endswith("Z")
    assert reader.graded(PIKACHU) == first
    psa10 = "categoryId:183454,Professional Grader:{Professional Sports Authenticator (PSA)},Grade:{10}"
    # Four searches: eBay's own grade fields by number and by set, then the
    # grade in words by number and by set. The five cheapest are opened.
    assert calls == [
        "ebay:Pikachu 58/102", psa10, "ebay:Pikachu base", psa10,
        "Pikachu 58/102 PSA 10", "Pikachu base PSA 10",
        "open", "open", "open", "open", "open",
    ]
    reader.close()


def test_one_dear_listing_does_not_move_the_price():
    prices = [680, 750, 775, 800, 2999]
    reader = _reader([], [_item(f"Pikachu 58/102 Base Set PSA 10 #{n}", n) for n in prices])
    # The middle of the five, where their mean would be 1,200.80.
    assert reader.graded(PIKACHU)["average"] == 775.0
    reader.close()


def test_an_answer_stands_a_day_for_everyone_and_survives_a_restart(tmp_path):
    found = [_item(f"Pikachu 58/102 Base Set PSA 10 #{n}", n) for n in (100, 110, 120)]

    def reader(calls):
        return Ebay("id", "secret", path=tmp_path / "ebay.sqlite", client=httpx.Client(
            base_url="https://ebay.test",
            transport=httpx.MockTransport(lambda request: (
                calls.append(request.url.path),
                httpx.Response(200, json=(
                    {"access_token": "token", "expires_in": 7200}
                    if request.url.path.endswith("/token")
                    else {"itemSummaries": found} if "search" in request.url.path else {}
                )),
            )[1]),
        ))

    first_calls: list[str] = []
    first = reader(first_calls)
    # Nothing held yet: the cache alone has no answer, and eBay is not asked.
    assert first.kept(PIKACHU) is None and first_calls == []
    answer = first.graded(PIKACHU)
    assert answer["average"] == 110.0 and first_calls
    assert first.kept(PIKACHU) == answer
    first.close()

    # Another server process, another collector: read from disk, no eBay call.
    second_calls: list[str] = []
    second = reader(second_calls)
    assert second.kept(PIKACHU) == answer
    assert second.graded(PIKACHU) == answer and second_calls == []
    # Another grade of the same card is another question.
    other = GradedCard("Pikachu", "58", "PSA", "9", total=102, year=1999, set_name="Base Set")
    assert second.kept(other) is None
    # After a day it is asked again.
    second.reuse_s = 0
    assert second.kept(PIKACHU) is None
    second.close()


def test_ebays_own_grade_stands_in_for_a_title_that_does_not_say_it():
    catalogue = "Pikachu 58/102 Base Set Holo"
    assert not listing_is(catalogue, PIKACHU)
    assert listing_is(catalogue, PIKACHU, graded=True)
    # Still not another slab, card or language.
    assert not listing_is("Pikachu 58/102 Base Set Holo BGS 9.5", PIKACHU, graded=True)
    assert not listing_is("Pikachu 58/102 Base Set PSA 9", PIKACHU, graded=True)
    assert not listing_is("Pikachu 60/64 Jungle Holo", PIKACHU, graded=True)
    reader = _reader(
        [],
        [_item("Pikachu 58/102 Base Set PSA 10", 300)],
        by_ebay=[_item(catalogue, 100), _item(catalogue, 200), _item("Raichu 14/102 Base Set", 5)],
    )
    answer = reader.graded(PIKACHU)
    assert [item["amount"] for item in answer["listings"]] == [100, 200, 300]
    assert answer["average"] == 200.0
    reader.close()


def test_an_opened_listing_must_agree_before_it_counts():
    psa = {"name": "Professional Grader", "values": [{"content": "Professional Sports Authenticator (PSA)"}]}
    ten = {"name": "Grade", "values": [{"content": "10"}]}
    aspect = lambda name, value: {"name": name, "value": value}  # noqa: E731
    good = {"conditionDescriptors": [psa, ten],
            "localizedAspects": [aspect("Card Number", "58/102"), aspect("Language", "English")]}
    assert item_confirms(good, PIKACHU)
    assert item_confirms({}, PIKACHU)  # nothing recorded, nothing against it
    assert item_confirms({"localizedAspects": [aspect("Card Number", "#58"), aspect("Language", "Not Specified")]}, PIKACHU)
    for wrong in (
        {"conditionDescriptors": [psa, {"name": "Grade", "values": [{"content": "9"}]}]},
        {"conditionDescriptors": [{"name": "Professional Grader",
                                   "values": [{"content": "Certified Guaranty Company (CGC)"}]}, ten]},
        {"localizedAspects": [aspect("Card Number", "60/64")]},
        {"localizedAspects": [aspect("Card Number", "58/108")]},
        {"localizedAspects": [aspect("Language", "Japanese")]},
        {"localizedAspects": [aspect("Language", "Italian")]},
    ):
        assert not item_confirms(wrong, PIKACHU), wrong
    japanese = GradedCard("Mew ex", "205", "PSA", "10", total=165, japanese=True)
    assert item_confirms({"localizedAspects": [aspect("Language", "Japanese")]}, japanese)
    assert not item_confirms({"localizedAspects": [aspect("Language", "English")]}, japanese)

    # The cheapest listing turns out to be a PSA 9 once opened: it is left
    # out, and the next ones make the average.
    items = [_item(f"Pikachu 58/102 Base Set PSA 10 #{n}", n) for n in (50, 100, 110, 120)]
    details = {item["itemId"]: good for item in items[1:]}
    details[items[0]["itemId"]] = {"conditionDescriptors": [psa, {"name": "Grade", "values": [{"content": "9"}]}]}
    reader = _reader([], items, details=details)
    answer = reader.graded(PIKACHU)
    assert [item["amount"] for item in answer["listings"]] == [100, 110, 120]
    assert answer["average"] == 110.0 and answer["count"] == 3
    reader.close()


def test_every_grader_the_app_offers_has_ebays_name():
    from app.ebay import GRADER_NAMES, GRADERS

    assert set(GRADER_NAMES) == set(GRADERS)
    calls: list[str] = []
    card = GradedCard("Pikachu", "58", "TAG", "9.5", total=102, set_name="Base Set")
    reader = _reader(calls, [])
    reader.graded(card)
    assert "categoryId:183454,Professional Grader:{Technical Authentication & Grading (TAG)},Grade:{9.5}" in calls
    reader.close()


def test_too_few_listings_give_no_average_but_are_still_listed():
    reader = _reader([], [_item("Pikachu 58/102 PSA 10", 100), _item("Pikachu 58/102 PSA 10", 120)])
    answer = reader.graded(PIKACHU)
    # No average from two listings, but the two are still sent.
    assert answer["average"] is None and answer["count"] == 2
    assert [item["amount"] for item in answer["listings"]] == [100, 120]
    reader.close()


def test_the_route_builds_the_search_from_the_catalogue_card(tmp_path):
    calls: list[str] = []
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    for values in (
        {"id": "en:base1-58", "name": "Pikachu", "language": "en", "set_id": "base1",
         "set_name": "Base Set", "collector_number": "58"},
        {"id": "ja:SV2a-205", "name": "ミュウex", "language": "ja", "set_id": "SV2a",
         "set_name": "Pokemon Card 151", "collector_number": "205",
         "cardmarket_url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Pokemon-Card-151/Mew-ex-V1-sv2a205"},
        {"id": "de:x-1", "name": "Pikachu", "language": "de", "set_id": "x",
         "set_name": "X", "collector_number": "1"},
    ):
        values.update({
            row[1]: "" for row in catalog.execute("PRAGMA table_info(cards)")
            if row[3] and row[4] is None and row[1] not in values
        })
        catalog.execute(
            f"INSERT INTO cards ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            list(values.values()),
        )
    catalog.execute("INSERT INTO set_totals VALUES ('en', 'base1', 102, '')")
    catalog.execute("INSERT INTO set_releases VALUES ('en', 'base1', '1999-01-09', '')")
    catalog.execute("INSERT INTO set_totals VALUES ('ja', 'SV2a', 165, '')")
    catalog.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.dbs = type("Dbs", (), {"catalog": catalog})()
    app.state.ebay = _reader(calls, [
        _item(f"1999 Pokemon Base Set Pikachu 58/102 PSA 10 #{n}", n) for n in (10, 20, 30)
    ] + [_item("2021 Pikachu 58/102 Celebrations PSA 10", 1)])
    client = TestClient(app)
    ask = lambda **params: client.get("/api/v1/ebay/graded", params=params)  # noqa: E731

    body = ask(card_id="en:base1-58", grader="psa", grade="10").json()
    assert body["enabled"] is True and body["average"] == 20.0 and len(body["listings"]) == 3
    assert "Pikachu 58/102 PSA 10" in calls and "Pikachu base PSA 10" in calls
    ask(card_id="ja:SV2a-205", grader="PSA", grade="10")
    assert "Mew ex 205/165 Japanese PSA 10" in calls
    assert "ebay:Mew ex 205/165 Japanese" in calls
    # No eBay search for a language sellers do not title reliably.
    before = len(calls)
    assert ask(card_id="de:x-1", grader="PSA", grade="10").json() == {
        "enabled": True, "average": None, "currency": "USD", "count": 0,
        "listings": [], "observed_at": None,
    }
    assert len(calls) == before
    assert ask(card_id="en:base1-58", grader="XYZ", grade="10").status_code == 422
    assert ask(card_id="en:base1-58", grader="PSA", grade="11").status_code == 422
    assert ask(card_id="nope", grader="PSA", grade="10").status_code == 404

    # The cache alone: the card just asked about is there, another is not,
    # and eBay is not asked for it.
    held = ask(card_id="en:base1-58", grader="PSA", grade="10", cached_only="true").json()
    assert held["average"] == 20.0
    before = len(calls)
    miss = ask(card_id="en:base1-58", grader="PSA", grade="9", cached_only="true").json()
    assert miss["enabled"] is True and miss["average"] is None and miss["listings"] == []
    assert len(calls) == before

    app.state.ebay = None
    assert ask(card_id="en:base1-58", grader="PSA", grade="10").json()["enabled"] is False
