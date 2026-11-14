"""Export a verified server snapshot to an immutable phone index directory.

Use a snapshot exported by export_cloud_snapshot.py when the server uses the
cloud catalogue. Supply the matching operational SQLite database for set totals.
The output is an offline candidate; do not publish it until the parity gate and
device tests in the shipping plan pass.

card_index.meta.tsv columns: id, name, number, printed_number, set_total, language,
promo_code, row_kind. The app reads the first six and ignores the rest. set_total is the
total printed on the card when printed_number (or number) carries a fraction, else the
operational total; Japanese promo rows carry their code ("SV-P") in promo_code and no total.
row_kind is app.phone_index_subset's kind (digital, language, duplicate, reference or empty).

The build fails when a row breaks a check (CHECKS: an id without a language prefix, a ja row
without a Japanese name, a printed fraction without a total or code, a digital set) unless the
row is listed in --allow-exceptions. --exclude leaves out rows by kind (the subset rule).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

import numpy as np

MODEL_ID = '2ddf6ec79e37'
DIMENSIONS = 384
HEADER = '#id\tname\tnumber\tprinted_number\tset_total\tlanguage\tpromo_code\trow_kind\n'

# Loaded by path so the exporter also runs from a copied folder (api/app/phone_index_subset.py).
_spec = importlib.util.spec_from_file_location(
    'phone_index_subset', Path(__file__).resolve().parents[2] / 'app' / 'phone_index_subset.py')
subset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(subset)

# Japanese promo sets print their code where a set prints its total ("001/SV-P"). The count of
# cards in such a set is not printed on any card, so these rows carry the code and no total.
JA_PROMO_CODES = {'SV-P': 'SV-P', 'M-P': 'M-P', 'SP': 'S-P', 'SMP': 'SM-P', 'XYP': 'XY-P',
                  'BWP': 'BW-P', 'DPtP': 'DPt-P', 'DPP': 'DP-P', 'LP': 'L-P'}
_FRACTION = re.compile(r'^[^/]+/\s*([A-Za-z]*)0*(\d+)\s*$')
_PROMO_FRACTION = re.compile(r'^[^/]+/\s*([A-Za-z]+(?:-[A-Za-z]+)*-P)\s*$')
# Kana, CJK ideographs, half-width katakana: a Japanese name has at least one.
_JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]')
CHECKS = ('unprefixed_id', 'latin_name_ja', 'missing_total', 'digital_set')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def clean(value: object) -> str:
    text = '' if value is None else str(value)
    if any(c in text for c in '\t\r\n'):
        raise ValueError('Catalogue field contains a tab or newline')
    return text


def printed_identity(printed: str) -> tuple[str, str]:
    """(set_total, promo_code) as the printed number shows them: "006/163" is ("163", ""),
    "TG01/TG30" is ("30", "") as the app reads it, "002/S-P" is ("", "S-P")."""
    if match := _FRACTION.match(printed or ''):
        return str(int(match.group(2))), ''
    if match := _PROMO_FRACTION.match(printed or ''):
        return '', match.group(1)
    return '', ''


def row_identity(number: str, printed: str, language: str, set_id: str,
                 catalogue_total: object) -> tuple[str, str]:
    """The row's set_total and promo_code. A fraction printed on the card wins over the set
    total from the operational database (the app compares totals with what the photo shows);
    a Japanese promo row carries its code and no total; otherwise the database total."""
    total, code = printed_identity(printed)
    if not (total or code) and '/' in (number or ''):
        total, code = printed_identity(number)
    if total or code:
        return total, code
    code = JA_PROMO_CODES.get(set_id.split(':')[-1]) if language == 'ja' else None
    if code:
        return '', code
    return ('' if catalogue_total is None else str(catalogue_total)), ''


def check_rows(rows: list[tuple[str, ...]]) -> dict[str, list[str]]:
    """Rows that break a build rule, by rule. A row is (id, name, number, printed_number,
    set_total, language, promo_code, row_kind)."""
    found = {name: [] for name in CHECKS}
    for card_id, name, number, printed, total, language, code, kind in rows:
        if ':' not in card_id:
            found['unprefixed_id'].append(card_id)
        if (language == 'ja' or card_id.startswith('ja:')) and not _JAPANESE.search(name):
            found['latin_name_ja'].append(card_id)
        if not total and not code and ('/' in printed or '/' in number):
            found['missing_total'].append(card_id)
        if kind == 'digital':
            found['digital_set'].append(card_id)
    return found


def check_failures(found: dict[str, list[str]], allowed: dict[str, list[str]]) -> dict[str, list[str]]:
    """The rows not covered by the recorded exceptions; any one fails the build."""
    return {name: sorted(set(ids) - set(allowed.get(name, ()))) for name, ids in found.items()
            if set(ids) - set(allowed.get(name, ()))}


def export(snapshot_dir: Path, catalogue: Path, totals_db: Path, model: Path, out: Path,
           *, exclude: tuple[str, ...] = (), allowed: dict[str, list[str]] | None = None,
           report: Path | None = None) -> Path:
    manifest = json.loads((snapshot_dir / 'manifest.json').read_text())
    if manifest.get('preprocess_config') != 'pad' or manifest.get('embedding_dim') != DIMENSIONS:
        raise ValueError('Expected a 384-dimensional pad snapshot')
    model_hash = digest(model)
    if manifest.get('dinov2_sha256') != model_hash or not model_hash.startswith(MODEL_ID):
        raise ValueError('Snapshot model does not match the phone model')
    emb_path = snapshot_dir / 'embeddings.npy'
    ids_path = snapshot_dir / 'embedding_card_ids.npy'
    for path, key in ((emb_path, 'embeddings_sha256'), (ids_path, 'ids_sha256')):
        if not manifest.get(key) or digest(path) != manifest[key]:
            raise ValueError(f'Snapshot checksum mismatch: {path.name}')
    vectors = np.load(emb_path, mmap_mode='r', allow_pickle=False)
    ids = np.load(ids_path, allow_pickle=False).astype(str).tolist()
    if (vectors.dtype != np.float32 or vectors.shape != (len(ids), DIMENSIONS)
            or not ids or len(set(ids)) != len(ids) or manifest.get('indexed_count') != len(ids)):
        raise ValueError('Invalid snapshot shape, rows, or ids')
    if manifest.get('indexed_ids') is not None and manifest['indexed_ids'] != ids:
        raise ValueError('Snapshot ids do not match the manifest order')
    for start in range(0, len(ids), 8192):
        chunk = np.asarray(vectors[start:start + 8192])
        if not np.isfinite(chunk).all() or np.max(np.abs(np.linalg.norm(chunk, axis=1) - 1)) > .01:
            raise ValueError('Snapshot vectors are not finite and normalized')
    with sqlite3.connect(f'{catalogue.resolve().as_uri()}?mode=ro', uri=True) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(cards)')}
        printed = 'printed_collector_number' if 'printed_collector_number' in columns else "''"
        cards = {row[0]: row for row in db.execute(
            f'SELECT id, name, collector_number, {printed}, language, set_id FROM cards')}
    with sqlite3.connect(f'{totals_db.resolve().as_uri()}?mode=ro', uri=True) as db:
        totals = {(str(lang).casefold(), str(set_id).split(':')[-1].casefold()): total
                  for lang, set_id, total in db.execute(
                      'SELECT language, set_id, official_total FROM set_totals')}
    if not totals:
        raise ValueError('Set totals are empty; provide the server operational database')
    if any(card_id not in cards for card_id in ids):
        raise ValueError('Snapshot contains ids absent from the catalogue')
    if not manifest.get('catalogue_version'):
        raise ValueError('Snapshot has no catalogue version')
    excluded = subset.normalize_excluded(exclude)
    kept = subset.subset_ids(ids, excluded)
    kinds = dict(zip(ids, subset.row_kinds(ids)))
    rows = []
    for card_id in kept:
        _, name, number, printed_number, lang, set_id = (clean(v) for v in cards[card_id])
        catalogue_total = totals.get((str(lang or 'en').casefold(), set_id.split(':')[-1].casefold()))
        total, code = row_identity(number, printed_number, lang, set_id, catalogue_total)
        rows.append((clean(card_id), name, number, printed_number, total, lang, code, kinds[card_id]))
    found = check_rows(rows)
    failures = check_failures(found, allowed or {})
    if report is not None:
        report.write_text(json.dumps({'counts': {k: len(v) for k, v in found.items()},
                                      'not_allowed': {k: len(v) for k, v in failures.items()},
                                      'rows': found}, indent=1, sort_keys=True) + '\n')
    if failures:
        raise ValueError('Export checks failed: ' + ', '.join(
            f'{name} {len(bad)} (first {bad[0]})' for name, bad in failures.items()))
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.phone-index-', dir=out))
    try:
        (tmp / 'card_index.ids.txt').write_text(''.join(row[0] + '\n' for row in rows), encoding='utf-8')
        with (tmp / 'card_index.meta.tsv').open('w', encoding='utf-8', newline='\n') as f:
            f.write(HEADER)
            for row in rows:
                f.write('\t'.join(row) + '\n')
        keep = set(kept)
        positions = np.asarray([i for i, card_id in enumerate(ids) if card_id in keep]) if excluded else None
        with (tmp / 'card_index.f16.bin').open('wb') as f:
            for start in range(0, len(kept), 8192):
                block = (vectors[start:start + 8192] if positions is None
                         else vectors[positions[start:start + 8192]])
                f.write(np.asarray(block, dtype='<f2').tobytes(order='C'))
        names = ('card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv')
        files = {name: {'bytes': (tmp / name).stat().st_size, 'sha256': digest(tmp / name)} for name in names}
        identity = {'model_id': MODEL_ID, 'catalogue_version': str(manifest['catalogue_version']),
                    'rows': len(kept), 'dims': DIMENSIONS, 'files': files,
                    'source_ids_sha256': manifest['ids_sha256'],
                    'source_embeddings_sha256': manifest['embeddings_sha256']}
        if excluded:
            identity['subset'] = {'rule': subset.RULE, 'excluded': list(excluded), 'source_rows': len(ids)}
        version = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        identity['version'] = version
        (tmp / 'card_index.version.json').write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
        destination = out / version
        if destination.exists():
            if any(not (destination / name).is_file() or digest(destination / name) != digest(tmp / name)
                   for name in (*names, 'card_index.version.json')):
                raise ValueError('Existing version directory differs from the candidate')
            shutil.rmtree(tmp)
        else:
            os.rename(tmp, destination)
        return destination
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot-dir', type=Path, required=True)
    p.add_argument('--catalogue', type=Path, required=True)
    p.add_argument('--totals-db', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exclude', default='', help=f'row kinds to leave out, comma-separated, of {subset.EXCLUDABLE}; '
                   'a subset index is served only by a server that knows the subset rule')
    p.add_argument('--allow-exceptions', type=Path,
                   help='JSON {check: [ids]} of known rows each check lets through; any other row fails the build')
    p.add_argument('--report', type=Path, help='write the check results (counts and ids) here')
    a = p.parse_args()
    allowed = json.loads(a.allow_exceptions.read_text()) if a.allow_exceptions else {}
    print(export(a.snapshot_dir, a.catalogue, a.totals_db, a.model, a.out,
                 exclude=tuple(x for x in a.exclude.split(',') if x), allowed=allowed, report=a.report))


if __name__ == '__main__':
    main()
