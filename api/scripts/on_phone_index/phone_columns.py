"""Values for the phone index's appended columns and reviewed fixes, as extend_index.py's COLUMNS_JSON.

    python3 phone_columns.py --base RELEASE_DIR --catalogue CATALOG_SQLITE --totals-db TOTALS_SQLITE \
        --families FAMILIES_JSON --names NAMES_JSON --tcgdex-sets SETS_JSON --tcgdex-hp HP_JSON \
        --limitless-sets LIM_JSON --set-map NAMES3_JSON --ocr-reads READS_JSONL --add-ids IDS_TXT \
        --out COLUMNS_JSON

Offline; every source is a file. Column rules:

release_year  Year of the set's release date: TCGdex (`/v2/{lang}/sets/{id}` releaseDate); for a
              Japanese set TCGdex lacks, Limitless's Japanese set index through NAMES3's set map
              (or the same code). Empty when neither has a date (Japanese promo sets span years).
hp            TCGdex card HP (`/v2/{lang}/cards?hp=eq:N`) for the row's provider id, Pokemon only.
printing      prize_pack: a Play! Pokemon Prize Pack set (PPS*). stamped: a printing family member of
              kind stamped, or a Trick or Trade set (tot*). promo: a Japanese promo code, or a set
              named as promos (Black Star, Promo, McDonald's, Burger King, Professor Program, POP,
              Best of game, Futsal). other: trainer kits, the Classic decks, extra reference rows,
              the 151 UPC metal card. regular: everything else.
reprint_of    For prize_pack and stamped rows: the regular card of its printing family
              (families.json), or the base the family step named when it left the row out.
name_en       For ja rows: the catalogue's English title (view_title), without a scraped
              "(CODE NNN)From N/A" tail.

Fixes: `name` from NAMES_JSON (build_phone_names.py). `set_total` for ja rows with neither total nor
promo code, from OCR reads of the set's reference images (READS_JSONL, ocr_totals.py): accepted when
at least two reads whose numerator equals the card's own number give the same printed total and no
such read gives another.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_index import JA_PROMO_CODES, row_identity  # noqa: E402

PROMO_NAME = re.compile(r'Promo|Black Star|McDonald|Burger King|Professor Program|POP Series|Best of game|Futsal')
OTHER_SET = re.compile(r'^(tk-|CLB$|CLC$|CLV$|clc$|pooka-|CLF$|CLK$|CLL$|sv03\.5-upc$)')
SCRAPED_TAIL = re.compile(r'\s*\([^)]*\)\s*From N/A$')
LIM_DATE = re.compile(r'^\d{1,2} \w{3} (\d{2})$')


def year(date: str | None) -> str:
    if not date:
        return ''
    m = re.match(r'^(\d{4})[-/]', date)
    if m:
        return m.group(1)
    m = LIM_DATE.match(date)
    return f'20{m.group(1)}' if m else ''


def accepted_totals(reads_path: Path) -> tuple[dict[str, int], dict[str, dict]]:
    by_set = collections.defaultdict(list)
    for line in reads_path.read_text().splitlines():
        r = json.loads(line)
        if 'fractions' not in r:
            continue
        own = [b for a, b in r['fractions'] if str(a) == str(int(r['number']))]
        by_set[r['set']].append(own[0] if len(set(own)) == 1 else None)
    accepted, evidence = {}, {}
    for sid, totals in by_set.items():
        seen = collections.Counter(t for t in totals if t)
        evidence[sid] = {'reads': len(totals), 'totals': dict(seen)}
        if len(seen) == 1 and next(iter(seen.values())) >= 2:
            accepted[sid] = next(iter(seen))
    return accepted, evidence


def main() -> None:
    p = argparse.ArgumentParser()
    for name in ('base', 'catalogue', 'totals-db', 'families', 'names', 'tcgdex-sets', 'tcgdex-hp',
                 'limitless-sets', 'set-map', 'ocr-reads', 'add-ids', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    meta = {}
    lines = (a.base / 'card_index.meta.tsv').read_text().split('\n')[:-1]
    header = lines[0].lstrip('#').split('\t')
    for line in lines[1:]:
        f = line.split('\t')
        meta[f[0]] = dict(zip(header, f))
    add_ids = a.add_ids.read_text().split()
    with sqlite3.connect(f'{a.catalogue.resolve().as_uri()}?mode=ro', uri=True) as db:
        cards = {r[0]: r for r in db.execute(
            'SELECT id, name, collector_number, printed_collector_number, language, set_id, set_name, '
            'view_title, category, provider_id FROM cards')}
    with sqlite3.connect(f'{a.totals_db.resolve().as_uri()}?mode=ro', uri=True) as db:
        op_totals = {(str(lang).casefold(), str(s).split(':')[-1].casefold()): t
                     for lang, s, t in db.execute('SELECT language, set_id, official_total FROM set_totals')}
    fam = json.loads(a.families.read_text())
    family = fam['family']
    stamped = {j['id'] for j in fam['joined'] + fam['left'] if j['kind'] == 'stamped'}
    left_base = {j['id']: j['base'] for j in fam['left'] if j.get('base')}
    names = json.loads(a.names.read_text())['names']
    ts = json.loads(a.tcgdex_sets.read_text())
    hp = json.loads(a.tcgdex_hp.read_text())
    lim = json.loads(a.limitless_sets.read_text())
    set_map = json.loads(a.set_map.read_text())['set_map']
    totals, evidence = accepted_totals(a.ocr_reads)

    def release_year(lang, sid):
        y = year((ts.get(f'{lang}:{sid}') or {}).get('releaseDate'))
        if not y and lang == 'ja':
            code = (set_map.get(sid) or {}).get('limitless') or (sid if sid in lim else None)
            y = year((lim.get(code) or {}).get('date')) if code else ''
        return y

    def printing(cid, lang, sid, set_name, code):
        if cid.startswith('extra-') or OTHER_SET.match(sid or ''):
            return 'other'
        if (sid or '').startswith('PPS'):
            return 'prize_pack'
        if cid in stamped or re.match(r'^tot\d', sid or ''):
            return 'stamped'
        if code or (lang == 'ja' and sid in JA_PROMO_CODES) or PROMO_NAME.search(set_name or ''):
            return 'promo'
        return 'regular'

    rows, counts = {}, collections.Counter()
    for cid in list(meta) + add_ids:
        _, name, number, printed, lang, sid, set_name, title, category, provider = cards[cid]
        m = meta.get(cid)
        r = {}
        if m is None:  # an added row: the six base columns as export_index.py builds them
            total, code = row_identity(number or '', printed or '', lang, sid,
                                       op_totals.get((lang.casefold(), sid.casefold())))
            r.update(name=name, number=number or '', printed_number=printed or '', set_total=total,
                     language=lang, promo_code=code, row_kind='', alt_name='', printing_family='')
            code_now, total_now = code, total
        else:
            code_now, total_now = m.get('promo_code', ''), m['set_total']
        if cid in names:
            r['name'] = names[cid]['name']
        if lang == 'ja' and not total_now and not code_now and sid in totals:
            r['set_total'] = str(totals[sid])
            counts['set_total_filled'] += 1
        r['release_year'] = release_year(lang, sid)
        r['hp'] = str(hp.get(f'{lang}:{provider}', '')) if category in (None, '', 'Pokemon') else ''
        kind = printing(cid, lang, sid, set_name, code_now)
        r['printing'] = kind
        if kind in ('prize_pack', 'stamped'):
            base = family.get(cid) or left_base.get(cid) or ''
            r['reprint_of'] = base if base != cid else ''
        if lang == 'ja':
            r['name_en'] = SCRAPED_TAIL.sub('', title or '').strip()
        if m is None and r.get('name_en') and r['name_en'] != r['name']:
            r['alt_name'] = r['name_en']
        rows[cid] = r
    Path(a.out).write_text(json.dumps({'rows': rows, 'ocr_totals': {'accepted': totals, 'evidence': evidence},
                                       'rules': __doc__.split('\n\n')[2]}, ensure_ascii=False) + '\n')
    print(json.dumps(dict(counts)), len(rows))


if __name__ == '__main__':
    main()
