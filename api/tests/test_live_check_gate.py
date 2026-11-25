"""Pro live checks: eBay, CardTrader and live Cardmarket parses spend a permit."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import get_settings
from app.routes import cardmarket as cardmarket_routes
from app.routes import cardtrader as cardtrader_routes
from app.routes import ebay as ebay_routes
from app.subscription_client import PermitRefused, SubscriptionClient, SubscriptionUnavailable

PERMIT = 'p' * 43
HEADERS = {'x-pokesingle-live-permit': PERMIT}
URL = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu'
ANSWER = {'enabled': True, 'average': 20.0, 'count': 3}


class Product:
    """The product API's claim endpoint: 'ok', 'refused' or 'down'."""

    def __init__(self, answer='ok'):
        self.answer = answer
        self.claims: list[tuple[str, str]] = []

    def claim_live(self, permit, kind):
        self.claims.append((permit, kind))
        if self.answer == 'refused':
            raise PermitRefused()
        if self.answer == 'down':
            raise SubscriptionUnavailable('product API unavailable')


class Ebay:
    def __init__(self):
        self.live = 0

    def kept(self, _card):
        return dict(ANSWER)

    def graded(self, _card):
        self.live += 1
        return dict(ANSWER)


class CardTrader:
    def __init__(self):
        self.live = 0

    def prices(self, *_args, **_kwargs):
        self.live += 1
        return {'enabled': True, 'matched': True, 'count': 0, 'prices': []}


class Catalog:
    def execute(self, *_):
        return self

    def fetchone(self):
        return (1,)


@pytest.fixture
def gate(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'product_api_live_gate_ready', True)
    product = Product()
    monkeypatch.setattr('app.live_permit.SubscriptionClient', lambda _s: product)
    return product


@pytest.fixture
def app(monkeypatch):
    stored: list[str] = []
    monkeypatch.setattr(ebay_routes, '_graded_card', lambda *_: object())
    monkeypatch.setattr(ebay_routes, '_in_euros', lambda _r, answer, _c: answer)
    monkeypatch.setattr(cardtrader_routes, '_product', lambda *_: ({'language': 'en'}, 5))
    monkeypatch.setattr(cardtrader_routes, '_main', lambda *_: False)
    monkeypatch.setattr(cardmarket_routes, 'get_or_create_session',
                        lambda *_: stored.append('session') or 'session-1')
    monkeypatch.setattr(cardmarket_routes, 'parse_cardmarket_html',
                        lambda url, _html: {'url': url, 'rows': [{'price': '2,00 €'}]})
    monkeypatch.setattr(cardmarket_routes, 'remember_phone_offers', lambda *_a, **_k: stored.append('offers'))
    monkeypatch.setattr(cardmarket_routes, 'remember_listing_product', lambda *_: stored.append('listing'))
    monkeypatch.setattr(cardmarket_routes, 'record_phone_challenge', lambda *_a, **_k: stored.append('challenge'))
    app = FastAPI()
    for module in (ebay_routes, cardtrader_routes, cardmarket_routes):
        app.include_router(module.router, prefix='/api/v1')
    app.state.settings = get_settings()
    app.state.dbs = type('Dbs', (), {'catalog': Catalog()})()
    app.state.ebay = Ebay()
    app.state.cardtrader = CardTrader()
    app.state.stored = stored
    return app


def _ebay(client, headers=None, **params):
    return client.get('/api/v1/ebay/graded', headers=headers or {},
                      params={'card_id': 'en:base1-58', 'grader': 'PSA', 'grade': '10', **params})


def _cardtrader(client, headers=None):
    return client.get('/api/v1/cardtrader/prices', headers=headers or {}, params={'card_id': 'base1-58'})


def _parse(client, headers=None, **body):
    return client.post('/api/v1/cardmarket/parse', headers=headers or {},
                       json={'url': URL, 'html': '<html></html>', **body})


def test_flag_off_leaves_every_route_unchanged(app, monkeypatch):
    monkeypatch.setattr(get_settings(), 'product_api_live_gate_ready', False)
    product = Product()
    monkeypatch.setattr('app.live_permit.SubscriptionClient', lambda _s: product)
    client = TestClient(app)
    assert _ebay(client).json()['average'] == 20.0
    assert _cardtrader(client).json()['matched'] is True
    assert _parse(client, live=True).status_code == 200
    assert app.state.ebay.live == 1 and app.state.cardtrader.live == 1
    assert product.claims == []


