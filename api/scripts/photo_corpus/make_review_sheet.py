"""Create a private, local HTML review sheet and labels.csv for a corpus."""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
import re


def title_guess(title: str) -> str:
    match = re.search(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b", title)
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def name_in_title(name: str, title: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    normalized = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
    return bool(tokens) and " ".join(tokens) in normalized


def create(corpus: Path, results_file: Path | None = None) -> tuple[int, int]:
    with (corpus / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    results = {}
    if results_file and results_file.exists():
        data = json.loads(results_file.read_text(encoding="utf-8"))
        results = {int(row["index"]): row for row in data.get("results", []) if "index" in row}
    sections = []
    labels = []
    auto = 0
    for i, row in enumerate(rows):
        result = results.get(i, {})
        guess = title_guess(row.get("title", ""))
        candidates = result.get("candidates", [])
        top = candidates[0] if candidates else {}
        agreed = bool(
            guess
            and top.get("number")
            and re.fullmatch(r"\d{1,3}/\d{1,3}", str(top.get("number")))
            and top["number"] == guess
            and name_in_title(str(top.get("name", "")), row.get("title", ""))
        )
        label_source = "auto_title_server_agreement" if agreed else "needs_review"
        auto += int(agreed)
        labels.append({
            "photo": row["photo"], "bucket": row.get("bucket", ""),
            "card_id": top.get("card_id", "") if agreed else "",
            "label_source": label_source,
            "title_number_guess": guess,
            "reviewed": "false",
        })
        candidate_html = "".join(
            f'<option value="{html.escape(str(c.get("card_id", "")), quote=True)}">'
            f'{html.escape(str(c.get("name", "")))} — {html.escape(str(c.get("set_name", "")))} '
            f'{html.escape(str(c.get("number", "")))} ({html.escape(str(c.get("card_id", "")))})</option>'
            for c in candidates
        )
        auto_card = str(top.get("card_id", "")) if agreed else ""
        sections.append(f"""<article data-index="{i}" data-auto-card="{html.escape(auto_card, quote=True)}" data-auto-label="{str(agreed).lower()}">
<img src="{html.escape(row['photo'], quote=True)}" loading="lazy" alt="Card photo {i+1}">
<div><h2>{i+1}. {html.escape(row.get('bucket',''))}</h2>
<p class="title">{html.escape(row.get('title',''))}</p>
<p>Title number guess: <b>{html.escape(guess or 'none')}</b> · API status: {html.escape(str(result.get('status','not run')))}</p>
<p>Stage result: {html.escape(str(result.get('stage','full pipeline')))} · Top card: {html.escape(str(top.get('card_id','none')))}</p>
<label>Choose the true card <select class="candidate"><option value="">Choose or leave blank</option>{candidate_html}</select></label>
<label>Or enter card ID <input class="custom" type="text" maxlength="128"></label>
<button type="button" class="save">Mark reviewed</button> <span class="state">{label_source}</span></div>
</article>""")
    with (corpus / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labels[0]) if labels else ["photo", "bucket", "card_id", "label_source", "title_number_guess", "reviewed"])
        writer.writeheader()
        writer.writerows(labels)
    page = """<!doctype html><meta charset="utf-8"><title>Private photo corpus review</title>
<style>body{font:16px system-ui;margin:1rem;background:#f4f4f4}header{position:sticky;top:0;background:white;padding:1rem;z-index:2}article{display:grid;grid-template-columns:minmax(200px,340px) 1fr;gap:1rem;background:white;margin:1rem 0;padding:1rem;border-radius:12px}img{width:100%;height:auto;max-height:540px;object-fit:contain;background:#ddd}.title{font-weight:600}label{display:block;margin:.6rem 0}select,input{max-width:100%;padding:.5rem}button{padding:.6rem}.state{margin-left:.5rem;color:#555}@media(max-width:700px){article{grid-template-columns:1fr}}</style>
<header><h1>Private corpus label review</h1><p>Photos and listing text stay on this computer. Auto labels require a title-number and card-name match with the server top card; review them before treating them as truth.</p><button id="export">Download reviewed labels.csv</button></header>
""" + "\n".join(sections) + """
<script>
const state=new Map();
document.querySelectorAll('article').forEach(a=>a.querySelector('.save').onclick=()=>{
 const id=a.querySelector('.custom').value.trim()||a.querySelector('.candidate').value;
 state.set(a.dataset.index,{card_id:id,reviewed:!!id});
 a.querySelector('.state').textContent=id?'reviewed':'needs_review';
});
document.querySelector('#export').onclick=()=>{
 const rows=[...document.querySelectorAll('article')].map(a=>{const r=state.get(a.dataset.index)||{};const auto=a.dataset.autoLabel==='true';return {photo:a.querySelector('img').getAttribute('src'),card_id:r.card_id||a.dataset.autoCard||'',reviewed:r.reviewed?'true':(auto?'auto':'false')};});
 const q=v=>'"'+String(v).replaceAll('"','""')+'"';
 const csv='photo,card_id,reviewed\\n'+rows.map(r=>[r.photo,r.card_id,r.reviewed].map(q).join(',')).join('\\n');
 const u=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const x=document.createElement('a');x.href=u;x.download='reviewed-labels.csv';x.click();URL.revokeObjectURL(u);
};</script>"""
    (corpus / "review.html").write_text(page, encoding="utf-8")
    return len(rows), auto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/photo-corpus-fullsize-20261023"))
    parser.add_argument("--results", type=Path, default=Path("/tmp/pokesingle-fullsize-results/corpus-results.json"))
    args = parser.parse_args()
    count, auto = create(args.corpus, args.results)
    print(f"Review sheet created for {count} photos; {auto} strict title/server matches marked as auto-label candidates.")


if __name__ == "__main__":
    main()
