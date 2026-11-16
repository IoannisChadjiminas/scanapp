"""Third pass for Japanese Cardmarket links: same number, name differing only in spelling.

python3 -I match_spelling_links.py CATALOG_SQLITE EXTRA_CRAWL_JSON EXCLUDE_IDS_JSON OUT_JSON
For a row whose set maps to one expansion (as in match_crawl_links.py), the products of that expansion with the
row's printed number are taken; exactly one of them must have the same canonical name:
lower-case ASCII, `Lv.` and what follows dropped, brackets, spaces, hyphens and apostrophes dropped
("M Rayquaza-EX" = "MRayquaza EX", "NidoranF" = "Nidoran [F]"), a leading "Basic " before "... Energy"
dropped, a trailing "(...)" on our title dropped, and a product's "[M]" movie mark ignored.
Rows already matched by the other passes (EXCLUDE_IDS_JSON, a list of match files) are skipped, and their
products count as taken.
"""
import collections, json, re, sqlite3, sys, unicodedata

def canon(s, movie=False):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\blv\.?\s*x?\s*\d*.*$', '', s)
    if movie:
        s = s.replace('[m]', '')
    s = re.sub(r'^basic (\w+ energy)$', r'\1', s.strip())
    return re.sub(r"[\s\-'\[\]\.&,:]", '', s)

catalog, extra, exclude, out_path = sys.argv[1:5]
prior = [o for f in json.load(open(exclude)) for o in json.load(open(f))]
done = {o['id'] for o in prior}
db = sqlite3.connect(f'file:{catalog}?mode=ro', uri=True)
cards = db.execute("select id,set_id,collector_number,printed_collector_number,view_title,cardmarket_url from cards where language='ja'").fetchall()
exp = collections.defaultdict(collections.Counter)
for cid, sid, n, p, t, u in cards:
    m = re.search(r'/Singles/([^/]+)/', u or '')
    if m: exp[sid][m.group(1)] += 1
used = {c[5] for c in cards if c[5]} | {o['url'] for o in prior}
listed = [tuple(r) for r in db.execute("select url, expansion, name from cardmarket_expansion_products")]
for e, items in json.load(open(extra)).items():
    listed += [('https://www.cardmarket.com' + p, e, name) for p, name in items]
byexp, seen = collections.defaultdict(list), set()
for url, e, name in listed:
    if url in used or url in seen: continue
    seen.add(url)
    base = re.sub(r'From .*$', '', name).strip()
    m = re.match(r'^(.*?)\s*\(([^()]*)\)$', base)
    t, c = (m.group(1), m.group(2)) if m else (base, '')
    d = re.search(r'(\d+)\s*$', c)
    byexp[e].append({'url': url, 'title': t, 'code': c, 'num': int(d.group(1)) if d and ' ' in c else None})
out, why = [], collections.Counter()
for cid, sid, n, p, t, u in cards:
    if u or cid in done or sid not in exp or len(exp[sid]) != 1: continue
    e = next(iter(exp[sid]))
    nn = re.match(r'^0*(\d+)', (p or n or ''))
    if not nn: continue
    same = [x for x in byexp[e] if x['num'] == int(nn.group(1))]
    if not same: continue
    ours = canon(re.sub(r'\s*\([^)]*\)\s*$', '', t))
    hit = [x for x in same if canon(x['title']) == ours or canon(x['title'], movie=True) == ours]
    if len(hit) == 1:
        out.append({'id': cid, 'set': sid, 'expansion': e, 'url': hit[0]['url'], 'title': t,
                    'product': f"{hit[0]['title']} ({hit[0]['code']})"})
    why['matched' if len(hit) == 1 else ('ambiguous' if hit else 'name differs')] += 1
count = collections.Counter(o['url'] for o in out)
out = [o for o in out if count[o['url']] == 1]
json.dump(out, open(out_path, 'w'), indent=1, ensure_ascii=False)
print(dict(why), len(out))
