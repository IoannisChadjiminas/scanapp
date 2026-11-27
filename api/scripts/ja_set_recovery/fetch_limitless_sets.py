"""Download Limitless's card list (list view) for each Japanese set, politely. Resumable."""
import json, time, urllib.request, os
for code in json.load(open('limitless-sets.json')):
    path = f'limitless/{code}.html'
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        continue
    req = urllib.request.Request(f'https://limitlesstcg.com/cards/jp/{code}?display=list', headers={'User-Agent': 'catalogue-check'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                open(path, 'wb').write(r.read()); break
        except Exception as e:
            print(code, 'retry', e, flush=True); time.sleep(10)
    time.sleep(1.5)
print('done', len(os.listdir('limitless')))
