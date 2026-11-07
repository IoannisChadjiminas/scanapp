import json

from audit_remaining_routes import audit


def test_cached_locale_aliases_do_not_require_refetch_or_certify_membership(tmp_path):
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return str(path)
    url = 'https://www.cardmarket.com/en/Pokemon/Expansions/Shared'
    listing = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Shared'
    product = listing + '/Card'
    page = write('page.json', {'result': {'outcome': 'listing_links', 'listing_urls': [listing]}})
    cards = write('cards.json', {'result': {
        'outcome': 'offers', 'products': [{'url': product, 'name': 'Card'}],
        'pagination_urls': [listing.replace('/en/', '/fr/')],
    }})
    write('set-registry.json', [{'group_id': 'a', 'name': 'Subdeck', 'code': 'A', 'listed_cards': 2}])
    write('shared-listing-review-queue.json', [{'group_ids': ['a'], 'name': 'Shared', 'url': url}])
    write('listing-progress.json', {'groups': {'other': {'pages': {url: page, listing: cards}}}})
    (tmp_path / 'review').mkdir(exist_ok=True)
    (tmp_path / 'review/remaining-group-routing.csv').write_text(
        'group_id,state,next_action\na,shared_listing_needs_partition,Compare checklist\n')
    result = audit(tmp_path)
    assert result['fully_cached_sources'] == 1
    assert result['sources'][0]['cached_product_count'] == 1
    assert result['groups'][0]['all_source_pages_cached'] is True
    assert result['groups'][0]['membership_verified'] is False
    assert result['groups'][0]['reference_card_count'] == 2

    write('cards.json', {'result': {'outcome': 'offers', 'products': [],
                                  'pagination_urls': [listing + '?site=2']}})
    result = audit(tmp_path)
    assert result['fully_cached_sources'] == 0
    assert result['sources'][0]['missing_page_urls'] == [listing + '?site=2']
