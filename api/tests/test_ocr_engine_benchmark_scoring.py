import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('ocr_engine_benchmark_scoring',
    Path(__file__).resolve().parents[1] / 'scripts/score_ocr_engine_benchmark.py')
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def test_formatting_is_neutral_but_digits_are_not_fuzzy_repaired():
    assert scorer.normalize_name('Flabébé HP 40') == scorer.normalize_name('Flabébé')
    assert scorer.normalize_name('Blastoise 0') != scorer.normalize_name('Blastoise')
    assert scorer.canonical_number('０６５ / ０９５') == scorer.canonical_number('65/95')
    assert scorer.canonical_number('065/095') != scorer.canonical_number('065/096')


def test_gallery_namespaces_and_denominators_are_preserved():
    numbers = scorer.observed_numbers(['G TG01/TG30', 'SV59/SV94', 'RC29/RC32'])
    assert scorer.canonical_number('TG01/TG30') in numbers
    assert scorer.canonical_number('SV59/SV94') in numbers
    assert scorer.canonical_number('RC29/RC32') in numbers
    assert not scorer.agrees(scorer.canonical_number('1/30'), scorer.canonical_number('TG1/TG30'))


def test_presence_is_not_the_same_as_correct_first_selection():
    record = {'lines':[{'text':'188/167'}, {'text':'TEF EN 165/162'}]}
    score = scorer.evaluate(record, {'printed_name':'Ancient Booster Energy Capsule','number':'165/162'})
    assert score['number_recalled']
    assert not score['number_selected']


def test_no_number_is_not_a_success():
    score = scorer.evaluate({'lines':[]}, {'printed_name':'Toxel','number':'68/189'})
    assert not score['name_recalled']
    assert not score['number_recalled']
    assert not score['number_selected']


def test_missing_japanese_name_label_is_unscored_not_wrong():
    score = scorer.evaluate({'lines':[{'text':'029/055'}]}, {'number':'029/055'})
    assert score['name_recalled'] is None
    assert score['name_selected'] is None
    assert score['number_recalled']


def test_promos_and_explicit_adjacent_namespace():
    numbers = scorer.observed_numbers(['SWSH 020', 'SVP EN', '053', 'MEP023'])
    assert scorer.canonical_number('SWSH020') in numbers
    assert scorer.canonical_number('SVP053') in numbers
    assert scorer.canonical_number('MEP023') in numbers


def test_partial_number_truth_does_not_assert_denominator():
    assert scorer.agrees(scorer.canonical_number('165/162'), scorer.canonical_number('165'))
    assert not scorer.agrees(scorer.canonical_number('165/163'), scorer.canonical_number('165/162'))


def test_exact_name_selection_and_recall_are_distinct():
    score = scorer.evaluate({'lines':[{'text':'Blastoise 0'}]}, {'printed_name':'Blastoise','number':'14/100'})
    assert score['name_recalled']
    assert not score['name_selected']
