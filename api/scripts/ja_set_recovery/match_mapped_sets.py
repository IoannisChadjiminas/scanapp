"""Match unlinked rows of sets with no Cardmarket link yet to products of hand-mapped expansions.

python3 -I match_mapped_sets.py CATALOG_SQLITE SET_MAP_JSON PRODUCTS_JSON OUT_JSON [NUMBERED_SETS]
SET_MAP_JSON: {our set_id: [Cardmarket expansion slug, ...]}, chosen by hand from Cardmarket's expansion list.
PRODUCTS_JSON: {expansion slug: [[path, 'Name (CODE NNN)'], ...]}, the complete list pages of those expansions.
A row gets a product when exactly one product of its mapped expansions has the same English name (Lv. ignored),
with the same printed number for a set in NUMBERED_SETS (comma list), and no other row of the batch claims that product.
"""
import collections, json, re, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location('mcl', Path(__file__).resolve().parent / 'match_crawl_links.py')
norm_src = Path(spec.origin).read_text().split('\ndb = ')[0]
ns = {}; exec(norm_src, ns); norm = ns['norm']

catalog, set_map, products, out_path = sys.argv[1:5]
# Sets whose collector numbers are the printed ones (the deck's position), so a product's number must agree.
# The others number their rows themselves (u01.. or 001.. in list order) and match by name only.
NUMBERED = set(sys.argv[5].split(',')) if len(sys.argv) > 5 else set()
smap = json.load(open(set_map)); prods = json.load(open(products))
db = sqlite3.connect(f'file:{catalog}?mode=ro', uri=True)
used = {r[0] for r in db.execute("select cardmarket_url from cards where coalesce(cardmarket_url,'')<>''")}
parsed = {}
for e, items in prods.items():
    for path, name in items:
        url = 'https://www.cardmarket.com' + path
        if url in used: continue
        m = re.match(r'^(.*?)\s*\(([^()]*)\)$', name)
        title, code = (m.group(1), m.group(2)) if m else (name, '')
        d = re.search(r'(\d+)', code)
        parsed.setdefault(e, []).append({'url': url, 'title': title, 'code': code, 'num': int(d.group(1)) if d else None})
out, why = [], collections.Counter()
for sid, exps in smap.items():
    free = [p for e in exps for p in parsed.get(e, [])]
    own_numbers = sid in NUMBERED
    for cid, num, pr, title in db.execute("select id, collector_number, printed_collector_number, view_title from cards "
                                          "where set_id=? and coalesce(cardmarket_url,'')=''", (sid,)):
        cand = [p for p in free if norm(p['title']) == norm(title)]
        n = re.match(r'^0*(\d+)$', (pr or num or '').split('/')[0])
        if n and own_numbers:
            cand = [p for p in cand if p['num'] is None or p['num'] == int(n.group(1))]
        if len(cand) == 1:
            out.append({'id': cid, 'set': sid, 'expansion': exps, 'url': cand[0]['url'],
                        'product': f"{cand[0]['title']} ({cand[0]['code']})", 'title': title})
        why['matched' if len(cand) == 1 else ('ambiguous' if cand else 'no_match')] += 1
count = collections.Counter(o['url'] for o in out)
why['dropped_url_twice'] = sum(1 for o in out if count[o['url']] > 1)
out = [o for o in out if count[o['url']] == 1]
json.dump(out, open(out_path, 'w'), indent=1, ensure_ascii=False)
print(dict(why), len(out)); print(collections.Counter(o['set'] for o in out))
