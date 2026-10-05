"""Evidence-only recovery: crop pixels, read twice, never infer a grade."""
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.recognition.grading import LabelLine
from app.recognition.ocr import CardOcr


def test_grade_hypothesis_crops_original_observed_ink_not_full_proposal():
    from app.recognition.label_vision import grade_regions
    image = Image.new('RGB', (600, 300), 'white')
    image.paste((30, 50, 70), (330, 90, 345, 160))
    image.paste((30, 50, 70), (355, 90, 385, 160))
    lines = [LabelLine('PRISTINE', .99, (.5, .6, .7, .65))]
    regions = grade_regions(image, lines, 'cgc', tight=True)
    assert regions
    tile, observed = regions[0]
    assert tile.width < 100 and tile.height < 100
    assert np.any(np.all(np.asarray(tile) == [30, 50, 70], axis=2))
    assert .54 < observed[0] < .56 and .63 < observed[2] < .65
    legacy, legacy_box = grade_regions(image, lines, 'cgc')[0]
    assert legacy.width > tile.width and legacy_box == observed


@pytest.mark.parametrize('first,second,expected', [
    ('10', '10', 10), ('10', '9', None), ('4', '4', None),
    ('', '10', None), ('PRISTINE', 'PRISTINE', None),
])
def test_first_strip_recovery_requires_two_literal_reads(monkeypatch, first, second, expected):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision, 'label_panels', lambda image: [])
    monkeypatch.setattr(vision, 'text_label_panel', lambda *a, **k: None)
    monkeypatch.setattr(vision, 'grade_regions', lambda image, lines, company, **kwargs:
        [(image.crop((10, 10, 35, 50)), (.55, .35, .70, .55))])
    reader = object.__new__(CardOcr)
    reader.engine = SimpleNamespace(get_rec_res=lambda *a: None)
    calls = []
    lines = [LabelLine('CGC', .99, (.1, .1, .3, .2)),
             LabelLine('2023 POKEMON', .99, (.1, .3, .4, .4)),
             LabelLine('PRISTINE', .99, (.5, .6, .7, .7)),
             LabelLine('12345678', .99, (.1, .8, .4, .9))]
    def read(image):
        calls.append('detector')
        return lines
    reads = iter((first, second))
    def tokens(patches):
        calls.extend(['recognizer'] * len(patches))
        return [LabelLine(next(reads, ''), .99) for _ in patches]
    reader._grading_lines, reader._grading_tokens = read, tokens
    result = reader.read_grading(Image.new('RGB', (600, 1000)))
    assert result.grade == expected and len(calls) <= 10
    if expected is not None:
        assert calls == ['detector', 'recognizer', 'recognizer']
        assert result.company == 'cgc'
    if first == '4':
        assert 'condition_grade_contradiction' in result.warnings


@pytest.mark.parametrize('lines', [[], [LabelLine('PRISTINE', .99)],
    [LabelLine('CGC', .99)], [LabelLine('HP 100', .99)]])
def test_missing_label_context_cannot_trigger_grade_glyph_reads(monkeypatch, lines):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision, 'label_panels', lambda image: [])
    monkeypatch.setattr(vision, 'text_label_panel', lambda *a, **k: None)
    def unexpected(*a, **k):
        raise AssertionError('unverified label must not request grade glyphs')
    monkeypatch.setattr(vision, 'grade_regions', unexpected)
    reader = object.__new__(CardOcr)
    reader.engine = SimpleNamespace(get_rec_res=lambda *a: None)
    reader._grading_lines = lambda image: lines
    reader._grading_tokens = unexpected
    result = reader.read_grading(Image.new('RGB', (600, 1000)))
    assert result.grade is None
