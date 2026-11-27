"""Parse the downloaded Limitless list pages into rows {set, number, name, rarity}. Offline."""
import glob, html, json, re, os
out = []
for path in sorted(glob.glob('limitless/*.html')):
    code = os.path.basename(path)[:-5]
    t = open(path, encoding='utf-8').read()
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S):
        cells = [' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', c)).split()) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
        if len(cells) >= 5:
            out.append({'page': code, 'set': cells[0], 'number': cells[1], 'name': cells[2], 'type': cells[3], 'rarity': cells[4]})
json.dump(out, open('limitless-rows.json', 'w'), ensure_ascii=False)
print(len(out), 'rows from', len(glob.glob('limitless/*.html')), 'pages')
