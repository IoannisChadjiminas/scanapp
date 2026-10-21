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
from app.recognition.ocr import (OcrHit, OcrResult, grading_label_line, pick_collector_text, pick_confident_name,
                                 slab_label_field)
from app.recognition.label_identity import label_identity_candidates, number_key, parse_label
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


def scan(tmp_path, monkeypatch, *, enabled, verify_aligned=True, lead_score=.73, name='PRISTINE',
         slab_label=False, lead_name='オーロンゲ', screenshot=False, full_image=False, detected=False,
         holder=False, holder_region=False, recovery=False):
    """One slab-screenshot scan through the real pipeline with a faked OCR and verifier."""
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify', lambda im: (im, detected))
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
                        (cid, cid, lead_name, cid, cid, '054', 'ja', '054/070', f'/refs/{cid}.jpg'))
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
    reads = []
    if holder:
        # The holder-quad Lugia: the strips read the label and a misread footer.
        observed = OcrResult(name_text='CLASSIC COLLECTION', collector_text='017/012', lines=[],
            hits=[OcrHit(t, .99, 'holder_name') for t in
                  ('10', 'PRISTINE', '2023 POKÉMON JP', 'CLASSIC COLLECTION', 'LUGIA EX', '#17HOLO')]
                 + [OcrHit('017/012', .93, 'collector')])
        card = OcrResult(name_text='ルギア', collector_text=None, lines=['ルギア', '230'],
            hits=[OcrHit('ルギア', .998, 'name'), OcrHit('230*', .98, 'name'), OcrHit('×2', .8, 'collector')])
    if screenshot:
        # The app failure: the strips hold only the phone's status and browser bars.
        observed = OcrResult(name_text=None, collector_text='36', lines=['11:38', '1/5', '③ auctaro.com', '36'],
            hits=[OcrHit('11:38', .99, 'name'), OcrHit('1/5', .998, 'name'),
                  OcrHit('③ auctaro.com', .97, 'collector'), OcrHit('36', .9999, 'collector')])
    whole_reads = []
    def whole(patch):
        if holder:
            return (['10', 'PRISTINE', '2023 POKÉMON JP', 'CLASSIC COLLECTION', 'LUGIA EX', '#17HOLO', '00044829'],
                    [.99] * 7)
        whole_reads.append(patch.size)
        return (['11:38', '1/5', '10', 'PRISTINE', 'ルギア', '230*', '017/032', '③ auctaro.com'],
                [.99, .998, .9999, .9999, .998, .978, .995, .97])
    aligned = Image.new('RGB', (600, 825))
    def verify(image, references):
        return ([LocalArtworkMatch('ja:CLF-017', 28, 28, .33)]
                if verify_aligned and image is aligned and any(c == 'ja:CLF-017' for c, _ in references) else [])
    runtime = SimpleNamespace(require=lambda: (snapshot,
        SimpleNamespace(embed=lambda *args: np.array([1, 0], dtype=np.float32)),
        SimpleNamespace(read=lambda image: reads.append(image.size) or (card if holder and image.width < 700 else observed),
                        _run=whole)),
        card_languages=np.array([i.split(':')[0] for i in ids]), printing_index=None,
        artwork_verifier=SimpleNamespace(verify=verify, propose_frame=lambda image, reference: aligned),
        metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=set(ids)),
        versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
        threshold_config=lambda: {})
    payload = io.BytesIO()
    Image.fromarray(np.random.default_rng(7).integers(0, 255, (1990, 1180, 3), dtype=np.uint8)).save(payload, 'JPEG')
    try:
        response = recognize_bytes(payload.getvalue(), settings=Settings(_env_file=None, data_dir=tmp_path,
            store_captures=False, text_identity_candidates=enabled, ocr_label_name_filter=enabled,
            slab_label_identity=slab_label, full_image_text_fallback=full_image,
            slab_text_recovery=recovery, use_client_quad=holder),
            runtime=runtime, catalog=catalog, results=results, session_id='test', graded=False,
            **({'card_quad': [(.01, .17), (.86, .17), (.86, .79), (.01, .79)]} if holder else {}))
        evidence = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
        scan.whole_reads = whole_reads
        scan.reads = reads
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
    names = [h for h in hits if h.region in ('name', 'holder_name')][:len(case['hits'])]
    first = [h for h in names if h.region == 'name'] or names
    name = pick_confident_name([h.text for h in first], [h.confidence for h in first], label_filter=True)
    assert name is None or not grading_label_line(name)
    before_filter = True if case.get('path') == 'slab_recovery' else False
    assert pick_confident_name([h.text for h in first], [h.confidence for h in first],
                               label_filter=before_filter) == case['before']['name_text']
    footer = [h.text for h in hits if h.region == 'collector']
    if footer:
        assert pick_collector_text(footer, template_filter=before_filter) == case['before'].get(
            'collector_text', pick_collector_text(footer))
        assert pick_collector_text(footer, template_filter=True) not in {'retreat', 'resistance', 'weakness'}
    numbers = extract_collector_candidates([h.text for h in hits], hits=hits)
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'),
                                   indexed_ids={r['id'] for r in case['catalogue_rows']})
    if case.get('path') == 'slab_recovery':
        # Slab-outline app scans on staging: the recovery rules pick no label line as the
        # name, no attack damage as the number, and reach exactly the right card.
        texts = [h.text for h in first]
        name = pick_confident_name(texts, [h.confidence for h in first], label_filter='set_lines')
        assert name is None or not (grading_label_line(name) or slab_label_field(name))
        if footer:
            assert pick_collector_text(footer, template_filter='set_lines') not in {'20', '200', '21', 'retreat'}
        languages = tuple(case['languages'])
        label_hits = [*hits, *(OcrHit(h['text'], h['confidence'], h['region'])
                               for h in case.get('label_half_hits', []))]
        found, reason = label_identity_candidates(index, catalog, hits=label_hits, languages=languages,
                                                  recovery=True)
        if not found:
            found, reason = text_identity_candidates(index, catalog, hits=hits, numbers=numbers,
                                                     languages=languages, numerator_fallback=True)
        if case.get('answered_by_picture'):
            # No label text was read; the picture alone answered, and text must not interfere.
            catalog.close()
            return
        assert found == case['expected_card_ids']
        reason = 'candidates'
    elif case.get('path') == 'full_image':
        # The first pass alone reaches nothing on either path.
        assert text_identity_candidates(index, catalog, hits=hits, numbers=numbers,
                                        languages=())[0] == []
        assert label_identity_candidates(index, catalog, hits=hits, languages=())[0] == []
        full = [OcrHit(h['text'], h['confidence'], h['region']) for h in case['full_image_hits']]
        full_numbers = extract_collector_candidates([], hits=full)
        # The page counter "1/5" is a second confident fraction; only "any fraction" mode
        # lets the card's own 017/032 stand.
        assert text_identity_candidates(index, catalog, hits=full, numbers=full_numbers,
                                        languages=('ja',))[1] == 'conflicting_fractions'
        found, reason = text_identity_candidates(index, catalog, hits=full, numbers=full_numbers,
                                                 languages=('ja',), any_fraction=True)
        assert found == case['expected_card_ids']
    elif case.get('path') == 'label':
        found, reason = label_identity_candidates(index, catalog, hits=hits, languages=tuple(case['languages']))
        # The number+name path alone cannot reach these cards.
        assert set(case['expected_card_ids']).isdisjoint(text_identity_candidates(
            index, catalog, hits=hits, numbers=numbers, languages=tuple(case['languages']))[0])
    else:
        found, reason = text_identity_candidates(index, catalog, hits=hits, numbers=numbers,
                                                 languages=tuple(case['languages']))
    assert reason == 'candidates' and 1 <= len(found) <= 3
    assert set(case['expected_card_ids']) & set(found)
    if case.get('path') == 'label':
        assert found == case['expected_card_ids']
    catalog.close()


