import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('offline_evidence',Path(__file__).resolve().parents[1]/'scripts/offline_cardmarket_evidence.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
URL='https://www.cardmarket.com/en/Pokemon/Products/Singles/Example/Squirtle-ABC015'


def test_capture_without_offers_never_approves_identity_or_language():
    raw=f'<link rel="canonical" href="{URL}"><meta property="og:title" content="Squirtle (ABC 015)"><input name="idProduct" value="123">'.encode()
    result=adapter.capture(raw,URL,'2026-10-04T00:00:00+03:00')
    assert result['product_ids']==[123] and result['issues']==[]
    assert result['language'] is None and result['finish'] is None
    assert not result['identity_verified'] and not result['live_access_verified']
    assert result['paid_pages_used_by_adapter']==0


@pytest.mark.parametrize('url', [URL.replace('https:','http:'),URL.replace('www.cardmarket.com','www.cardmarket.com.evil.test'),
    URL.replace('www.cardmarket.com','user:password@www.cardmarket.com'),URL.replace('Singles','Sealed')])
def test_reject_nonpublic_or_nonproduct_urls(url):
    assert adapter.product_url(url) is None


def test_canonical_mismatch_is_not_done():
    result=adapter.capture(b'<link rel="canonical" href="/en/Pokemon/Products/Singles/Other/Wrong">',URL,'2026-10-04T00:00:00Z')
    assert 'canonical_missing_or_mismatch' in result['issues']


def test_challenge_is_not_a_missing_card():
    result=adapter.capture(b'<title>Just a moment</title>',URL,'2026-10-04T00:00:00Z')
    assert result['evidence_state']=='blocked_or_unavailable' and not result['identity_verified']


def test_expansion_links_keep_exact_captured_url_and_exclude_external():
    raw=f'<a href="{URL}?foo=bar">card</a><a href="https://evil.test/card">other</a>'.encode()
    result=adapter.capture(raw,'https://www.cardmarket.com/en/Pokemon/Products/Singles/Example','2026-10-04T00:00:00Z')
    assert result['listing_urls']==[URL]


def test_missing_timezone_is_rejected():
    with pytest.raises(ValueError):adapter.capture(b'',URL,'2026-10-04T00:00:00')
