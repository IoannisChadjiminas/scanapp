import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_listings import collect

BASE = 'https://www.cardmarket.com/en/Pokemon/'
URL = BASE + 'Expansions/Set'
LIST = BASE + 'Products/Singles/Set'
MANIFEST = [{'group_id': 'ja-ref-1', 'url': URL, 'source': 'observed fixture'}]


def prepare(tmp_path):
    (tmp_path / 'set-registry.json').write_text(json.dumps([{'group_id': 'ja-ref-1'}, {'group_id': 'ja-ref-2'}]))


def test_resume_follows_listing_and_pagination_without_refetching(tmp_path):
    prepare(tmp_path)
    calls = []
    def call(method, path, payload):
        calls.append(payload['url'])
        if payload['url'] == URL:
            return {'outcome': 'listing_links', 'listing_urls': [LIST]}
        return {'outcome': 'offers', 'products': [{'url': LIST + '/Card', 'name': 'Card'}],
                'pagination_urls': [LIST + '?site=2']}
    collect(MANIFEST, tmp_path, 'session', 2, call=call)
    result = collect(MANIFEST, tmp_path, 'session', 2, call=call)
    assert calls == [URL, LIST, LIST + '?site=2']
    assert result['groups_listed'] == 1
    assert result['groups_without_observed_url'] == ['ja-ref-2']
    assert len((tmp_path / 'cardmarket-products.jsonl').read_text().splitlines()) == 1
    collect(MANIFEST, tmp_path, 'session', 2, call=call)
    assert len(calls) == 3


def test_manual_challenge_resumes_by_reading_same_page(tmp_path):
    prepare(tmp_path)
    calls = []
    def call(method, path, payload):
        calls.append(path)
        if path.endswith('/confirm'):
            return {'outcome': 'offers', 'products': [{'url': LIST + '/Card'}]}
        return {'outcome': 'challenge_unsolved', 'owner_verification_required': True}
    assert collect(MANIFEST, tmp_path, 'session', 10, call=call)['state'] == 'waiting_for_owner'
    assert collect(MANIFEST, tmp_path, 'session', 10, call=call)['state'] == 'waiting_for_owner'
    assert calls == ['/catalogue-listing']
    assert collect(MANIFEST, tmp_path, 'session', 10, confirm=True, call=call)['groups_listed'] == 1
    assert calls == ['/catalogue-listing', '/catalogue-listing/confirm']


def test_timeout_is_retryable_and_never_completed(tmp_path):
    prepare(tmp_path)
    assert collect(MANIFEST, tmp_path, 'session', 10, call=lambda *a: {'outcome': 'timeout'})['state'] == 'stopped'
    state = json.loads((tmp_path / 'listing-progress.json').read_text())
    assert state['groups']['ja-ref-1']['pending'] == [URL]
    assert not state['groups']['ja-ref-1'].get('complete')


def test_confirmation_prioritizes_paused_group_after_manifest_is_extended(tmp_path):
    prepare(tmp_path)
    first = collect(MANIFEST, tmp_path, 'session', 10,
                    call=lambda *a: {'outcome': 'challenge_unsolved', 'owner_verification_required': True})
    assert first['state'] == 'waiting_for_owner'
    changed_manifest = [{'group_id': 'ja-ref-2', 'url': BASE+'Expansions/Other', 'source': 'observed fixture'}, *MANIFEST]
    calls = []
    def call(method, path, payload):
        calls.append((path, payload['url']))
        return {'outcome': 'offers', 'products': [{'url': LIST+'/Card'}]}
    collect(changed_manifest, tmp_path, 'session', 1, confirm=True, call=call)
    assert calls == [('/catalogue-listing/confirm', URL)]