@pytest.mark.parametrize('lines,sets,number', [
    (['CGC UNIVERSAL GRADE', 'Charmander', 'Pokémon (2017)', 'Burning Shadows- 18a/147'], 'BURNING SHADOWS', '18A'),
    (['2017 POKEMON SM BURNING SHADOWS', '#18A', 'CHARMANDER', 'NM-MT'], 'POKEMON SM BURNING SHADOWS', '18A'),
    (['2017 Pokemon Sun & Moon Burning Shadows #18a', 'Charmander'], 'POKEMON SUN & MOON BURNING SHADOWS', '18A'),
    (['2019 POKEMON SM HIDDEN FATES', '#SV59', 'MEWTWO GX'], 'POKEMON SM HIDDEN FATES', 'SV59'),
    (['2021 POKEMON SWSH PROMO', '#SWSH050', 'PIKACHU'], 'POKEMON SWSH PROMO', 'SWSH50'),
    (['2022 POKEMON LOST ORIGIN', '#TG01', 'BRAIXEN'], 'POKEMON LOST ORIGIN', 'TG1'),
    (['Trading Card Game Classic - 026/032', 'Holo - Blastoise & Suicune ex Deck'], 'TRADING CARD GAME CLASSIC', '26'),
])
def test_label_set_lines_of_each_grader(lines, sets, number):
    found, parsed = parse_label(lines)
    assert found[0].strip() == sets and parsed == number


