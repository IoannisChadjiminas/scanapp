"""Match need.json cards to collected Cardmarket list-view products (set code + number, name checked).

    python3 -I match_cardmarket_list.py RUN_DIR

RUN_DIR holds need.json (cards without a link), fixes-partial.json (links already verified),
name-map.json (Japanese name -> English Cardmarket names, from cards that already have links),
used-urls.json (pages the catalogue already uses) and cardmarket-products.jsonl (collect_listings).
Writes fixes-matched.json (one product with that number and a matching name, page not in use) and
match-detail.json (every card with its candidates). Ambiguous and number-only cards are held:
they are checked by eye or go on the browser worklist.
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
K = Path(sys.argv[1])
EXP = {"SI": ["Start-Deck-100"], "SP": ["Sword-Shield-Promos"], "MG": ["Mega-Gengar-ex-Mega-Dragonite-ex-Mega-Feraligatr-ex-Special-Deck-Set"],
       "SAf": ["Sword-Shield-Starter-Decks", "V-Starter-Decks"], "SAl": ["Sword-Shield-Starter-Decks", "V-Starter-Decks"],
       "SAg": ["Sword-Shield-Starter-Decks", "V-Starter-Decks"], "SAr": ["Sword-Shield-Starter-Decks", "V-Starter-Decks"],
       "SAw": ["Sword-Shield-Starter-Decks", "V-Starter-Decks"], "SC2": ["VMAX-Starter-Decks"], "SCr": ["VMAX-Starter-Decks"],
       "jr-grimmsnarl-vmax-starter-set": ["VMAX-Starter-Decks"], "jr-steelix-constructed-standard-deck": ["Steelix-Constructed-Standard-Deck"],
       "jr-tyranitar-constructed-standard-deck": ["Tyranitar-Constructed-Standard-Deck"], "BWP": ["BW-Promos"], "M-P": ["M-P-Promos"],
       "MMBP": ["M-Master-Deck-Build-Box-Power-Style"], "MMBS": ["M-Master-Deck-Build-Box-Speed-Style"], "SMA": ["Sun-Moon-Starter-Set"],
       "SMB": ["Premium-Trainer-Box"], "SVI": ["Scarlet-Violet-Battle-Academy"], "HXY": ["XY-Beginning-Set"],
       "SML": ["Sun-Moon-Family-Pokemon-Card-Game"], "MDB": ["Master-Deck-Build-Box-EX"], "BKv": ["Battle-Strength-Decks"],
       "BKt": ["Battle-Strength-Decks"], "BKc": ["Battle-Strength-Decks"], "S12a": ["VSTAR-Universe"], "SM1p": ["Strength-Expansion-Pack-Sun-Moon"],
       "SP4": ["Eevee-Heroes-VMAX-Special-Set"], "mep": ["MEP-Black-Star-Promos"], "30th": ["30th-Celebration"],
       "WCS23": ["World-Championships-2023-Yokohama-Deck-Pikachu"], "SGG": ["Gengar-VMAX-High-Class-Deck"], "det1": ["Detective-Pikachu"]}

def norm(s):
    s = s.casefold().replace("é", "e").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

need = json.loads((K / "need.json").read_text())
done = json.loads((K / "fixes-partial.json").read_text())
names = json.loads((K / "name-map.json").read_text())
used = set(json.loads((K / "used-urls.json").read_text())) | {v["url"] for v in done.values()}
by_exp = defaultdict(list)
for line in (K / "cardmarket-products.jsonl").open():
    p = json.loads(line)
    exp = p["url"].split("/Singles/")[1].split("/")[0]
    m = re.search(r"\(([^()]*)\)\s*$", p["name"])
    code = m.group(1).split() if m else []
    p["code"] = " ".join(code[:-1]) if len(code) > 1 else ""
    p["num"] = code[-1] if code else ""
    p["en"] = norm(re.sub(r"\s*\([^()]*\)\s*$", "", p["name"]))
    p["en"] = re.sub(r"-v\d+$", "", p["en"])
    by_exp[exp].append(p)
out, report = {}, defaultdict(Counter)
detail = []
for card in need:
    if card["id"] in done:
        continue
    exps = EXP.get(card["set_id"])
    if not exps:
        report[card["set_id"]]["no_expansion"] += 1
        continue
    num = card["collector_number"].lstrip("0")
    cands = [p for e in exps for p in by_exp[e] if p["num"].lstrip("0").casefold() == num.casefold()]
    want = Counter(names.get(card["name"], {}))
    if not want:  # same Pokémon with a card-type suffix: base name from the map, suffix kept
        m = re.fullmatch(r"(.+?)(VMAX|VSTAR|V|ex|EX|GX)", card["name"])
        if m and names.get(m.group(1)):
            base = Counter(names[m.group(1)]).most_common(1)[0][0]
            want = Counter({base + "-" + m.group(2).casefold(): 1})
    ok = [p for p in cands if p["en"] in want and p["url"] not in used]
    status = "matched" if len(ok) == 1 else ("ambiguous" if len(ok) > 1 else ("number_only" if cands else "none"))
    report[card["set_id"]][status] += 1
    detail.append({"id": card["id"], "name": card["name"], "want": list(want)[:3], "status": status,
                   "cands": [(p["name"], p["url"].split("/")[-1]) for p in cands][:4]})
    if status == "matched":
        p = ok[0]
        out[card["id"]] = {"url": p["url"], "product_id": int(p["product_id"]), "product_name": p["url"].split("/")[-1]}
(K / "fixes-matched.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
(K / "match-detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=1))
for s, c in sorted(report.items()):
    print(s, dict(c))
print("matched", len(out), "dup urls", len(out) - len({v["url"] for v in out.values()}))
