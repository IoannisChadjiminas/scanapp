import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.local_match import LocalArtworkMatch
from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit, OcrResult, grading_label_line, pick_confident_name
from app.recognition.pipeline import recognize_bytes
from app.recognition.rank import extract_collector_candidates
from app.recognition.text_identity import name_agrees, name_tokens, text_identity_candidates


@pytest.mark.parametrize('text', ['PRISTINE', '10 PRISTINE', 'GEM MT 10', 'GEM MINT', 'MINT 9', 'PSA', 'BGS',
                                  'CGC', 'TAG', 'ACE', 'BECKETT', 'AUTHENTIC', 'Pi', '00044829', '#17 HOLO',
                                  '2023 POKEMON JP', 'Black Label', 'Hidden Fates - SV59/SV94'])
def test_grading_label_fields(text):
    assert grading_label_line(text)


@pytest.mark.parametrize('text', ['Tag Team', 'Pikachu', 'ルギアex', 'Porygon2', 'Ace Trainer', 'Mew', 'EX',
                                  'Mewtwo & Mew GX', 'Lugia V'])
def test_card_titles_are_not_label_fields(text):
    assert not grading_label_line(text)


def test_label_words_never_become_the_name_and_a_title_after_the_label_wins():
    # The Lugia slab screenshot: the title strip holds only the label's grade and logo.
    lines = ['十', 'X', '1/5', '10', 'Pi', 'PRISTINE']
    scores = [.84, .90, .999, .9999, .69, .9999]
    assert pick_confident_name(lines, scores) == 'PRISTINE'
    assert pick_confident_name(lines, scores, label_filter=True) is None
    # A stage badge after the label marks the card's own title.
    label = ['10', 'PRISTINE', '2023 POKEMON JP', '#17 HOLO', '00044829', 'たね', 'ルギアex', '230']
    assert pick_confident_name(label, [.99]*8, label_filter=True) == 'ルギアex'
    psa = ['PSA', 'GEM MT 10', 'Charizard', '2016 POKEMON EVOLUTIONS', '12345678']
    assert pick_confident_name(psa, [.99]*5, label_filter=True) == 'Charizard'
    # PSA prints the grade word mid-label (panel photo fresh100_277613285848): the label's
    # card name stays, never the product line after the grade.
    mew = ['2023 POKEMON SVP EN', '#053', 'MEW ex', 'NM-MT', '151 ULTRA-PREMIUM COLL', '8', 'FSA']
    assert pick_confident_name(mew, [.99]*7, label_filter=True) == pick_confident_name(mew, [.99]*7) == 'MEW ex'
    # CGC slab (panel photo fresh100_177390016065): the set line after the dated header is a
    # label field too, so the name stays the old harmless 'GC' rather than a conflicting set name.
    cgc = ['GC', 'UNIVERSAL', 'GRA', 'Mewtwo GX', 'ristine', 'Pokémon (2019)', 'Hidden Eates - SV59/SV94', 'X', '00']
    assert pick_confident_name(cgc, [.99]*9, label_filter=True) == pick_confident_name(cgc, [.99]*9) == 'GC'
    # Raw cards are unchanged.
    raw = ['BASIC', 'Pikachu', 'HP 60']
    assert pick_confident_name(raw, [.99]*3, label_filter=True) == pick_confident_name(raw, [.99]*3) == 'Pikachu'


def test_name_tokens_drop_hp_labels_and_weak_reads():
    hits = [OcrHit('PRISTINE', .99, 'name'), OcrHit('アルセウス280', .99, 'collector'),
            OcrHit('ルギア', .85, 'collector'), OcrHit('230', .99, 'collector'), OcrHit('ギラティナ', .5, 'collector')]
    assert name_tokens(hits) == ['アルセウス', 'ルギア']
    assert name_agrees(['ルギア'], 'ルギアex')
    assert name_agrees(['lugiaex'], 'ルギアex', 'Lugia ex')
    assert not name_agrees(['ルギア'], 'ニャオニクス', 'Meowstic')
    assert not name_agrees(['アルセウス'], 'ルギアex')


