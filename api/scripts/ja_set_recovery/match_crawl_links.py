"""Match unlinked Japanese rows to crawled Cardmarket products of their set's expansion.

python3 -I match_crawl_links.py CATALOG_SQLITE OUT_JSON [EXTRA_CRAWL_JSON]
EXTRA_CRAWL_JSON: {expansion: [[path or slug, 'Name (CODE NNN)'], ...]} read from Cardmarket's own list pages
(sorted by number both ways, which gets past the list's 300-result cap); added to the stored crawl.
Expansion of a set = the expansion(s) its already-linked rows point to. A product is free when no card links its URL.
Numbered: product '(CODE NNN)' number == our printed/collector number, and English names agree.
Unnumbered: English name (Lv. ignored) unique among free products and our unlinked rows of the set, and only
when no other of our sets links into that expansion (Expansion-Sheet holds three vending series).
"""
import sqlite3, re, sys, json, collections, unicodedata

def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' and ').replace("'", '').replace('-', ' ').replace('.', ' ')
    s = re.sub(r'\b(lv|lv x|lvx)\b.*$', '', s)
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 \[\]]', ' ', s)).strip()

db = sqlite3.connect(sys.argv[1])
cards = db.execute("select id,set_id,collector_number,printed_collector_number,name,view_title,cardmarket_url from cards where language='ja'").fetchall()
used = {r[0] for r in db.execute("select cardmarket_url from cards where coalesce(cardmarket_url,'')<>''")}
exp = collections.defaultdict(collections.Counter)
for cid, sid, num, pr, name, title, u in cards:
    m = re.search(r'/Singles/([^/]+)/', u or '')
    if m: exp[sid][m.group(1)] += 1
prods = collections.defaultdict(list)
listed = [tuple(r) for r in db.execute("select url, expansion, name from cardmarket_expansion_products")]
if len(sys.argv) > 3:
    known = {r[0] for r in listed}
    for e, items in json.load(open(sys.argv[3])).items():
        for slug, name in items:
            path = slug if slug.startswith('/') else f'/en/Pokemon/Products/Singles/{e}/{slug}'
            url = 'https://www.cardmarket.com' + path
            if url not in known:
                listed.append((url, e, name)); known.add(url)
for url, e, name in listed:
    if url in used: continue
    base = re.sub(r'From .*$', '', name).strip()
    m = re.match(r'^(.*?)\s*\(([^()]*)\)$', base)
    title, code = (m.group(1), m.group(2)) if m else (base, '')
    n = re.search(r'(\d+)\s*$', code)
    prods[e].append({'url': url, 'title': title, 'code': code, 'num': int(n.group(1)) if n and ' ' in code else None})

out, why = [], collections.Counter()
by_set = collections.defaultdict(list)
for c in cards:
    if not c[6]: by_set[c[1]].append(c)
for sid, rows in by_set.items():
    if sid not in exp: why['set_not_mapped'] += len(rows); continue
    if len(exp[sid]) > 1: why['set_maps_to_several_expansions'] += len(rows); continue
    e = next(iter(exp[sid]))
    shared = sum(1 for x in exp.values() if e in x) > 1
    free = prods.get(e, [])
    numbered = [p for p in free if p['num'] is not None]
    for cid, _, num, pr, name, title, _ in rows:
        n = re.match(r'^0*(\d+)', (pr or num or ''))
        cand = []
        if n and numbered:
            cand = [p for p in numbered if p['num'] == int(n.group(1))]
            cand = [p for p in cand if norm(p['title']) == norm(title)]
            kind = 'number+name'
        elif not numbered and shared:
            cand, kind = [], 'unique-name'
            why['unnumbered_expansion_shared_by_sets'] += 1
            continue
        elif not numbered:
            cand = [p for p in free if norm(p['title']) == norm(title)]
            same = [r for r in rows if norm(r[5]) == norm(title)]
            if len(same) != 1: cand = []
            kind = 'unique-name'
        if len(cand) == 1:
            out.append({'id': cid, 'set': sid, 'expansion': e, 'url': cand[0]['url'], 'product': cand[0]['title'] + ' (' + cand[0]['code'] + ')', 'title': title, 'kind': kind})
            why['matched_' + kind] += 1
        else:
            why['no_match' if not cand else 'ambiguous'] += 1
urls = collections.Counter(o['url'] for o in out)
dup = {u for u, k in urls.items() if k > 1}
out = [o for o in out if o['url'] not in dup]
why['dropped_url_twice'] = sum(urls[u] for u in dup)
json.dump(out, open(sys.argv[2], 'w'), indent=1, ensure_ascii=False)
print(dict(why), len(out))
print(collections.Counter(o['set'] for o in out).most_common(30))