def test_number_keys_keep_prefix_and_suffix():
    assert [number_key(v) for v in ('018a', '18', 'SV059', 'TG01', 'GG70', 'SWSH050', '026/032')] == [
        '18A', '18', 'SV59', 'TG1', 'GG70', 'SWSH50', '26']
    # Two different numbers on one label abstain.
    assert parse_label(['#18A', 'Burning Shadows - 19/147'])[1] is None


def test_template_words_never_become_the_collector_text():
    footer = ['Flame Tail', '20', '×2', 'resistance', 'retreat']
    assert pick_collector_text(footer) == 'retreat'
    assert pick_collector_text(footer, template_filter=True) == '20'
    assert pick_collector_text(['×2', '-30', 'retreat'], template_filter=True) is None
    assert pick_collector_text(['weakness', 'resistance'], template_filter=True) is None
    assert pick_collector_text(['retreat', '18a/147'], template_filter=True) == '18a/147'
    for junk in ('damage and Electabuzz does 10 damage', '©2023 PokemoeN', 'es 2 Priz', '09470703AK', '30KC'):
        assert pick_collector_text([junk], template_filter=True) is None
    assert pick_collector_text(['your turn.', 'MFGG66/GG70'], template_filter=True) == 'MFGG66/GG70'
    assert pick_collector_text(['energy', '085'], template_filter=True) == '085'
    assert pick_collector_text(['SV59'], template_filter=True) == 'SV59'


def test_near_threshold_leader_that_contradicts_the_text_gets_candidates(tmp_path, monkeypatch):
    # Without the label flag a 0.80 leader keeps text out entirely.
    response, evidence, _ = scan(tmp_path, monkeypatch, enabled=True, lead_score=.80)
    assert evidence['text_identity']['candidate_ids'] == []
    assert all(s.card_id != 'ja:CLF-017' for s in response.suggestions)


def test_slab_label_flag_tries_text_against_a_contradicted_near_threshold_leader(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=True, lead_score=.80, slab_label=True)
    assert evidence['text_identity']['leader_conflict'] is True
    assert [s.card_id for s in response.suggestions] == ['ja:CLF-017']
    assert response.status == 'uncertain' and response.confidence.requires_confirmation
    assert evidence['text_identity']['outcome'] == 'verified' and not boundary


def test_slab_label_flag_leaves_a_leader_the_text_supports(tmp_path, monkeypatch):
    # The leader is named like the read (ルギア), so text has no say at 0.80.
    response, evidence, _ = scan(tmp_path, monkeypatch, enabled=True, lead_score=.80, slab_label=True,
                                 lead_name='ルギアV')
    assert evidence['text_identity']['candidate_ids'] == []
    assert evidence['text_identity']['reason'] == 'visual_leader_supported'
    assert all(s.card_id != 'ja:CLF-017' for s in response.suggestions)


def test_whole_image_fallback_reads_a_screenshot_once_and_verifies(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=True, slab_label=True,
                                        screenshot=True, full_image=True)
    assert len(scan.whole_reads) == 1 and max(scan.whole_reads[0]) <= 1400
    assert [s.card_id for s in response.suggestions] == ['ja:CLF-017']
    assert response.status == 'uncertain' and response.confidence.requires_confirmation
    full = evidence['text_identity']['full_image']
    assert full['candidate_ids'] == ['ja:CLF-017'] and evidence['text_identity']['outcome'] == 'verified'
    assert any(p['scope'] == 'full_image_text' for p in evidence['passes'])
    assert {'text': '017/032', 'confidence': .995, 'region': 'full_image'} in evidence['hits']
    assert not boundary


def test_whole_image_fallback_is_off_by_default_and_the_screenshot_stays_a_retake(tmp_path, monkeypatch):
    response, evidence, boundary = scan(tmp_path, monkeypatch, enabled=True, slab_label=True, screenshot=True)
    assert scan.whole_reads == [] and response.status == 'retake' and boundary


@pytest.mark.parametrize('change', [dict(detected=True), dict(screenshot=False)])
def test_whole_image_fallback_never_runs_on_a_found_frame_or_a_read_number(tmp_path, monkeypatch, change):
    options = dict(enabled=True, slab_label=True, screenshot=True, full_image=True)
    options.update(change)
    scan(tmp_path, monkeypatch, **options)
    assert scan.whole_reads == []


