#!/usr/bin/env python3
"""Read-only review of unmatched listing photos; never writes catalogue links.

Input: JSON containing cards and cardmarket_expansion_products from a read-only
SQLite export. Output: JSON decisions and a searchable HTML comparison page.
Run from the repository root; see docs/cardmarket-photo-audit.md.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app.cardmarket import cardmarket_slug, listing_product_title, listing_set_collector


def number_key(value: str) -> str:
    # Retain alphabetic prefixes/suffixes: 95a and 95b are different prints.
    return re.sub(r'\d+', lambda m: str(int(m[0])), value.strip().casefold())


def name_key(value: str) -> str:
    value = value.replace('♀', ' F ').replace('♂', ' M ')
    value = unicodedata.normalize('NFKD', value).casefold()
    return re.sub(r'[^a-z0-9]', '', value)


def image_product_id(url: str) -> int | None:
    parts = urlparse(url or '')
    if parts.hostname != 'product-images.s3.cardmarket.com':
        return None
    match = re.search(r'/(\d+)/\1\.jpg$', parts.path)
    return int(match[1]) if match else None


def official(card: dict) -> bool:
    return card['id'].startswith(card['language'] + ':')


def old_candidates(path: Path | None) -> dict:
    result = {}
    if path:
        for block in path.read_text().split('\n\n'):
            urls = re.findall(r'^https://www.cardmarket[^\s]+', block, re.M)
            ids = re.findall(r'^official: ([^ |]+) \|', block, re.M)
            if urls and ids:
                result[urls[0]] = ids
    return result


def audit(snapshot: dict, old: dict | None = None) -> list[dict]:
    cards = [c for c in snapshot['cards'] if official(c)]
    products = snapshot['cardmarket_expansion_products']
    sets = defaultdict(set)
    by_number = defaultdict(list)
    by_code = defaultdict(set)
    for c in cards:
        scope = (c['language'], c['set_id'])
        sets[cardmarket_slug(c['set_name']).lower()].add(scope)
        by_number[(*scope, number_key(c['collector_number']))].append(c)
        by_code[c['set_id'].casefold()].add(scope)
    # This is an explicit deck alias, NOT a global rule for collector suffixes.
    trainer_decks = {'z': ('en', 'tk-bw-z'), 'e': ('en', 'tk-bw-e')}
    siblings = defaultdict(list)
    for p in products:
        parsed = listing_set_collector(p['name'])
        if parsed:
            siblings[(p['expansion'], parsed[0].casefold(), number_key(parsed[1]),
                      name_key(listing_product_title(p['name'])))].append(p['url'])
    output = []
    for p in products:
        if (p['matched'] and p['card_id']) or not p['listing_image_url']:
            continue
        r = {k: p[k] for k in ('url', 'expansion', 'name', 'listing_image_url')}
        r.update(status='unresolved', reason='', candidates=[], old_candidates=(old or {}).get(p['url'], []))
        parsed = listing_set_collector(p['name'])
        scopes = sets[p['expansion'].lower()]
        num = number_key(parsed[1]) if parsed else ''
        title = name_key(listing_product_title(p['name']))
        trainer = p['expansion'] == 'BW-Trainer-Kit' and parsed and parsed[0] == 'TK5'
        if trainer and re.fullmatch(r'\d+[ez]', num):
            scopes = {trainer_decks[num[-1]]}
            num = num[:-1]
        if re.search(r'(?:Live|Online) Code Card', p['name'], re.I):
            r.update(status='non_catalogue_item', reason='Online redemption code, not a collectible card print.')
        elif not scopes:
            r.update(status='no_supported_set', reason='No exact expansion/deck in this catalogue. Do not substitute another language or a set with the same short code.')
            r['code_collisions'] = sorted(by_code[parsed[0].casefold()]) if parsed else []
        elif not parsed:
            r.update(status='missing_collector', reason='Listing has no usable collector number; name alone cannot establish a print.')
        else:
            candidates = [c for scope in scopes for c in by_number[(*scope, num)]]
            r['candidates'] = candidates
            if not candidates:
                r.update(status='missing_print', reason='Expansion is present, but this full collector number is not.')
            elif len(candidates) != 1:
                r.update(status='ambiguous_catalogue', reason='Multiple catalogue rows share the exact set and collector number.')
            else:
                c = candidates[0]
                sib = siblings[(p['expansion'], parsed[0].casefold(), number_key(parsed[1]), title)]
                # An oversized photo belongs to a separate product even with the same art.
                if p['url'].endswith('-OS'):
                    r.update(status='separate_variant', reason='Oversized product; do not attach to the standard-size catalogue print.')
                elif c['language'] != 'en':
                    r.update(status='needs_language_check', reason='Exact set/number candidate; translated title and physical print still need checking.')
                elif title != name_key(c['name']):
                    r.update(status='metadata_conflict', reason='Exact set/number points to a different card name. Hold for inspection.')
                elif len(sib) != 1:
                    r.update(status='separate_variant', reason='Multiple products share this name, expansion, and full collector number.')
                elif c.get('cardmarket_url') and c['cardmarket_url'] != p['url']:
                    r.update(status='existing_link_conflict', reason='Catalogue card already owns another product URL; do not overwrite.')
                else:
                    pid = image_product_id(p['listing_image_url'])
                    evidence = ['Exact expansion/deck, full collector number, and name']
                    if trainer:
                        evidence.append('E/Z deck suffix selects Excadrill/Zoroark')
                    if pid and pid == c.get('cardmarket_id'):
                        evidence.append('Listing photo product ID agrees with TCGdex product ID (supporting evidence only)')
                    r.update(status='proposed_match', reason='; '.join(evidence) + '.', proposed_card_id=c['id'])
                    r['official_image_available'] = bool(c.get('remote_image_url'))
        output.append(r)
    # Never propose two URLs for one card even if the labels differ.
    owners = Counter(r.get('proposed_card_id') for r in output if r['status'] == 'proposed_match')
    for r in output:
        if r['status'] == 'proposed_match' and owners[r['proposed_card_id']] != 1:
            r.update(status='ambiguous_catalogue', reason='Multiple proposed URLs target the same catalogue card.')
            del r['proposed_card_id']
    return sorted(output, key=lambda r: (r['status'] != 'proposed_match', r['status'], r['expansion'], r['name']))


def render(rows: list[dict], output: Path, summary: dict, embedded: dict | None = None) -> None:
    def e(s): return html.escape(str(s or ''), quote=True)
    articles = []
    for r in rows:
        source = (embedded or {}).get(r['url'], r['listing_image_url'])
        pictures = [f'<figure><a href="{e(r["url"])}"><img loading="lazy" src="{e(source)}" alt="Cardmarket listing photo"></a><figcaption>Cardmarket listing</figcaption></figure>']
        for c in r['candidates']:
            src = c.get('remote_image_url')
            pic = f'<img loading="lazy" src="{e(src)}" alt="Catalogue art">' if src else '<div class="missing">No official image in catalogue</div>'
            pictures.append(f'<figure>{pic}<figcaption>{e(c["id"])} · {e(c["name"])}<br>{e(c["set_name"])} · {e(c["collector_number"])} · {e(c["language"])}</figcaption></figure>')
        previous = ('<p class="old">Previous suggestions (not approved): ' + e(', '.join(r['old_candidates'])) + '</p>') if r['old_candidates'] else ''
        if r.get('visual_review'):
            previous += '<p><b>Visual review:</b> ' + e(r['visual_review']) + '</p>'
        articles.append(f'<article data-status="{e(r["status"])}"><h2>{e(r["name"])}</h2><p>{e(r["expansion"])} · <strong>{e(r["status"])}</strong></p><p>{e(r["reason"])}</p>{previous}<div class="photos">{"".join(pictures)}</div><p><a href="{e(r["url"])}">Open product page</a></p></article>')
    opts = ''.join(f'<option value="{e(k)}">{e(k)} ({v})</option>' for k, v in sorted(summary['statuses'].items()))
    output.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cardmarket photo matching review</title><style>
body{font:16px system-ui;background:#f3f5f8;color:#172236;max-width:1200px;margin:30px auto;padding:0 20px}h1{font-size:32px}h2{font-size:19px}header{background:white;padding:24px;border-radius:12px}nav{position:sticky;top:0;background:#edf2f7;padding:16px;display:flex;flex-wrap:wrap;gap:12px;z-index:1}input,select{font:inherit;padding:10px;min-width:0}input{flex:1 1 200px}select{flex:1 1 200px}article{background:white;padding:24px;margin:18px 0;border:1px solid #dce2e8;border-radius:12px}article[data-status=proposed_match]{border-left:5px solid #168064}.photos{display:flex;gap:24px;flex-wrap:wrap}figure{margin:0;max-width:280px}img,.missing{width:240px;height:336px;object-fit:contain;background:#edf0f4}.missing{display:grid;place-items:center;padding:12px;box-sizing:border-box;text-align:center;color:#687487}figcaption{font-size:13px;margin-top:8px}.old{color:#894b23}a{color:#175e9c}article[hidden]{display:none}
</style><header><h1>Cardmarket photo matching review</h1><p>''' + e(summary['created_at'][:10]) + ' · ' + str(len(rows)) + ''' unmatched products with photos.</p><p>Proposals require the same expansion/deck, full collector number, name, and an unambiguous product. Matching a short set code or similar artwork is insufficient.</p><p><b>Read-only review: this audit has not changed database links.</b> “Proposed match” means a metadata-supported identity. Individual visual checks are recorded below; a missing official image does not mean a missing catalogue card.</p><p>''' + str(summary.get('visually_reviewed_proposals', 0)) + ''' proposals visually compared with official art. Other proposals are metadata only. Unresolved rows need further catalogue/alias or variant research. Cached listing photos are embedded where available; other images need network access.</p></header><nav><input id="q" aria-label="Search" placeholder="Search name, expansion, or card ID"><select id="status" aria-label="Status"><option value="proposed_match">Proposed matches</option><option value="">All rows</option>''' + opts + '''</select><span id="count"></span></nav><main>''' + ''.join(articles) + '''</main><script>
const cards=[...document.querySelectorAll('article')],q=document.querySelector('#q'),s=document.querySelector('#status');function filter(){let n=0;const t=q.value.toLowerCase();cards.forEach(c=>{c.hidden=!!((s.value&&c.dataset.status!==s.value)||!c.textContent.toLowerCase().includes(t));if(!c.hidden)n++});document.querySelector('#count').textContent=n+' shown'}q.oninput=filter;s.onchange=filter;filter();</script></html>''')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--old-review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--embedded-photos', type=Path, help='Optional URL-to-data-URL cache from the original review HTML')
    parser.add_argument('--visual-review', type=Path, help='Optional URL-to-review evidence JSON; cannot create matches')
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    old = old_candidates(args.old_review)
    rows = audit(snapshot, old)
    reviewed = json.loads(args.visual_review.read_text()) if args.visual_review else {}
    for r in rows:
        evidence = reviewed.get(r['url'])
        if evidence and r.get('proposed_card_id') == evidence.get('card_id'):
            r['visual_review'] = evidence['note']
        elif evidence and evidence.get('hold'):
            r['visual_review'] = evidence['note']
    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'photo_rows': len(rows),
               'old_review_candidates': len(old), 'statuses': dict(Counter(r['status'] for r in rows)),
               'proposed_by_expansion': dict(Counter(r['expansion'] for r in rows if r['status'] == 'proposed_match')),
               'proposed_with_official_image': sum(r.get('official_image_available', False) for r in rows if r['status'] == 'proposed_match'),
               'visually_reviewed_proposals': sum(bool(r.get('visual_review')) for r in rows if r['status'] == 'proposed_match')}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'review.json').write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    proposals = [{k: r[k] for k in ('url', 'proposed_card_id', 'reason', 'official_image_available')} for r in rows if r['status'] == 'proposed_match']
    for p in proposals:
        p['visual_review'] = reviewed.get(p['url'], {}).get('note') if reviewed.get(p['url'], {}).get('card_id') == p['proposed_card_id'] else None
    (args.output / 'proposed-matches.json').write_text(json.dumps(proposals, ensure_ascii=False, indent=2))
    embedded = json.loads(args.embedded_photos.read_text()) if args.embedded_photos else {}
    render(rows, args.output / 'review.html', summary, embedded)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
