"""Decide a rarity for each Japanese card that has none, from Limitless. Offline.

A card gets a rarity only when: its Limitless row (same set code, or a listed alias, and number) is
unique; the names agree (same text, same species via the catalogue's species table, or a Trainer/
Energy whose Limitless type agrees); Limitless gives a rarity; and that label maps to the
catalogue's own label without ambiguity, learnt from cards that already have both (same set first,
then same era, at least 90% one way).
"""
import json, collections, re, unicodedata
L = json.load(open('limitless-rows.json')); cards = json.load(open('ja-cards.json'))
SPECIES = json.load(open('ja_species_names.json'))['species']; ALIAS = json.load(open('set-aliases.json'))
def num(x):
    m = re.match(r'^0*(\d+)$', str(x or '')); return m.group(1) if m else str(x or '')
def key(s):
    s = unicodedata.normalize('NFKC', s or '').lower()
    return re.sub(r"[\s・･\-‐ー()（）\[\]「」『』.,'’:：!！?？&＆♂♀]", '', s)
def species(name):
    w = re.sub(r"[^a-z0-9.\-' ]", ' ', unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower())
    return {ja for en, ja in SPECIES.items() if re.search(r'(?<![a-z])' + re.escape(en) + r'(?![a-z])', w)}
TRAINERISH = ('item', 'supporter', 'stadium', 'tool', 'energy')
def era(set_id):
    m = re.match(r'^(SV|SM|BW|XY|S|M)(?=\d|[A-Z])', set_id); return m.group(1) if m else 'other'
lim = collections.defaultdict(list)
for r in L: lim[(r['set'], num(r['number']))].append(r)
def row_for(c):
    rs = lim.get((ALIAS.get(c['set_id'], c['set_id']), num(c['number'])), [])
    return rs[0] if len(rs) == 1 else None, len(rs)
def name_check(c, r):
    if key(r['name']) == key(c['name']): return 'same name'
    sp = species(c['name'])
    if sp: return 'same species' if any(key(j) in key(r['name']) for j in sp) else None
    return 'trainer or energy, type agrees' if any(t in r['type'].lower() for t in TRAINERISH) and (c['category'] or 'trainer').lower() in ('trainer', 'energy') else None
# calibration from cards that already have a rarity
by_set, by_era = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
for c in cards:
    if c['rarity'] and c['rarity'].strip() not in ('', 'None'):
        r, n = row_for(c)
        if r and r['rarity']:
            by_set[(c['set_id'], r['rarity'])][c['rarity']] += 1; by_era[(era(c['set_id']), r['rarity'])][c['rarity']] += 1
DEFAULT = {'Common': 'Common', 'Uncommon': 'Uncommon', 'Rare': 'Rare', 'Double Rare': 'Double rare', 'Art Rare': 'Illustration rare',
           'Special Art Rare': 'Special illustration rare', 'Triple Rare': 'Triple Rare', 'Character Super Rare': 'Character Super Rare',
           'Character Holo Rare': 'Character Rare', 'Holo Rare': 'Holo Rare', 'Radiant Rare': 'Radiant Rare',
           'Shiny Rare': 'Shiny rare', 'Shiny Ultra Rare': 'Shiny Ultra Rare', 'Amazing Rare': 'Amazing Rare'}
def dominant(counter):
    if not counter: return None
    label, n = counter.most_common(1)[0]
    return label if n / sum(counter.values()) >= .9 else 'AMBIGUOUS'
def label_for(set_id, lab):
    for how, cnt in (('set', by_set.get((set_id, lab))), ('era', by_era.get((era(set_id), lab)))):
        d = dominant(cnt)
        if d == 'AMBIGUOUS': return None, f'{how}: Limitless "{lab}" maps to several labels {dict(cnt)}'
        if d: return d, f'{how} calibration'
    if lab in DEFAULT: return DEFAULT[lab], 'label table'
    return None, f'no mapping for Limitless "{lab}"'
out = []
for c in cards:
    if c['rarity'] and c['rarity'].strip() not in ('', 'None'): continue
    rec = {'id': c['id'], 'set_id': c['set_id'], 'number': c['number'], 'name': c['name'], 'rarity': None}
    r, n = row_for(c)
    if not r:
        out.append({**rec, 'reason': 'not on Limitless' if n == 0 else 'several Limitless rows'}); continue
    rec.update(limitless=f"{r['set']} {r['number']} {r['name']} | {r['type']} | {r['rarity'] or '-'}",
               evidence=f"https://limitlesstcg.com/cards/jp/{r['page']}?display=list")
    chk = name_check(c, r)
    if not chk: out.append({**rec, 'reason': 'names do not agree'}); continue
    if not r['rarity']: out.append({**rec, 'reason': 'Limitless shows no rarity', 'check': chk}); continue
    if r['rarity'] == 'Holo Rare':  # Limitless uses it for HR (Hyper Rare, rainbow) in S9-S12; S9a-090 prints HR
        out.append({**rec, 'reason': 'Limitless "Holo Rare" is HR (Hyper Rare) here; not mapped', 'check': chk}); continue
    label, how = label_for(c['set_id'], r['rarity'])
    out.append({**rec, 'rarity': label, 'check': chk, 'reason': how})
json.dump(out, open('ja-decisions.json', 'w'), ensure_ascii=False, indent=1)
filled = [o for o in out if o['rarity']]
print('cards', len(out), 'filled', len(filled))
print(collections.Counter(o['rarity'] for o in filled).most_common())
print(collections.Counter(o['reason'] for o in filled).most_common())
print('left empty:'); [print(f'  {v:6} {k[:110]}') for k, v in collections.Counter(o['reason'] if not o['reason'].startswith(('set:','era:')) else o['reason'].split(' maps')[0] for o in out if not o['rarity']).most_common(14)]
