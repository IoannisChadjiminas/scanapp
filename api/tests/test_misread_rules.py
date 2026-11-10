"""OCR_DAMAGE_NUMBER_GUARD and LATIN_NAME_TWIN, with negative cases."""

from app.recognition.misread_rules import damage_number_guard, latin_name_twin
from app.recognition.ocr import OcrHit


def texts(hits):
    return [h.text for h in hits]


def test_unpadded_damage_number_is_dropped_on_a_japanese_card():
    hits = [OcrHit('40', 0.9999, 'collector')]
    assert texts(damage_number_guard(hits, 'ja')) == []


def test_damage_guard_keeps_everything_when_another_bare_read_would_be_left_alone():
    # Emolga BW-P 236: dropping "60" would leave "4" naming PokéPark's Pikachu 004.
    hits = [OcrHit('60', 0.955, 'collector'), OcrHit('4', 0.908, 'collector'), OcrHit('70', None, 'unknown')]
    assert texts(damage_number_guard(hits, 'ja')) == ['60', '4', '70']


def test_damage_guard_drops_every_damage_read_when_they_are_the_only_bare_reads():
    hits = [OcrHit('40', 0.99, 'collector'), OcrHit('120', 0.9, 'collector'), OcrHit('058/102', 0.9, 'collector')]
    assert texts(damage_number_guard(hits, 'ja')) == ['40', '120', '058/102']   # 120 is not damage-shaped: keep all
    hits = [OcrHit('40', 0.99, 'collector'), OcrHit('20', 0.9, 'collector'), OcrHit('058/102', 0.9, 'collector')]
    assert texts(damage_number_guard(hits, 'ja')) == ['058/102']


def test_damage_guard_keeps_padded_numbers_fractions_other_languages_and_non_tens():
    hits = [OcrHit('040', 0.99, 'collector'), OcrHit('058/102', 0.9, 'collector'), OcrHit('48', 0.99, 'collector'),
            OcrHit('40', 0.99, 'unknown')]
    assert texts(damage_number_guard(hits, 'ja')) == ['040', '058/102', '48', '40']
    assert texts(damage_number_guard([OcrHit('40', 0.99, 'collector')], 'en')) == ['40']
    assert texts(damage_number_guard([OcrHit('40', 0.99, 'collector')], None)) == ['40']


EN_MEW = {'id': 'en:si1-1', 'name': 'Mew', 'language': 'en', 'set_name': 'Southern Islands'}
EN_MEW_OTHER = {'id': 'en:base1-x', 'name': 'Mew', 'language': 'en', 'set_name': 'Wizards Black Star Promos'}
JA_MEW = {'id': 'ja:jr-southern-islands-u09', 'name': 'Mew', 'language': 'ja', 'set_name': 'Southern Islands'}
BY_NAME = {'mew': [EN_MEW, EN_MEW_OTHER, JA_MEW]}


def test_latin_name_on_a_japanese_leader_names_the_english_card_in_the_same_set():
    assert latin_name_twin(BY_NAME, JA_MEW, 'MEW') == 'en:si1-1'


def test_latin_name_twin_negatives():
    assert latin_name_twin(BY_NAME, JA_MEW, 'ミュウ') is None              # Japanese name read
    assert latin_name_twin(BY_NAME, EN_MEW, 'MEW') is None                # leader already English
    assert latin_name_twin(BY_NAME, JA_MEW, 'Mewtwo') is None             # read does not name the leader
    assert latin_name_twin(BY_NAME, JA_MEW, 'Me') is None                 # too short
    assert latin_name_twin(BY_NAME, None, 'MEW') is None
    two = {'mew': [EN_MEW, dict(EN_MEW, id='en:si1-1b'), JA_MEW]}
    assert latin_name_twin(two, JA_MEW, 'MEW') is None                    # ambiguous in that set
    other_set = dict(JA_MEW, set_name='Expansion Pack')
    assert latin_name_twin(BY_NAME, other_set, 'MEW') is None             # no English card in that set


def test_index_rows_without_set_name_are_completed_by_fetch():
    bare = {'mew': [{'id': 'en:si1-1', 'name': 'Mew', 'language': 'en'}, {'id': 'en:basep-8', 'name': 'Mew', 'language': 'en'}, JA_MEW]}
    full = {'en:si1-1': EN_MEW, 'en:basep-8': EN_MEW_OTHER}
    assert latin_name_twin(bare, JA_MEW, 'MEW') is None
    assert latin_name_twin(bare, JA_MEW, 'MEW', fetch=lambda ids: {i: full[i] for i in ids}) == 'en:si1-1'
