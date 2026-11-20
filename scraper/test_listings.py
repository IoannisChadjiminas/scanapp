from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parent))

from allow import cardmarket_expansion_listing
from listings import parse_expansion_listing
from browser import run_attempt

URL = "https://www.cardmarket.com/en/Pokemon/Expansions/MEGA-Starter-Set-Mega-Diancie-ex?page=2"


def test_expansion_allowlist_accepts_only_bounded_cardmarket_listing_urls():
    assert cardmarket_expansion_listing(URL)
    assert not cardmarket_expansion_listing("http://www.cardmarket.com/en/Pokemon/Expansions/Set")
    assert not cardmarket_expansion_listing("https://evil.example/en/Pokemon/Expansions/Set")
    assert not cardmarket_expansion_listing("https://www.cardmarket.com/en/Pokemon/Products/Singles/Set/Card")
    assert not cardmarket_expansion_listing(URL + "&redirect=https://evil.example")
    assert not cardmarket_expansion_listing(URL + "&page=3")


def test_listing_parser_keeps_only_singles_from_the_requested_expansion():
    html = '''<html><h1>MEGA Starter Set Mega Diancie ex</h1>
      <a href="/en/Pokemon/Expansions/MEGA-Starter-Set-Mega-Diancie-ex?page=3">3</a>
      <a data-product-id="98765" href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Mega-Diancie-ex-mBD005">Mega Diancie ex mBD005</a>
      <a href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Gengar-ex/Mega-Gengar-ex-mBG003">Mega Gengar ex mBG003</a>
      <a href="https://evil.example/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Fake">fake</a>
    </html>'''
    result = parse_expansion_listing(URL, html)
    assert result["outcome"] == "offers"
    assert result["products"] == [{
        "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Mega-Diancie-ex-mBD005",
        "name": "Mega Diancie ex mBD005",
        "product_id": "98765",
    }]
    assert result["pagination_urls"] == ["https://www.cardmarket.com/en/Pokemon/Expansions/MEGA-Starter-Set-Mega-Diancie-ex?page=3"]


def test_challenge_and_empty_page_are_distinct_from_a_valid_product_list():
    assert parse_expansion_listing(URL, '<div id="challenge-form">Just a moment</div>')["outcome"] == "challenge_unsolved"
    assert parse_expansion_listing(URL, '<div data-test-empty="true">No products found</div>')["outcome"] == "empty"
    assert parse_expansion_listing(URL, '<html><h1>Unrelated page</h1></html>')["outcome"] == "wrong_product"


def test_listing_parser_accepts_case_variants_in_cardmarket_product_paths():
    html = '<a href="/en/pokemon/products/singles/mega-starter-set-mega-diancie-ex/card-1">Card 1</a>'
    result = parse_expansion_listing(URL, html)
    assert result["outcome"] == "offers"
    assert result["products"][0]["name"] == "Card 1"


def test_listing_parser_keeps_image_only_singles_tiles():
    html = '<a href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Diancie-ex-mBD004"><img alt=""></a>'
    result = parse_expansion_listing(URL, html)
    assert result["outcome"] == "offers"
    assert result["products"] == [{
        "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Diancie-ex-mBD004",
        "name": "Diancie ex mBD004",
    }]


def test_listing_pauses_immediately_without_clicking_or_stopping_challenge():
    class Session:
        proxy = None
        cleared = False
        calls = 0
        opened = 0

        def open(self, _url): self.opened += 1
        def block_extra_resources(self): pass
        def probe(self): return "challenge" if self.calls == 0 else "offers"
        def solve_captcha(self): self.calls += 1
        def html(self): return "<html>products</html>"
        def stop(self): raise AssertionError("must leave challenge loading")
        def alive(self): return True
        def finish(self): self.finished = True
        def quit(self): raise AssertionError("listing challenge session should be preserved")

    session = Session()
    result = run_attempt(session, URL, parse_html=lambda _url, _html: {
        "outcome": "offers", "products": [{"url": "https://www.cardmarket.com/p"}],
    }, catalogue_listing=True)
    assert result["outcome"] == "challenge_unsolved"
    assert result["owner_verification_required"] is True
    assert session.calls == 0
    assert session.opened == 1
    assert session.finished is True


def test_local_listing_pause_requires_same_session_confirmation(monkeypatch):
    spec = importlib.util.spec_from_file_location("scraper_listing_route_test", Path(__file__).with_name("main.py"))
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    monkeypatch.setenv("SCRAPER_IN_PROCESS", "1")
    monkeypatch.setattr(service, "API_KEY", "local-test-key")
    monkeypatch.setattr(service, "_supervisor", None)
    monkeypatch.setattr(service, "wait_for_page_gap", lambda **kwargs: None)
    monkeypatch.setattr(service, "reap_stale_browsers", lambda *args, **kwargs: None)
    session = SimpleNamespace(reused=False, net_summary=None, last_title="", last_url="", last_screenshot=b"")
    session.current_url = lambda: URL
    session.probe = lambda: "challenge"
    session.html = lambda: '<a href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Card">Card</a>'
    monkeypatch.setattr(service, "open_session", lambda _session_id: session)
    monkeypatch.setattr(service, "run_attempt", lambda *args, **kwargs: {
        "outcome": "challenge_unsolved", "products": [], "rows": [],
        "owner_verification_required": True,
    })
    headers = {"Authorization": "Bearer local-test-key"}
    payload = {"url": URL, "session_id": "pilot-session"}
    with TestClient(service.app) as client:
        result = client.post("/catalogue-listing", headers=headers, json=payload)
        assert result.status_code == 200
        assert result.json()["owner_verification_required"] is True
        assert client.get("/status").json()["state"] == "waiting_for_owner"
        assert client.post("/catalogue-listing", headers=headers, json=payload).status_code == 503
        session.probe = lambda: "offers"
        confirmed = client.post("/catalogue-listing/confirm", headers=headers, json=payload)
        assert confirmed.status_code == 200
        assert confirmed.json()["outcome"] == "offers"
        assert client.get("/status").json()["state"] == "idle"