def catalogue(tmp_path, extra=()):
    catalog = connect(tmp_path/'catalog.sqlite')
    init_catalog(catalog)
    rows = [('ja:CLF-017', 'ルギアex', 'CLF', '017', 'ja', '017/032', 'Lugia ex'),
            ('ja:CP3-017', 'ニャオニクス', 'CP3', '017', 'ja', '017/032', 'Meowstic'),
            # Unknown set total: a bare 017 must not count as 017/032.
            ('ja:SM7b-017', 'ギラティナ', 'SM7b', '017', 'ja', None, 'Giratina'),
            ('en:sv1-17', 'Lugia', 'sv1', '17', 'en', '017/032', 'Lugia'),
            *extra]
    for cid, name, set_id, number, language, printed, title in rows:
        catalog.execute('INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,'
                        'printed_collector_number,view_title,image_path) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (cid, cid, name, set_id, set_id, number, language, printed, title, f'/refs/{cid}.jpg'))
    catalog.commit()
    return catalog


def test_number_and_name_narrow_the_catalogue(tmp_path):
    catalog = catalogue(tmp_path)
    ids = {r[0] for r in catalog.execute('SELECT id FROM cards')}
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=ids)
    number = [OcrHit('017/032', .99997, 'collector')]
    hits = [OcrHit('PRISTINE', .9999, 'name'), *number, OcrHit('ギラティナ', .90, 'collector'),
            OcrHit('ルギア', .85, 'collector')]
    found, reason = text_identity_candidates(index, catalog, hits=hits, numbers=number, languages=('ja',))
    assert (found, reason) == (['ja:CLF-017'], 'candidates')
    # A Japanese read never matches an English-only name; a Latin read reaches both.
    assert text_identity_candidates(index, catalog, hits=hits, numbers=number, languages=())[0] == ['ja:CLF-017']
    latin = [*number, OcrHit('LUGIA', .95, 'name')]
    assert text_identity_candidates(index, catalog, hits=latin, numbers=number, languages=())[0] == [
        'en:sv1-17', 'ja:CLF-017']
    assert text_identity_candidates(index, catalog, hits=hits[:2], numbers=number,
                                    languages=('ja',)) == ([], 'no_name_token')
    weak = [OcrHit('017/032', .80, 'collector')]
    assert text_identity_candidates(index, catalog, hits=hits, numbers=weak,
                                    languages=('ja',)) == ([], 'no_confident_fraction')
    two = [*number, OcrHit('018/032', .99, 'collector')]
    assert text_identity_candidates(index, catalog, hits=hits, numbers=two,
                                    languages=('ja',)) == ([], 'conflicting_fractions')


def test_more_than_three_named_cards_is_too_broad(tmp_path):
    extra = [(f'ja:X{i}-017', 'ルギアex', f'X{i}', '017', 'ja', '017/032', 'Lugia ex') for i in range(3)]
    catalog = catalogue(tmp_path, extra)
    ids = {r[0] for r in catalog.execute('SELECT id FROM cards')}
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=ids)
    number = [OcrHit('017/032', .99, 'collector')]
    assert text_identity_candidates(index, catalog, hits=[OcrHit('ルギア', .9, 'collector')], numbers=number,
                                    languages=('ja',)) == ([], 'too_many_candidates')


def scan(tmp_path, monkeypatch, *, enabled, verify_aligned=True, lead_score=.73, name='PRISTINE'):
    """One slab-screenshot scan through the real pipeline with a faked OCR and verifier."""
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify', lambda im: (im, False))
    for name_ in ('card_frame_candidates', 'loose_frame_candidates', 'portrait_window_candidates'):
        monkeypatch.setattr(f'app.recognition.pipeline.{name_}', lambda *a, **k: [])
    monkeypatch.setattr('app.recognition.pipeline.slab_interior_candidate', lambda *a, **k: None)
    boundary = []
    monkeypatch.setattr('app.recognition.pipeline.line_frame_candidates',
                        lambda *a, **k: boundary.append(1) or [])
    catalog, results = catalogue(tmp_path), connect(tmp_path/'results.sqlite')
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    wrong = [f'ja:W{i}-054' for i in range(20)]
    for cid in wrong:
        catalog.execute('INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,'
                        'printed_collector_number,image_path) VALUES (?,?,?,?,?,?,?,?,?)',
                        (cid, cid, 'オーロンゲ', cid, cid, '054', 'ja', '054/070', f'/refs/{cid}.jpg'))
    catalog.commit()
    ids = [*wrong, 'ja:CLF-017', 'ja:CP3-017', 'ja:SM7b-017', 'en:sv1-17']
    scores = [lead_score - .001*i for i in range(20)] + [.60, .55, .69, .5]
    snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
        [[s, np.sqrt(1-s*s)] for s in scores], dtype=np.float32))
    observed = OcrResult(name_text=name if not enabled else None, collector_text='017/032',
        lines=['10', 'Pi', 'PRISTINE', '017/032', 'ギラティナ', 'ルギア', '230'],
        hits=[OcrHit('10', .9999, 'name'), OcrHit('Pi', .69, 'name'), OcrHit('PRISTINE', .9999, 'name'),
              OcrHit('017/032', .99997, 'collector'), OcrHit('ギラティナ', .90, 'collector'),
              OcrHit('ルギア', .85, 'collector'), OcrHit('230', .9999, 'collector')])
    aligned = Image.new('RGB', (600, 825))
    def verify(image, references):
        return ([LocalArtworkMatch('ja:CLF-017', 28, 28, .33)]
                if verify_aligned and image is aligned and any(c == 'ja:CLF-017' for c, _ in references) else [])
    runtime = SimpleNamespace(require=lambda: (snapshot,
        SimpleNamespace(embed=lambda *args: np.array([1, 0], dtype=np.float32)), SimpleNamespace(read=lambda image: observed)),
        card_languages=np.array([i.split(':')[0] for i in ids]), printing_index=None,
        artwork_verifier=SimpleNamespace(verify=verify, propose_frame=lambda image, reference: aligned),
        metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=set(ids)),
        versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
        threshold_config=lambda: {})
    payload = io.BytesIO()
    Image.fromarray(np.random.default_rng(7).integers(0, 255, (1990, 1180, 3), dtype=np.uint8)).save(payload, 'JPEG')
    try:
        response = recognize_bytes(payload.getvalue(), settings=Settings(_env_file=None, data_dir=tmp_path,
            store_captures=False, text_identity_candidates=enabled, ocr_label_name_filter=enabled),
            runtime=runtime, catalog=catalog, results=results, session_id='test', graded=False)
        evidence = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
        return response, evidence, bool(boundary)
    finally:
        catalog.close()
        results.close()


