"""Generic label/evidence rules, with no benchmark IDs or card exceptions."""
import pytest

from app.recognition.ocr import OcrHit, pick_name_line
from app.recognition.rank import artwork_evidence_compatible, decide_status, rerank, extract_collector_candidates


@pytest.mark.parametrize('label', ['トレーナーズ', 'サポート', 'サボート',
                                   'STAR', '#GG60', '#123', '#SWSH123'])
def test_layout_and_sku_labels_are_not_titles(label):
    assert pick_name_line([label]) is None
    assert pick_name_line([label, 'Example']) == 'Example'


@pytest.mark.parametrize('title', ['Porygon2', 'Unown V', 'ナンジャモ', 'Professor’s Research'])
def test_real_titles_remain_available(title):
    assert pick_name_line([title]) == title


def row(identifier, number, score=.9, name='Example', language='en'):
    return dict(card_id=identifier, collector_number=number, name=name,
                visual_score=score, language=language)


def test_explicit_fraction_beats_footer_stat_but_preserves_conflicting_fraction():
    def ranked(extra):
        return rerank([row('right', '096'), row('wrong', '071', .8)], 'Example',
            [OcrHit('096/071', .99, 'collector'), *extra], False,
            name_confidence=.99, require_confident_ocr=True)
    first = ranked([OcrHit('071', .99, 'collector')])[0]
    assert first['card_id'] == 'right' and not first['collector_conflict']
    conflicting = ranked([OcrHit('097/071', .99, 'collector')])
    assert next(r for r in conflicting if r['card_id']=='right')['structured_collector_conflict']
    assert decide_status(conflicting, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) != 'matched'


def test_untranslated_localized_title_is_unknown_not_equal_or_conflicting():
    candidate = row('local', '001', name='Example', language='ja')
    numbers = [OcrHit('001/028', .99, 'collector')]
    ranked = rerank([candidate], 'ピカチュウ', numbers, False,
        detected_languages=('ja',), name_confidence=.99, require_confident_ocr=True)
    assert ranked[0]['localized_name_unknown']
    assert not ranked[0]['strong_name_conflict']
    assert artwork_evidence_compatible(candidate, ocr_name='ピカチュウ',
        name_confidence=.99, numbers=numbers, languages=('ja',))
    assert decide_status(ranked, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) == 'uncertain'


def test_known_localized_name_conflict_and_foreign_language_stay_conflicts():
    for candidate in [row('other', '001', name='イーブイ', language='ja'),
                      row('foreign', '001', name='Example', language='en')]:
        ranked = rerank([candidate], 'ピカチュウ', [], False,
            detected_languages=('ja',), name_confidence=.99, require_confident_ocr=True)
        assert ranked[0]['strong_name_conflict']
        assert not artwork_evidence_compatible(candidate, ocr_name='ピカチュウ',
            name_confidence=.99, numbers=[], languages=('ja',))


@pytest.mark.parametrize('observed,expected', [
    ('G SY2D 096/071 SAR', ['096/071']),
    ('G sY2D 096/071 SAR', ['096/071']),
    ('FGG68/GG70', ['GG68/70']), ('MFGG60/GG70*', ['GG60/70']),
    ('TG01/TG30', ['TG01/30']), ('TG01/GG30', ['TG01', 'GG30']),
    ('S8a', []), ('Illus. Artist 2023', []), ('©2023 Nintendo', []),
    ('©1995, 96, 98 Nintendo ©1999–2000 Wizards. 87/130', ['87/130']),
    ('©1999 Nintendo 87/130 and 88/130', ['87/130', '88/130']),
    ('D201', ['D201']), ('GG70', ['GG70']), ('59/102', ['59/102']),
])
def test_collector_normalization_keeps_namespaces_and_rejects_non_identifiers(observed, expected):
    assert [h.text for h in extract_collector_candidates([], hits=[OcrHit(observed,.99,'collector')])] == expected


def test_health_label_does_not_override_a_weak_real_title():
    from app.recognition.ocr import pick_confident_name
    assert pick_confident_name(['Example', 'VSTAR', 'STAR', 'HP', '280'],
                              [.8, .99, .99, .99, .99]) == 'Example'


def test_unknown_translation_does_not_bypass_visual_floor():
    ranked = rerank([row('weak', '001', .2, name='Example', language='ja')],
        'ピカチュウ', [], False, detected_languages=('ja',),
        name_confidence=.99, require_confident_ocr=True)
    assert ranked[0]['localized_name_unknown']
    assert decide_status(ranked, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) == 'no_match'
