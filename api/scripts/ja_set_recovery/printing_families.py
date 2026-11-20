"""Printing families: the regular print plus its Prize Pack and stamped (Trick or Trade) copies.

Members: en:PPS<n>-<CODE>-<NUM> rows (Prize Pack) and rows whose variants_json names a
printed_set and a stamp (Trick or Trade). Base: the regular row in the set that <CODE> stands
for, with the same number. <CODE> -> set: the en set where the most members of that code find
a row of the same name at the same number; used only if at least 80% of them do. A member joins
its base only if the names are equal (case, spaces and punctuation ignored) and the art is the
same: cosine of the two catalogue vectors >= MIN_COS (0.70: every pair from 0.70 to 0.88 was checked
by eye and is the same art with a stamp; the next lower pairs, 0.38-0.43, are card-back images). family id = the base row's id; every other
row is its own family. Deterministic: same catalogue -> same families.
    python3 families.py CATALOG.sqlite VECTOR_DIR OUT.json
"""
import collections, json, re, sqlite3, sys, unicodedata
import numpy as np
MIN_COS = 0.70
DB, VEC, OUT = sys.argv[1:4]
db = sqlite3.connect(DB)
rows = db.execute("select id,name,set_id,collector_number,variants_json,language from cards").fetchall()
ids = [str(x) for x in np.load(VEC + "/embedding_card_ids.npy", allow_pickle=True)]
emb = np.load(VEC + "/embeddings.npy").astype(np.float32); pos = {c: i for i, c in enumerate(ids)}
def nm(s): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())
def nu(s): return (s or "").lstrip("0") or "0"
members = []
for cid, name, sid, num, var, lang in rows:
    m = re.match(r"en:PPS\d+-([A-Za-z0-9]+)-(\w+)$", cid)
    if m: members.append((cid, name, "prize-pack", m.group(1).upper(), nu(m.group(2)))); continue
    try: v = json.loads(var or "{}")
    except ValueError: v = {}
    if lang == "en" and v.get("printed_set") and v.get("stamp"):
        members.append((cid, name, "stamped", str(v["printed_set"]).upper(), nu(num)))
member_ids = {m[0] for m in members}
base = {}
for cid, name, sid, num, var, lang in rows:
    if lang == "en" and cid not in member_ids: base.setdefault((sid, nu(num)), []).append((cid, name))
by_code = collections.defaultdict(list)
for m in members: by_code[m[3]].append(m)
code_set = {}
sets = {k[0] for k in base}
for code, ms in sorted(by_code.items()):
    score = collections.Counter()
    for s in sets:
        for _, name, _, _, n in ms:
            if any(nm(b[1]) == nm(name) for b in base.get((s, n), [])): score[s] += 1
    if score:
        s, k = score.most_common(1)[0]
        if k >= 0.8 * len(ms): code_set[code] = {"set": s, "agree": k, "members": len(ms)}
        else: code_set[code] = {"set": None, "best": s, "agree": k, "members": len(ms)}
fam = {}; joined = []; left = []
for cid, name, kind, code, n in members:
    s = (code_set.get(code) or {}).get("set")
    cands = [b for b in base.get((s, n), []) if nm(b[1]) == nm(name)] if s else []
    if len(cands) != 1: left.append({"id": cid, "kind": kind, "why": "no base set" if not s else f"{len(cands)} base rows named alike"}); continue
    b = cands[0][0]
    if cid not in pos or b not in pos: left.append({"id": cid, "kind": kind, "base": b, "why": "no vector"}); continue
    cos = float(emb[pos[cid]] @ emb[pos[b]] / (np.linalg.norm(emb[pos[cid]]) * np.linalg.norm(emb[pos[b]])))
    if cos < MIN_COS: left.append({"id": cid, "kind": kind, "base": b, "why": f"art differs (cos {cos:.3f})"}); continue
    fam[cid] = b; fam.setdefault(b, b); joined.append({"id": cid, "base": b, "kind": kind, "cos": round(cos, 4)})
json.dump({"rule": "printing-family-v1", "min_cos": MIN_COS, "code_set": code_set, "family": fam, "joined": joined, "left": left},
          open(OUT, "w"), ensure_ascii=False, indent=0)
fams = collections.Counter(fam.values())
print("members", len(members), collections.Counter(m[2] for m in members), "joined", len(joined), collections.Counter(j["kind"] for j in joined),
      "left", len(left), collections.Counter(l["why"].split(" (")[0] for l in left))
print("families with >1 row", len(fams), "size histogram", sorted(collections.Counter(fams.values()).items()))
cs = sorted(j["cos"] for j in joined); print("cos min/p5/median", cs[0], cs[len(cs)//20], cs[len(cs)//2])
print("codes without a set", {c: v for c, v in code_set.items() if not v.get("set")}, "codes", len(code_set), "of", len(by_code))