@pytest.mark.parametrize('header', [None, {'x-pokesingle-live-permit': 'short'},
                                    {'x-pokesingle-live-permit': 'x' * 101}])
def test_a_missing_or_malformed_permit_is_refused_without_a_claim(app, gate, header):
    client = TestClient(app)
    for response in (_ebay(client, header), _cardtrader(client, header), _parse(client, header, live=True)):
        assert response.status_code == 403
        assert response.json() == {'detail': 'subscription_required'}
    assert gate.claims == []
    assert app.state.ebay.live == 0 and app.state.cardtrader.live == 0
    assert app.state.stored == []


def test_a_claimed_permit_reads_live_once_per_kind(app, gate):
    client = TestClient(app)
    assert _ebay(client, HEADERS).json()['average'] == 20.0
    assert _cardtrader(client, HEADERS).json()['matched'] is True
    assert _parse(client, HEADERS, live=True).status_code == 200
    assert gate.claims == [(PERMIT, 'ebay'), (PERMIT, 'cardtrader'), (PERMIT, 'cardmarket')]
    assert app.state.ebay.live == 1 and app.state.cardtrader.live == 1
    assert app.state.stored == ['session', 'offers', 'listing']


def test_a_refused_permit_is_403_and_stores_nothing(app, gate):
    gate.answer = 'refused'
    client = TestClient(app)
    for response in (_ebay(client, HEADERS), _cardtrader(client, HEADERS), _parse(client, HEADERS, live=True)):
        assert response.status_code == 403
        assert response.json() == {'detail': 'subscription_required'}
    assert app.state.ebay.live == 0 and app.state.cardtrader.live == 0
    assert app.state.stored == []


def test_an_unreachable_product_api_fails_closed(app, gate):
    gate.answer = 'down'
    client = TestClient(app)
    for response in (_ebay(client, HEADERS), _cardtrader(client, HEADERS), _parse(client, HEADERS, live=True)):
        assert response.status_code == 503
        assert PERMIT not in response.text
    assert app.state.ebay.live == 0 and app.state.cardtrader.live == 0
    assert app.state.stored == []


def test_cached_ebay_and_non_live_parses_need_no_permit(app, gate):
    client = TestClient(app)
    assert _ebay(client, cached_only='true').json()['average'] == 20.0
    assert _parse(client).status_code == 200
    assert _parse(client, live=False).status_code == 200
    assert gate.claims == [] and app.state.ebay.live == 0
    assert app.state.stored == ['session', 'offers', 'listing'] * 2


def test_a_live_parse_of_a_foreign_url_is_400_before_any_claim(app, gate):
    response = TestClient(app).post('/api/v1/cardmarket/parse', headers=HEADERS,
                                    json={'url': 'https://example.com/page', 'html': 'x', 'live': True})
    assert response.status_code == 400
    assert gate.claims == [] and app.state.stored == []


def _client(handler):
    settings = get_settings().model_copy(update={
        'product_api_url': 'https://product.example',
        'scanapp_service_token': SecretStr('t' * 40),
    })
    return SubscriptionClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_claim_live_sends_permit_and_kind_and_reads_the_answer():
    seen = []

    def handler(request):
        seen.append((request.url.path, request.headers['authorization'], request.content))
        return httpx.Response(200, json={'state': 'claimed'})

    _client(handler).claim_live(PERMIT, 'ebay')
    path, auth, content = seen[0]
    assert path == '/internal/live-checks/permits/claim' and auth == 'Bearer ' + 't' * 40
    assert b'"kind":"ebay"' in content and PERMIT.encode() in content


@pytest.mark.parametrize('code', ['permit_invalid', 'permit_expired'])
def test_claim_live_refusals_are_not_outages(code):
    with pytest.raises(PermitRefused):
        _client(lambda _r: httpx.Response(403, json={'code': code})).claim_live(PERMIT, 'cardtrader')


@pytest.mark.parametrize('response', [
    httpx.Response(403, json={'code': 'something_else'}),
    httpx.Response(403, text='not json'),
    httpx.Response(500, json={}),
    httpx.Response(200, json={'state': 'used'}),
    httpx.Response(200, json=['claimed']),
])
def test_claim_live_fails_closed_on_anything_else(response):
    with pytest.raises(SubscriptionUnavailable):
        _client(lambda _r: response).claim_live(PERMIT, 'cardmarket')


def test_claim_live_fails_closed_when_unreachable():
    def handler(_request):
        raise httpx.ConnectError('down')

    with pytest.raises(SubscriptionUnavailable):
        _client(handler).claim_live(PERMIT, 'ebay')
