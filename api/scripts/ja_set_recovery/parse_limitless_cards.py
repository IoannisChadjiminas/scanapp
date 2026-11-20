"""Limitless JP set pages -> [{code, num, name_ja, set_name_ja}] (set + printed number + Japanese name)."""
import glob, html, json, os, re, sys
D = sys.argv[1]; out = []
for f in sorted(glob.glob(D + "/*.html")):
    code = os.path.basename(f)[:-5]; h = open(f, encoding="utf-8").read()
    t = h[h.find('card-list'):]; t = t[:t.find('</table>')]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 3: continue
        m = re.search(r'href="/cards/jp/([^/"]+)/([^"]+)"', tds[1])
        if not m: continue
        sn = re.search(r'data-tooltip="([^"]*)"', tds[0])
        out.append({"code": m.group(1), "page": code, "num": html.unescape(m.group(2)),
                    "name_ja": html.unescape(re.sub(r"<[^>]+>", "", tds[2])).strip(),
                    "set_name_ja": html.unescape(sn.group(1)) if sn else ""})
json.dump(out, open("limitless_cards.json", "w"), ensure_ascii=False)
from collections import Counter
c = Counter(r["page"] for r in out); print(len(out), "cards on", len(c), "pages")
print("pages where card set code differs:", sorted({(r["page"], r["code"]) for r in out if r["page"] != r["code"]})[:20])
