"""eBay graded asking prices: which listings count, and what the app is sent.

The title rules are checked against titles eBay returned on 21 November 2026.
"""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import connect, init_catalog
from app.ebay import Ebay, GradedCard, graded_listings, listing_is, name_from_listing, names_grade
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
                        set_name="30th Classic Collection")
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
    # Outside the reprint sets a name alone never stands in for the number.
    arbok = GradedCard("Arbok", "24", "PSA", "10", total=165, year=2023,
                       set_name="151", set_code="sv03.5", unique_name=True)
    assert not listing_is("2023 POKEMON MEW EN-151 #185 ARBOK ex ULTRA RARE PSA 10", arbok)
    # "Base Set 2" is another set.
    base = GradedCard("Charizard", "4", "PSA", "9", total=102, year=1999, set_name="Base Set")
    assert listing_is("1999 POKEMON GAME BASE SET #4 CHARIZARD HOLO PSA 9", base)
    assert not listing_is("2000 POKEMON BASE SET 2 #4 CHARIZARD HOLO PSA 9", base)


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


def _reader(calls, items):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/oauth2/token"):
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["x-ebay-c-marketplace-id"] == "EBAY_US"
        assert request.url.params["category_ids"] == "183454"
        assert request.url.params["filter"] == "buyingOptions:{FIXED_PRICE}"
        calls.append(request.url.params["q"])
        return httpx.Response(200, json={"itemSummaries": items})

    return Ebay("id", "secret", client=httpx.Client(
        base_url="https://ebay.test", transport=httpx.MockTransport(handle)))


PIKACHU = GradedCard("Pikachu", "58", "PSA", "10", total=102, year=1999, set_name="Base Set")


def test_the_cheapest_five_are_averaged_and_asked_once_in_six_hours():
    calls: list[str] = []
    prices = [100, 110, 120, 130, 140, 900, 1500]
    reader = _reader(calls, [_item(f"Pikachu 58/102 Base Set PSA 10 #{n}", n) for n in prices])
    first = reader.graded(PIKACHU)
    assert first["average"] == 120.0
    assert first["count"] == 7
    assert [item["amount"] for item in first["listings"]] == [100, 110, 120, 130, 140]
    assert first["observed_at"].endswith("Z")
    assert reader.graded(PIKACHU) == first
    # One token and two searches, by number and by set.
    assert calls == [
        "/identity/v1/oauth2/token",
        "/buy/browse/v1/item_summary/search",
        "Pikachu 58/102 PSA 10",
        "/buy/browse/v1/item_summary/search",
        "Pikachu base PSA 10",
    ]
    reader.close()


def test_too_few_listings_give_no_average():
    reader = _reader([], [_item("Pikachu 58/102 PSA 10", 100), _item("Pikachu 58/102 PSA 10", 120)])
    answer = reader.graded(PIKACHU)
    assert answer["average"] is None and answer["listings"] == [] and answer["count"] == 2
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
    assert "Pikachu 58/102 PSA 10" in calls and calls[-1] == "Pikachu base PSA 10"
    ask(card_id="ja:SV2a-205", grader="PSA", grade="10")
    assert "Mew ex 205/165 Japanese PSA 10" in calls
    assert calls[-1] == "Mew ex pokemon 151 Japanese PSA 10" or calls[-1] == "Mew ex 151 Japanese PSA 10"
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

    app.state.ebay = None
    assert ask(card_id="en:base1-58", grader="PSA", grade="10").json()["enabled"] is False
