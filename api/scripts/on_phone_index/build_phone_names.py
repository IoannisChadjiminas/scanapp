"""Japanese names for the phone index: fill Latin names and replace plainly wrong ones. Offline.

    python3 build_phone_names.py CATALOG_SQLITE SPECIES_JSON NAMES3_JSON IDS_TXT OUT_JSON

For every `ja:` row listed in IDS_TXT (the rows of the phone index), decides the `name` the phone
index carries; the catalogue itself is not changed. Rules, in order:

1. `held`: the row still has its English name and NAMES3 (docs/catalogue-names-families-20261114.md)
   matched a Japanese name for it but held it back from the server catalogue (the no-split rule and
   CP6 protect the server's printing tie-break, which the phone does not have). The held name must
   pass the species check below.
2. `species`: the row's name is Latin script, or Japanese script that fails the species check, and
   its English title (`view_title`) is one species from the server's species table
   (app/recognition/assets/ja_species_names.json: official names from Sun & Moon onward), with at
   most one prefix from PREFIX and one suffix from SUFFIX. The name is built from those parts.
3. `review`: a Japanese-script name that fails the species check and cannot be built by rule 2
   (owners, forms, Unown letters, delta species, tag teams, or a set outside TRANSLITERATED: there
   the English title may be the wrong side). The name is left as it is and listed.

Species check: build_species_names.py reduces the English title and the Japanese name to species;
the Japanese species must equal the table's (or contain it). Rows whose title is not a known species
(Trainers, Energies, unknown species) are not checked.

OUT_JSON: {"names": {id: {"name", "old", "rule"}}, "review": [...], "counts": {...}}.
"""
from __future__ import annotations

import collections
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ja_set_recovery'))
from build_species_names import MEGA, OWNER, en_species, ja_species  # noqa: E402

JAPANESE = re.compile(r'[぀-ヿ㐀-鿿ｦ-ﾟ]')
PREFIX = {'dark': 'わるい', 'shining': 'ひかる', 'radiant': 'かがやく', 'alolan': 'アローラ',
          'galarian': 'ガラル', 'hisuian': 'ヒスイ', 'paldean': 'パルデア'}
# Sets whose Japanese names came in part as machine transliterations (e-Card, neo, PCG, VS, web):
# only there is a Japanese-script name that fails the check replaced. Elsewhere it goes to review
# (the English title is as likely to be the wrong side, e.g. a tag team titled with one species).
TRANSLITERATED = re.compile(r'^ja:(E\d|neo\d|PCG\d|VS\d|web\d)-')
SUFFIX = {'ex': 'ex', 'EX': 'EX', 'GX': 'GX', 'V': 'V', 'VMAX': 'VMAX', 'VSTAR': 'VSTAR',
          'LV.X': 'LV.X', 'BREAK': 'BREAK'}


def build_name(title: str, species: dict[str, str]) -> str | None:
    """The Japanese name of a title made of [PREFIX] species [SUFFIX], or None."""
    t = unicodedata.normalize('NFKC', title or '').strip()
    if not t or re.search(r"[\[\](){}&/'’]|δ|☆", t):
        return None
    words = t.split()
    prefix = suffix = ''
    if len(words) > 1 and words[0].lower() in PREFIX:
        prefix = PREFIX[words.pop(0).lower()]
    if len(words) > 1 and words[-1] in SUFFIX:
        suffix = SUFFIX[words.pop()]
    ja = species.get(' '.join(words).lower())
    return f'{prefix}{ja}{suffix}' if ja else None


def species_ok(name: str, title: str, species: dict[str, str]) -> bool | None:
    """True/False when the title is a known species, None when it cannot be checked."""
    en = en_species(title or '')
    if not en or en not in species:
        return None
    ja = ja_species(name, mega=bool(MEGA.match(title.strip())), owner=bool(OWNER.match(title.strip())))
    return bool(ja) and (ja == species[en] or species[en] in ja)


def main(catalog, species_json, names3_json, ids_txt, out_json):
    species = json.loads(Path(species_json).read_text())['species']
    names3 = json.loads(Path(names3_json).read_text())
    held_ids = set(names3['held_cp6']) | set(names3['held_split'])
    held = {r['id']: r for r in names3['review'] if r['id'] in held_ids}
    ids = [i for i in Path(ids_txt).read_text().split() if i.startswith('ja:')]
    with sqlite3.connect(f'{Path(catalog).resolve().as_uri()}?mode=ro', uri=True) as db:
        cards = {r[0]: r for r in db.execute(
            "SELECT id, name, view_title, category FROM cards WHERE language='ja'")}
    out, review, counts = {}, [], collections.Counter()
    for cid in ids:
        _, name, title, category = cards[cid]
        name, title = name or '', title or ''
        if not JAPANESE.search(name):
            h = held.get(cid)
            if h and h['en'] == name and species_ok(h['name_ja'], title, species) is not False:
                out[cid] = {'name': h['name_ja'], 'old': name, 'rule': 'held', 'source': h.get('limitless')}
                counts['held'] += 1
                continue
            built = build_name(title, species) if category in (None, '', 'Pokemon') else None
            if built:
                out[cid] = {'name': built, 'old': name, 'rule': 'species'}
                counts['species_fill'] += 1
            else:
                counts['latin_kept'] += 1
            continue
        ok = species_ok(name, title, species)
        if ok is None:
            counts['not_checkable'] += 1
        elif ok:
            counts['checked_ok'] += 1
        else:
            built = build_name(title, species)
            if (built and built != name and TRANSLITERATED.match(cid)
                    and not re.search(r'[&＆（(]|デルタ', name)):
                out[cid] = {'name': built, 'old': name, 'rule': 'species_fix'}
                counts['species_fix'] += 1
            else:
                review.append({'id': cid, 'name': name, 'title': title,
                               'species': species.get(en_species(title) or '')})
                counts['wrong_kept_for_review'] += 1
    Path(out_json).write_text(json.dumps({'names': out, 'review': review, 'counts': dict(counts),
                                          'rule_doc': __doc__.split('\n\n')[1]},
                                         ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(dict(counts)))


if __name__ == '__main__':
    main(*sys.argv[1:6])