def test_psa_japanese_label_recovers_by_name_number_and_language(tmp_path):
    # Holder-quad Lugia scan ad1b8f19: the label's set name is not the catalogue's.
    lines = ['10', 'PRISTINE', '2023 POKÉMON JP', 'CLASSIC COLLECTION', 'LUGIA EX', '#17HOLO', '00044829']
    assert parse_label(lines)[1] is None
    assert parse_label(lines, recovery=True)[1] == '17'
    catalog = catalogue(tmp_path)
    ids = {r[0] for r in catalog.execute('SELECT id FROM cards')}
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=ids)
    hits = [OcrHit(t, .99, 'holder_name') for t in lines]
    assert label_identity_candidates(index, catalog, hits=hits, languages=())[0] == []
    # "JP" decides the language even when the scan's own read was English.
    assert label_identity_candidates(index, catalog, hits=hits, languages=('en',),
                                     recovery=True)[0] == ['ja:CLF-017']


def test_unknown_denominator_falls_back_to_numerator_and_name(tmp_path):
    catalog = catalogue(tmp_path)
    ids = {r[0] for r in catalog.execute('SELECT id FROM cards')}
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=ids)
    misread = [OcrHit('017/012', .95, 'collector')]
    hits = [*misread, OcrHit('ルギア', .99, 'name')]
    assert text_identity_candidates(index, catalog, hits=hits, numbers=misread,
                                    languages=('ja',))[1] == 'number_not_in_catalogue'
    assert text_identity_candidates(index, catalog, hits=hits, numbers=misread, languages=('ja',),
                                    numerator_fallback=True) == (['ja:CLF-017'], 'numerator_candidates')
    # A known total that simply has no such card is not a misread.
    other = [OcrHit('017/147', .95, 'collector')]
    catalog.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,"
                    "printed_collector_number) VALUES ('ja:X-1','ja:X-1','x','X','X','001','ja','001/147')")
    catalog.commit()
    index = MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=ids | {'ja:X-1'})
    assert text_identity_candidates(index, catalog, hits=[*other, OcrHit('ルギア', .99, 'name')], numbers=other,
                                    languages=('ja',), numerator_fallback=True)[0] == ['ja:CLF-017']


def test_set_line_under_a_dated_label_header_is_never_the_name():
    lines = ['10', 'PRISTINE', '2023 POKÉMON JP', 'CLASSIC COLLECTION', 'LUGIA EX', '#17HOLO', '00044829']
    assert pick_confident_name(lines, [.99]*7, label_filter=True) == 'CLASSIC COLLECTION'
    assert pick_confident_name(lines, [.99]*7, label_filter='set_lines') == 'LUGIA EX'
    mew = ['2023 POKEMON SVP EN', '#053', 'MEW ex', 'NM-MT', '151 ULTRA-PREMIUM COLL', '8', 'FSA']
    assert pick_confident_name(mew, [.99]*7, label_filter='set_lines') == 'MEW ex'
    cgc = ['CGC UNIVERSAL GRADE', 'NM/Mint+', 'Charmander', '8.5', 'Pokémon (2017)', 'Burning Shadows- 18a/147']
    assert pick_confident_name(cgc, [.99]*6, label_filter='set_lines') == 'Charmander'
    # Panel slab fresh100_307061782471: this header already holds its set; the next line is the card.
    gyarados = ['2016 BREAKPOINT', 'MGYARADOSEX', 'FULLART', 'NM-MT', '#115', '792958']
    assert pick_confident_name(gyarados, [.99]*6, label_filter='set_lines') == 'MGYARADOSEX'



def test_slab_label_lines_and_attack_damage_are_never_name_or_number():
    for line in ('#17HOLO', 'Burning Shadows- 18a/147', 'Cos. Holo - Charmander Sidekick Coll.'):
        assert slab_label_field(line)
    for title in ('Charmander', 'Porygon2', 'LUGIA EX', 'Mr. Mime', 'Ho-Oh ex', 'Pikachu-GX'):
        assert not slab_label_field(title)
    assert pick_confident_name(['#17HOLO', '00044829', '龙办', 'ルギア', '230*'], [.99, 1, .52, 1, .99],
                               label_filter='set_lines') == 'ルギア'
    assert pick_confident_name(['CLASSIC COLLECTION', 'LUGIA EX', '#17HOLO', '00044829', 'ルギア', '230*'],
                               [.99] * 6, label_filter='set_lines') == 'ルギア'
    assert pick_confident_name(['Pokemon (2017)', 'Burning Shadows- 18a/147', 'Cos. Holo - Charmander Sidekick Coll.'],
                               [.94, .97, .99], label_filter='set_lines') is None
    assert pick_collector_text(['****エアロブレイク', '200', '-30', '×21'], template_filter='set_lines') is None
    assert pick_collector_text(['Flame Tail', '20', '×2', 'retreat'], template_filter='set_lines') is None
    assert pick_collector_text(['053'], template_filter='set_lines') == '053'
    assert pick_collector_text(['SWSH050'], template_filter='set_lines') == 'SWSH050'
