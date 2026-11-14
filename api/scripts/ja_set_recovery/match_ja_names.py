"""Japanese names for ja: rows that carry only an English name, from Limitless JP set lists.

Join on set + printed number only; a name is accepted only when it agrees with the row's English
name: the (English, Japanese) pair already exists on another ja row of the catalogue, or the
species in the English name translates (ja_species_names.json) into the Japanese name with the
same mechanic suffix. Our set -> Limitless set is the Limitless set where most rows agree.
A Mega card whose source name has no Mega prefix (Limitless drops it on XY Mega EX) is not
accepted. A row whose English name has no species (trainers, energies, species missing from the
table) is accepted only from a set where at least 85% of the rows that have the number agree.
A set maps to a Limitless set only when at least 70% of its numbered rows agree.
Writes names.json {accepted, review, no_source, set_map}.
"""
import collections, json, re, sqlite3, sys, unicodedata
DB, LIM, SPECIES = sys.argv[1:4]
JA = re.compile(r"[ぁ-んァ-ヶ一-龯]")
db = sqlite3.connect(DB)
rows = db.execute("select id,name,view_title,set_id,collector_number,printed_collector_number,category from cards where language='ja'").fetchall()
targets = [r for r in rows if r[0].startswith("ja:") and not JA.search(r[1] or "")]
def n(s): return re.sub(r"[\s'’.\-:!]", "", unicodedata.normalize("NFKC", s or "").lower())
pairs = collections.defaultdict(collections.Counter)
for r in rows:
    if JA.search(r[1] or "") and r[2] and not JA.search(r[2]): pairs[n(r[2])][n(r[1])] += 1
species = json.load(open(SPECIES))["species"]
sp_keys = sorted(species, key=len, reverse=True)
SUFFIX = ["vmax", "vstar", "v-union", "gx", "ex", "break", "lv.x", "legend", "prime", "star", "v"]
def suffix(s):
    s = unicodedata.normalize("NFKC", s).lower().strip()
    for x in SUFFIX:
        if re.search(r"(^|[\s\-])" + re.escape(x) + r"$", s) or (x in ("gx", "ex", "v", "vmax", "vstar") and s.endswith(x) and not s[-len(x)-1:-len(x)].isalpha()): return x
    return ""
def jsuffix(j):
    j = unicodedata.normalize("NFKC", j).lower().strip()
    for x in SUFFIX:
        if j.endswith(x.replace("-", "")) or j.endswith(x): return x
    return ""
import functools
WORD = re.compile(r"[a-z0-9é♀♂]+(?:[.'’\-][a-z0-9é♀♂]+)*")
@functools.lru_cache(None)
def species_of(en):
    e = unicodedata.normalize("NFKC", en).lower(); toks = WORD.findall(e)
    found = [k for k in species if k in e and re.search(r"(^|[\s'’\-])" + re.escape(k) + r"($|[\s'’\-])", e)]
    return max(found, key=len) if found else None
MEGA = re.compile(r"^(M\s?[A-Z]|Mega\s)")
@functools.lru_cache(None)
def agree(en, ja):
    if n(ja) in pairs.get(n(en), {}): return "pair"
    k = species_of(en)
    if k and species[k] in unicodedata.normalize("NFKC", ja) and suffix(en) == jsuffix(ja): return "species"
    return None
lim = json.load(open(LIM)); L = collections.defaultdict(dict)
for c in lim:
    L[c["code"]].setdefault(c["num"].lstrip("0") or "0", c)
def num(r):
    p = (r[5] or "").split("/")[0].strip() if r[5] else ""
    return (p or r[4] or "").lstrip("0") or "0"
by_set = collections.defaultdict(list)
for r in targets: by_set[r[3]].append(r)
set_map = {}; accepted = {}; review = []; no_source = []
for s, rs in sorted(by_set.items()):
    best = None
    for code, cards in L.items():
        ok = sum(1 for r in rs if num(r) in cards and agree(r[2] or r[1], cards[num(r)]["name_ja"]))
        if ok and (best is None or ok > best[1]): best = (code, ok)
    if best and best[1] >= max(2, 0.5 * len(rs)) or (best and best[1] >= 0.9 * len(rs)):
        set_map[s] = {"limitless": best[0], "agree": best[1], "rows": len(rs)}
        cards = L[best[0]]
        ratio = best[1] / max(1, sum(1 for r in rs if num(r) in cards))
        set_map[s]["ratio"] = round(ratio, 3)
        if ratio < 0.7:
            del set_map[s]
            for r in rs: no_source.append({"id": r[0], "name": r[1], "why": f"no Limitless set (best {best[0]} agrees on {ratio:.0%})"})
            continue
        for r in rs:
            c = cards.get(num(r))
            if c is None: no_source.append({"id": r[0], "name": r[1], "why": "number not in " + best[0]}); continue
            en = r[2] or r[1]; how = agree(en, c["name_ja"])
            if MEGA.search(en) and not re.match(r"(メガ|M)", c["name_ja"]): how = None
            elif not how and species_of(en) is None and ratio >= 0.85: how = "set-aligned"
            if how: accepted[r[0]] = {"name_ja": c["name_ja"], "en": r[1], "source": f"limitless:{best[0]}/{c['num']}", "check": how}
            else: review.append({"id": r[0], "en": r[1], "limitless": f"{best[0]}/{c['num']}", "name_ja": c["name_ja"]})
    else:
        for r in rs: no_source.append({"id": r[0], "name": r[1], "why": "no Limitless set" + (f" (best {best[0]} {best[1]}/{len(rs)})" if best else "")})
json.dump({"accepted": accepted, "review": review, "no_source": no_source, "set_map": set_map}, open("names.json", "w"), ensure_ascii=False, indent=0)
print("targets", len(targets), "sets", len(by_set), "mapped sets", len(set_map))
print("accepted", len(accepted), collections.Counter(v["check"] for v in accepted.values()), "review", len(review), "no source", len(no_source))