def test_singles_routes_pagination_and_canonical_deduplication():
    url = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Set?site=1'
    assert cardmarket_expansion_listing(url)
    html = '''<a href="/en/Pokemon/Products/Singles/Set/Card?language=7#x"><img></a>
      <a href="/en/Pokemon/Products/Singles/Set/Card">Card</a>
      <a href="?site=2">Next</a>
      <a href="/en/Pokemon/Products/Singles/Other?site=2">Other</a>'''
    result = parse_expansion_listing(url, html)
    assert len(result['products']) == 1
    assert result['products'][0]['url'].endswith('/Set/Card')
    assert result['pagination_urls'] == ['https://www.cardmarket.com/en/Pokemon/Products/Singles/Set?site=2']


def test_numeric_expansion_pagination_keeps_set_and_filters():
    url = 'https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion=4239&site=1'
    assert cardmarket_expansion_listing(url)
    assert not cardmarket_expansion_listing('https://www.cardmarket.com/en/Pokemon/Products/Singles?site=1')
    html = '''<a href="/en/Pokemon/Products/Singles/Eevee-Heroes/Card">Card</a>
      <a href="?idExpansion=4239&amp;site=2">Next</a>
      <a href="?idExpansion=1234&amp;site=2">Other set</a>
      <a href="?idExpansion=4239&amp;language=1&amp;site=2">Other filter</a>'''
    result = parse_expansion_listing(url, html)
    assert result['pagination_urls'] == ['https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion=4239&site=2']


def test_expansion_landing_returns_observed_singles_listing_link():
    result = parse_expansion_listing(URL, '''<a href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex">Singles</a>''')
    assert result['outcome'] == 'listing_links'
    assert result['listing_urls'] == ['https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex']


def test_attempt_preserves_listing_pagination():
    class Session:
        def open(self, url): pass
        def block_extra_resources(self): pass
        def probe(self): return 'offers'
        def html(self): return '''<a href="/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Card">Card</a><a href="?page=3">Next</a>'''
        def stop(self): pass
        def quit(self): pass
    result = run_attempt(Session(), URL, parse_html=parse_expansion_listing, catalogue_listing=True)
    assert result['outcome'] == 'offers'
    assert len(result['pagination_urls']) == 1


def test_price_text_and_current_page_modal_links_are_not_collected():
    url = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Set?site=1'
    html = '''<a href="/en/Pokemon/Products/Singles/Set/Card">Card (001)From 0,02 €</a>
      <a href="?site=1#modal">view</a><a href="?site=2#page">next</a>'''
    result = parse_expansion_listing(url, html)
    assert result['products'][0]['name'] == 'Card (001)'
    assert result['pagination_urls'] == ['https://www.cardmarket.com/en/Pokemon/Products/Singles/Set?site=2']


def test_manual_challenge_stays_available_after_previously_cleared_page():
    from browser import ChromeSession, CHALLENGE_BLOCKED
    session = ChromeSession(None, net_log=False)
    session.cleared = True
    session.catalogue_listing = True
    session._sb = SimpleNamespace(cdp=SimpleNamespace(get=lambda url: None))
    session.block_extra_resources = lambda: None
    session.open(URL)
    assert session._block_urls == CHALLENGE_BLOCKED


def test_master_index_returns_named_expansions_and_excludes_products_and_foreign_hosts():
    url = 'https://www.cardmarket.com/en/Pokemon/Expansions'
    assert cardmarket_expansion_listing(url)
    assert not cardmarket_expansion_listing(url + '?redirect=elsewhere')
    result = parse_expansion_listing(url, '''<a href="/en/Pokemon/Expansions/Real-Set">Real Set</a>
        <a href="https://evil.example/en/Pokemon/Expansions/Fake">Fake</a>
        <a href="/en/Pokemon/Products/Box-Sets/Real-Set">Sealed</a>
        <a href="/en/Pokemon/Expansions/Real-Set">Real Set</a>''')
    assert result['outcome'] == 'listing_links'
    assert result['expansions'] == [{'url': url + '/Real-Set', 'name': 'Real Set'}]


def test_list_view_product_id_comes_from_the_row():
    from listings import parse_expansion_listing
    html = ('<table><tr id="productRow907869"><td><a href="/en/Pokemon/Products/Singles/30th-Celebration-JP/'
            'Alolan-Exeggutor-V2-m6a104">Alolan Exeggutor (m6a 104)</a></td></tr>'
            '<tr id="productRow907870"><td><a href="/en/Pokemon/Products/Singles/30th-Celebration-JP/'
            'Moltres-V2-m6a105">Moltres</a></td></tr></table>')
    out = parse_expansion_listing('https://www.cardmarket.com/en/Pokemon/Products/Singles/30th-Celebration-JP?mode=list', html)
    assert [p.get("product_id") for p in out["products"]] == ["907869", "907870"]
