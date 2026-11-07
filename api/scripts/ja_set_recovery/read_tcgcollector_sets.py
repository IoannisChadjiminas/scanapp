"""Read TCG Collector set pages (card label + image URL) in the owner's Chrome. No downloads.

TCG Collector is an owner-approved Japanese image source; its pages answer 403 to plain HTTP,
so this drives a new Chrome window it opens at start (window and tab pinned) the way the handoff's
section 4.1 describes: one page every 15 seconds, and a human-check page stops the run (the
owner clears it, then rerun; finished sets are skipped). Records every <img> whose source is
under /content/images/ and whose alt ends in "(...)".

    python3 read_tcgcollector_sets.py RUN_DIR

Reads RUN_DIR/source-pages/tcgcollector-20261107/targets.json, writes one
<group_id>.json per set next to it.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

GAP_S = 15
JS = r"""
var low = ((document.title||'') + ' ' + ((document.body&&document.body.innerText)||'').slice(0,600)).toLowerCase();
var human = low.indexOf('verify you are human')>=0 || low.indexOf('just a moment')>=0 || low.indexOf('access denied')>=0;
var im = [...document.querySelectorAll('img')].filter(i => (i.getAttribute('src')||'').includes('/content/images/') && /\)\s*$/.test(i.alt||''));
var pages = [...new Set([...document.querySelectorAll('a[href*="page="]')].map(a => a.href))];
JSON.stringify({title: document.title, href: location.href, ready: document.readyState, human: human,
  cards: im.map(i => [i.alt, i.getAttribute('src')]), pages: pages});
"""


def osa(script):
    return subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True).stdout.strip()


def main(run_dir):
    out = Path(run_dir).resolve() / "source-pages/tcgcollector-20261107"
    targets = json.loads((out / "targets.json").read_text())
    # always work in a new window of our own, never in the tab the owner is using; then pin it
    osa('tell application "Google Chrome" to make new window')
    window = osa('tell application "Google Chrome" to get id of window 1')
    tab = osa('tell application "Google Chrome" to get id of active tab of window 1')
    where = f'(first tab of window id {window} whose id is {tab})'

    def visit(url):
        osa(f'tell application "Google Chrome" to tell {where} to set URL to {json.dumps(url)}')
        time.sleep(GAP_S)
        for _ in range(30):
            page = json.loads(osa(f'tell application "Google Chrome" to tell {where} to execute javascript {json.dumps(JS)}'))
            if page["human"] or (page["ready"] == "complete" and page["cards"]):
                return page
            time.sleep(2)
        return page

    for gid, target in targets.items():
        dest = out / f"{gid}.json"
        if dest.exists():
            continue
        page = visit(target["url"] + "&displayAs=images")
        if page["human"]:
            print(json.dumps({"stopped": "human_check", "group": gid, "title": page["title"]}), flush=True)
            raise SystemExit(2)
        cards, seen_pages = list(page["cards"]), {page["href"]}
        for extra in page["pages"]:
            if extra in seen_pages:
                continue
            seen_pages.add(extra)
            more = visit(extra)
            if more["human"]:
                print(json.dumps({"stopped": "human_check", "group": gid, "page": extra}), flush=True)
                raise SystemExit(2)
            cards += more["cards"]
        dest.write_text(json.dumps({"group_id": gid, "name": target["name"], "url": target["url"],
                                    "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "pages": sorted(seen_pages), "cards": cards}, ensure_ascii=False, indent=1))
        print(json.dumps({"group": gid, "name": target["name"], "cards": len(cards), "pages": len(seen_pages)}, ensure_ascii=False), flush=True)
    print(json.dumps({"done": True}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
