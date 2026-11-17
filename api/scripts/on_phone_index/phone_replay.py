"""Picture-only phone test: each gate photo's query vector (embed_photos.py) searched against two phone
indexes. No text step: the first answer is the top picture match.

    python3 phone_replay.py QUERIES_DIR OLD_RELEASE NEW_RELEASE FAMILIES_JSON OUT_JSON

Family: cards joined by reprint_of in the new index (meta and prints.tsv) or by families.json.
Twin of the right card: same family, or a picture vector at least 0.95 similar to a right card's (the
server's printing-alternative rule); `cross_language` marks a twin in another language.
Print sheet: the top two matches are in one family, or 0.95 similar to each other, and their scores
are within 0.05.
"""
import json, sys, collections
from pathlib import Path
import numpy as np
qdir, old, new, fam_path, out = map(Path, sys.argv[1:6])
Q = np.load(qdir / 'queries.npy'); meta = json.loads((qdir / 'queries.json').read_text())
PANEL = lambda m: 'dev' if m['shard'].split('/')[-1] in ('dev0', 'dev1', 'dev2', 'devr8', 'dev9') else (
    'dev2' if m['shard'].startswith('shards2') else 'dev3')

def load(rel):
    ids = (rel / 'card_index.ids.txt').read_text().split('\n')[:-1]
    v = np.frombuffer((rel / 'card_index.f16.bin').read_bytes(), dtype='<f2').reshape(len(ids), 384).astype(np.float32)
    return ids, v / np.linalg.norm(v, axis=1, keepdims=True)

parent = {}
def find(x):
    while parent.get(x, x) != x:
        parent[x] = parent.get(parent[x], parent[x]); x = parent[x]
    return x
def join(a, b):
    if a and b: parent[find(a)] = find(b)
lines = (new / 'card_index.meta.tsv').read_text().split('\n')[:-1]
head = lines[0].lstrip('#').split('\t'); ri = head.index('reprint_of')
for l in lines[1:]:
    f = l.split('\t'); join(f[0], f[ri])
for l in (new / 'card_index.prints.tsv').read_text().split('\n')[1:-1]:
    f = l.split('\t'); join(f[0], f[1])
for a, b in json.loads(fam_path.read_text())['family'].items():
    join(a, b)
same_family = lambda a, b: a and b and find(a) == find(b)
NIDS, NV = load(new)
NPOS = {c: i for i, c in enumerate(NIDS)}
def twins(a, b):
    if same_family(a, b):
        return True
    return a in NPOS and b in NPOS and float(NV[NPOS[a]] @ NV[NPOS[b]]) >= 0.95
lang = lambda c: c.split(':', 1)[0] if ':' in c else 'en'

def run(rel):
    ids, v = load(rel)
    S = Q @ v.T
    res = []
    for k, m in enumerate(meta):
        top = np.argsort(-S[k])[:5]
        t = [ids[j] for j in top]; s = [float(S[k, j]) for j in top]
        exp = [e for e in m['expected'] if ':' in e or e.startswith('extra-')]
        res.append({'first': t[0], 'top5': t, 's1': s[0], 's2': s[1], 'right_first': t[0] in exp,
                    'right_top5': bool(set(exp) & set(t)), 'twin_first': (t[0] not in exp) and any(twins(t[0], e) for e in exp),
                    'cross_language': all(lang(t[0]) != lang(e) for e in exp),
                    'sheet': twins(t[0], t[1]) and s[0] - s[1] <= 0.05})
    return res

A, B = run(old), run(new)
by = collections.defaultdict(collections.Counter)
changed = collections.Counter(); rows = []
for m, a, b in zip(meta, A, B):
    p = PANEL(m)
    for tag, r in (('old', a), ('new', b)):
        by[p][tag + '_right_first'] += r['right_first']; by[p][tag + '_wrong_first'] += not r['right_first']
        by[p][tag + '_right_top5'] += r['right_top5']; by[p][tag + '_twin_first'] += r['twin_first']
        by[p][tag + '_sheet'] += r['sheet']
    by[p]['photos'] += 1
    if a['first'] != b['first']:
        if a['right_first'] and b['right_first']:
            kind = 'right_to_other_right'
        elif b['right_first']:
            kind = 'fixed'
        elif a['right_first']:
            kind = 'right_to_twin' if b['twin_first'] else 'broken'
        else:
            kind = 'wrong_to_twin' if b['twin_first'] else 'wrong_to_other_wrong'
        changed[kind] += 1
        rows.append({'id': m['id'], 'panel': p, 'kind': kind, 'expected': m['expected'], 'old': a['first'],
                     'new': b['first'], 'new_cross_language': b['cross_language'], 'old_s': round(a['s1'], 4), 'new_s': round(b['s1'], 4)})
sheet = collections.Counter()
for m, a, b in zip(meta, A, B):
    sheet[(a['sheet'], b['sheet'])] += 1
summary = {'photos': len(meta), 'panels': {p: dict(c) for p, c in by.items()}, 'first_changed': dict(changed),
           'print_sheet': {'old': sum(a['sheet'] for a in A), 'new': sum(b['sheet'] for b in B),
                           'both': sheet[(True, True)], 'new_only': sheet[(False, True)], 'old_only': sheet[(True, False)]},
           'frame_found': sum(m['found'] for m in meta)}
out.write_text(json.dumps({'summary': summary, 'changed': rows}, indent=1, ensure_ascii=False))
print(json.dumps(summary, indent=1))