def test_flags_off_keep_the_retake(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=False)
    assert response.status == 'retake' and not response.suggestions
    assert 'text_identity' not in evidence and boundary


def test_verified_number_and_name_candidate_answers_without_boundary_retry(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=True)
    assert response.status == 'uncertain' and response.confidence.requires_confirmation
    assert [s.card_id for s in response.suggestions] == ['ja:CLF-017']
    assert evidence['text_identity']['candidate_ids'] == ['ja:CLF-017']
    assert evidence['text_identity']['outcome'] == 'verified'
    assert evidence['text_identity']['aligned_verified'] == ['ja:CLF-017']
    assert not boundary


def test_unverified_candidates_are_suggestions_needing_confirmation(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=True, verify_aligned=False)
    assert response.status == 'uncertain' and response.confidence.requires_confirmation
    assert [s.card_id for s in response.suggestions] == ['ja:CLF-017']
    assert evidence['text_identity']['outcome'] == 'unverified'
    assert 'text_identity_unverified' in evidence['status_reasons']
    # Without verification the boundary retry still looks for a better frame.
    assert boundary


def test_text_never_overrides_a_strong_visual_leader(tmp_path, monkeypatch):
    response, evidence, _ = scan(tmp_path, monkeypatch, enabled=True, lead_score=.90)
    assert evidence['text_identity']['candidate_ids'] == []
    assert all(s.card_id != 'ja:CLF-017' for s in response.suggestions)


FIXTURE = Path(__file__).parent / 'fixtures' / 'text_identity_cases.jsonl'
CASES = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_recorded_failures_name_and_narrow_to_the_right_card(tmp_path, case):
    """Recorded OCR of real failures, replayed against their true catalogue neighbours."""
    catalog = connect(tmp_path/'catalog.sqlite')
    init_catalog(catalog)
    for row in case['catalogue_rows']:
        catalog.execute(f"INSERT INTO cards ({','.join(row)},provider_id) VALUES ({','.join('?'*len(row))},?)",
                        [*row.values(), row['id']])
    for key, total in case['set_totals'].items():
        language, set_id = key.split(':', 1)
        catalog.execute('INSERT INTO set_totals VALUES (?,?,?,?)', (language, set_id, total, 'fixture'))
    catalog.commit()
    hits = [OcrHit(h['text'], h['confidence'], h['region']) for h in case['hits']]
    names = [h for h in hits if h.region == 'name']
    name = pick_confident_name([h.text for h in names], [h.confidence for h in names], label_filter=True)
    assert name is None or not grading_label_line(name)
    assert pick_confident_name([h.text for h in names], [h.confidence for h in names]) == case['before']['name_text']
    numbers = extract_collector_candidates([h.text for h in hits], hits=hits)
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'),
                                   indexed_ids={r['id'] for r in case['catalogue_rows']})
    found, reason = text_identity_candidates(index, catalog, hits=hits, numbers=numbers,
                                             languages=tuple(case['languages']))
    assert reason == 'candidates' and 1 <= len(found) <= 3
    assert set(case['expected_card_ids']) & set(found)
    catalog.close()
