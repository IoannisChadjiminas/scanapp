"""Extend an exported phone index: append rows and meta columns, apply reviewed name and total fixes.

    python3 extend_index.py --base RELEASE_DIR --columns COLUMNS_JSON --out OUT_DIR \
        [--add-ids IDS_TXT --add-vectors EMBEDDINGS_NPY] [--note TEXT]

RELEASE_DIR is a release written by export_index.py (checked against its version file). The result is
a new release folder named by its version hash; RELEASE_DIR is never changed.

- Existing rows keep their order, ids and float16 vectors byte for byte. Added rows go at the end,
  in IDS_TXT order, with their float32 vectors (normalized, 384 dims) written as float16.
- Existing meta columns keep their positions. NEW_COLUMNS are appended after them. Old app builds
  read the first six columns and ignore the rest.
- COLUMNS_JSON: {"rows": {id: {...}}, "prints": {id: {...}}}. Each row may carry NEW_COLUMNS values and
  the overrides `name`, `set_total` and `promo_code` (the only existing columns this script changes;
  `set_total` and `promo_code` only where empty). An added row must carry
  all six base columns (`name`, `number`, `printed_number`, `set_total`, `language`) and may carry
  `promo_code`, `row_kind`, `alt_name`, `printing_family`.
  `alt_name` follows `name`: when a name changes, alt_name becomes the old English title (`name_en`)
  if it differs from the new name.
- "prints" (optional) becomes card_index.prints.tsv: printing alternatives with no vector (same art as
  an indexed card), one row each with PRINTS_COLUMNS, for the phone to choose within a family by text.
  Its ids must not be index rows. It is hashed in the version file like the other files.
- card_index.version.json records the base version, the rows added, the columns and the counts of
  changed names and totals; its `version` is the sha256 of the identity, as in export_index.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

DIMENSIONS = 384
NEW_COLUMNS = ('release_year', 'hp', 'printing', 'reprint_of', 'name_en', 'set_code')
PRINTS_COLUMNS = ('reprint_of', 'printing', 'number', 'printed_number', 'set_total', 'set_code', 'promo_code',
                  'release_year')
PRINTS_FILE = 'card_index.prints.tsv'
PRINTINGS = {'', 'regular', 'promo', 'prize_pack', 'stamped', 'other'}
FILES = ('card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def clean(value) -> str:
    return ' '.join(str(value if value is not None else '').replace('\t', ' ').split())


def check_value(column: str, value: str, card_id: str) -> None:
    if column == 'release_year':
        assert value == '' or (len(value) == 4 and value.isdigit() and 1996 <= int(value) <= 2030), (card_id, value)
    elif column == 'hp':
        assert value == '' or (value.isdigit() and 0 < int(value) < 1000), (card_id, value)
    elif column == 'printing':
        assert value in PRINTINGS, (card_id, value)


def extend(base: Path, columns: dict, out: Path, add_ids: list[str], add_vectors: np.ndarray | None,
           note: str = '') -> Path:
    version = json.loads((base / 'card_index.version.json').read_text())
    for name in FILES:
        assert digest(base / name) == version['files'][name]['sha256'], name
    ids = (base / 'card_index.ids.txt').read_text().split('\n')[:-1]
    lines = (base / 'card_index.meta.tsv').read_text().split('\n')[:-1]
    header, meta = lines[0].lstrip('#').split('\t'), [line.split('\t') for line in lines[1:]]
    assert header[:6] == ['id', 'name', 'number', 'printed_number', 'set_total', 'language'], header
    assert not set(NEW_COLUMNS) & set(header), header
    assert [m[0] for m in meta] == ids and len(ids) == version['rows'] and len(set(ids)) == len(ids)
    rows = columns['rows']
    assert not set(add_ids) & set(ids) and len(set(add_ids)) == len(add_ids)
    pos = {c: header.index(c) for c in header}
    renamed = retotalled = recoded = 0
    out_rows = []
    for m in meta:
        r = rows.get(m[0], {})
        m = list(m) + [''] * (len(header) - len(m))
        if 'name' in r and r['name'] != m[1]:
            m[1] = clean(r['name'])
            renamed += 1
            if 'alt_name' in pos:
                en = clean(r.get('name_en', ''))
                m[pos['alt_name']] = en if en and en != m[1] else ''
        if 'set_total' in r and str(r['set_total']) != m[4]:
            assert m[4] == '' and str(r['set_total']).isdigit(), (m[0], m[4], r['set_total'])
            m[4] = str(r['set_total'])
            retotalled += 1
        if 'promo_code' in pos and r.get('promo_code') and r['promo_code'] != m[pos['promo_code']]:
            assert m[pos['promo_code']] == '', (m[0], m[pos['promo_code']], r['promo_code'])
            m[pos['promo_code']] = clean(r['promo_code'])
            recoded += 1
        out_rows.append(m)
    for card_id in add_ids:
        r = rows[card_id]
        m = [card_id] + [clean(r.get(c, '')) for c in header[1:]]
        assert m[1] and m[5], card_id
        out_rows.append(m)
    for m in out_rows:
        r = rows.get(m[0], {})
        for c in NEW_COLUMNS:
            value = clean(r.get(c, ''))
            check_value(c, value, m[0])
            m.append(value)
    prints = columns.get('prints') or {}
    assert not set(prints) & (set(ids) | set(add_ids))
    for card_id, r in prints.items():
        check_value('printing', clean(r.get('printing', '')), card_id)
        check_value('release_year', clean(r.get('release_year', '')), card_id)
        assert not r.get('reprint_of') or r['reprint_of'] in set(ids) | set(add_ids), (card_id, r['reprint_of'])
    if add_ids:
        assert add_vectors is not None and add_vectors.shape == (len(add_ids), DIMENSIONS)
        assert np.isfinite(add_vectors).all() and np.max(np.abs(np.linalg.norm(add_vectors, axis=1) - 1)) < .01
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.phone-index-', dir=out))
    try:
        all_ids = ids + add_ids
        (tmp / 'card_index.ids.txt').write_text(''.join(c + '\n' for c in all_ids), encoding='utf-8')
        with (tmp / 'card_index.meta.tsv').open('w', encoding='utf-8', newline='\n') as f:
            f.write('#' + '\t'.join(header + list(NEW_COLUMNS)) + '\n')
            for m in out_rows:
                f.write('\t'.join(m) + '\n')
        names = FILES
        if prints:
            with (tmp / PRINTS_FILE).open('w', encoding='utf-8', newline='\n') as f:
                f.write('#' + '\t'.join(('id',) + PRINTS_COLUMNS) + '\n')
                for card_id in sorted(prints):
                    f.write('\t'.join([card_id] + [clean(prints[card_id].get(c, '')) for c in PRINTS_COLUMNS]) + '\n')
            names = FILES + (PRINTS_FILE,)
        shutil.copyfile(base / 'card_index.f16.bin', tmp / 'card_index.f16.bin')
        if add_ids:
            with (tmp / 'card_index.f16.bin').open('ab') as f:
                f.write(np.asarray(add_vectors, dtype='<f2').tobytes(order='C'))
        assert (tmp / 'card_index.f16.bin').stat().st_size == len(all_ids) * DIMENSIONS * 2
        files = {name: {'bytes': (tmp / name).stat().st_size, 'sha256': digest(tmp / name)} for name in names}
        identity = {k: version[k] for k in ('model_id', 'catalogue_version', 'dims', 'source_ids_sha256',
                                            'source_embeddings_sha256') if k in version}
        identity.update(rows=len(all_ids), files=files, meta_columns=header + list(NEW_COLUMNS),
                        extends={'version': version['version'], 'rows': len(ids), 'added_rows': len(add_ids),
                                 'added_ids': add_ids, 'names_changed': renamed, 'totals_filled': retotalled,
                                 'promo_codes_filled': recoded, 'prints_rows': len(prints), 'note': note})
        if 'subset' in version:
            identity['subset'] = version['subset']
        identity['version'] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        (tmp / 'card_index.version.json').write_text(json.dumps(identity, sort_keys=True, ensure_ascii=False) + '\n',
                                                     encoding='utf-8')
        destination = out / identity['version']
        assert not destination.exists(), destination
        os.rename(tmp, destination)
        return destination
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--columns', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--add-ids', type=Path)
    p.add_argument('--add-vectors', type=Path)
    p.add_argument('--note', default='')
    a = p.parse_args()
    add_ids = a.add_ids.read_text().split() if a.add_ids else []
    vectors = np.load(a.add_vectors).astype(np.float32) if a.add_vectors else None
    print(extend(a.base, json.loads(a.columns.read_text()), a.out, add_ids, vectors, a.note))


if __name__ == '__main__':
    main()
