import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts/on_phone_index'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extend = load('extend_index')
names = load('build_phone_names')
columns = load('phone_columns')

SPECIES = {'houndoom': 'ヘルガー', 'weezing': 'マタドガス', 'charizard': 'リザードン', 'melmetal': 'メルメタル'}


def base_release(tmp_path):
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'card_index.ids.txt').write_text('ja:a\nen:b\n')
    (base / 'card_index.meta.tsv').write_text(
        '#id\tname\tnumber\tprinted_number\tset_total\tlanguage\tpromo_code\trow_kind\talt_name\tprinting_family\n'
        'ja:a\tHoundoom\t44\t\t\tja\t\t\t\t\n'
        'en:b\tBeta\t2\t02\t100\ten\t\t\t\t\n')
    vectors = np.zeros((2, 384), dtype='<f2')
    vectors[0, 0] = vectors[1, 1] = 1
    (base / 'card_index.f16.bin').write_bytes(vectors.tobytes())
    files = {n: {'bytes': (base / n).stat().st_size, 'sha256': extend.digest(base / n)} for n in extend.FILES}
    (base / 'card_index.version.json').write_text(json.dumps(
        {'version': 'v1', 'rows': 2, 'files': files, 'model_id': 'm', 'dims': 384, 'catalogue_version': 'c',
         'source_ids_sha256': 'i', 'source_embeddings_sha256': 'e'}))
    return base


def test_extend_keeps_rows_and_appends(tmp_path):
    base = base_release(tmp_path)
    added = np.zeros((1, 384), dtype=np.float32)
    added[0, 2] = 1
    cols = {'rows': {
        'ja:a': {'name': 'ヘルガー', 'name_en': 'Houndoom', 'set_total': '57', 'release_year': '2000', 'hp': '70',
                 'printing': 'regular'},
        'en:b': {'release_year': '2019', 'printing': 'promo'},
        'ja:c': {'name': 'ブラッキーV', 'number': '047', 'set_total': '69', 'language': 'ja',
                 'alt_name': 'Umbreon V', 'name_en': 'Umbreon V', 'printing': 'regular'}}}
    target = extend.extend(base, cols, tmp_path / 'out', ['ja:c'], added)
    lines = (target / 'card_index.meta.tsv').read_text().splitlines()
    assert lines[0].split('\t')[:6] == ['#id', 'name', 'number', 'printed_number', 'set_total', 'language']
    assert lines[0].split('\t')[10:] == list(extend.NEW_COLUMNS)
    assert lines[1].split('\t') == ['ja:a', 'ヘルガー', '44', '', '57', 'ja', '', '', 'Houndoom', '',
                                    '2000', '70', 'regular', '', 'Houndoom']
    assert lines[2].split('\t')[:10] == ['en:b', 'Beta', '2', '02', '100', 'en', '', '', '', '']
    assert lines[3].split('\t')[:6] == ['ja:c', 'ブラッキーV', '047', '', '69', 'ja']
    assert (target / 'card_index.ids.txt').read_text() == 'ja:a\nen:b\nja:c\n'
    bin_ = (target / 'card_index.f16.bin').read_bytes()
    assert bin_[:2 * 384 * 2] == (base / 'card_index.f16.bin').read_bytes()
    assert np.frombuffer(bin_, dtype='<f2').reshape(3, 384)[2, 2] == 1
    version = json.loads((target / 'card_index.version.json').read_text())
    assert version['rows'] == 3 and version['extends']['version'] == 'v1' and target.name == version['version']
    assert version['extends']['names_changed'] == 1 and version['extends']['totals_filled'] == 1


def test_extend_refuses_changed_base_and_existing_totals(tmp_path):
    base = base_release(tmp_path)
    with pytest.raises(AssertionError):
        extend.extend(base, {'rows': {'en:b': {'set_total': '99'}}}, tmp_path / 'out', [], None)
    (base / 'card_index.ids.txt').write_text('ja:a\nen:x\n')
    with pytest.raises(AssertionError):
        extend.extend(base, {'rows': {}}, tmp_path / 'out', [], None)


def test_build_name_and_species_check():
    assert names.build_name('Houndoom', SPECIES) == 'ヘルガー'
    assert names.build_name('Dark Charizard', SPECIES) == 'わるいリザードン'
    assert names.build_name('Charizard ex', SPECIES) == 'リザードンex'
    assert names.build_name("Rocket's Weezing", SPECIES) is None
    assert names.build_name('Unown [Y]', SPECIES) is None
    assert names.species_ok('猟犬', 'Houndoom', SPECIES) is False
    assert names.species_ok('ヘルガー', 'Houndoom', SPECIES) is True
    assert names.species_ok('ふしぎなアメ', 'Rare Candy', SPECIES) is None
    assert names.TRANSLITERATED.match('ja:neo3-044') and not names.TRANSLITERATED.match('ja:SM12a-184')


def test_ocr_totals_need_two_agreeing_reads(tmp_path):
    reads = tmp_path / 'reads.jsonl'
    reads.write_text('\n'.join(json.dumps(r) for r in [
        {'set': 'A', 'id': 'ja:A-1', 'number': '1', 'fractions': [[1, 70]]},
        {'set': 'A', 'id': 'ja:A-2', 'number': '002', 'fractions': [[2, 70], [5, 80]]},
        {'set': 'B', 'id': 'ja:B-1', 'number': '1', 'fractions': [[1, 30]]},
        {'set': 'C', 'id': 'ja:C-1', 'number': '1', 'fractions': [[1, 30]]},
        {'set': 'C', 'id': 'ja:C-2', 'number': '2', 'fractions': [[2, 31]]},
        {'set': 'C', 'id': 'ja:C-3', 'number': '3', 'fractions': [[3, 30]]},
        {'set': 'D', 'id': 'ja:D-1', 'number': '1', 'fractions': [[7, 40]]},
        {'set': 'D', 'id': 'ja:D-2', 'number': '2', 'fractions': [[9, 40]]}]) + '\n')
    accepted, _ = columns.accepted_totals(reads)
    assert accepted == {'A': 70}


def test_year():
    assert columns.year('2021-05-28') == '2021'
    assert columns.year('1999/01/09') == '1999'
    assert columns.year('17 Dec 10') == '2010'
    assert columns.year(None) == ''
