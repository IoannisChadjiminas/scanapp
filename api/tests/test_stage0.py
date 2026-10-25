import base64
from types import SimpleNamespace

from app.config import Settings
from app.routes.health import scan_price_config
from app.scan_summary import ScanSource
from app.stage0 import phone_evidence, stage0_line

MODEL = '2ddf6ec79e37/coreml-pal8'
VECTOR = base64.b64encode(b'\x00' * 768).decode('ascii')


def _result(name='Lugia ex', number='17'):
    top = SimpleNamespace(name=name, collector_number=number, card_id='ja:CLF-017')
    return SimpleNamespace(id='scan-1', suggestions=[top])


def _source(valid=True):
    return ScanSource(quad='rect' if valid else 'none', quad_valid=valid)


def test_config_switches_default_off_and_can_be_turned_on():
    off = scan_price_config(Settings(_env_file=None))
    assert off.client_text is False
    assert off.client_label is False
    assert off.client_embedding is False
    assert off.client_quality is False
    on = scan_price_config(Settings(
        _env_file=None,
        app_client_text=True,
        app_client_label=True,
        app_client_embedding=True,
        app_client_quality=True,
    ))
    assert on.client_text and on.client_label and on.client_embedding and on.client_quality


def test_invalid_fields_are_absent_and_do_not_raise():
    evidence = phone_evidence('{', 'nope', '{"model":"other","vector":"aa"}')
    assert evidence.text is False
    assert evidence.embedding is False
    assert evidence.quality is False
    line = stage0_line(_result(), trace='t', source=_source(), evidence=evidence)
    assert line.startswith('stage0 ')
    assert 'text=0' in line and 'embedding=0' in line and 'vector_top=off' in line
    assert 'would=none' in line
    assert 'Lugia' not in line


def test_text_quality_and_a_valid_embedding_are_logged_without_a_search():
    text = (
        '{"v":2,"engine":"apple-vision","name":"Lugia ex","number":"17/100",'
        '"label_name":"LUGIA EX","label_number":"17","label_language":"ja",'
        '"label_grader":"PSA","label_grade":"10"}'
    )
    quality = '{"sharpness":120.5,"card_fraction":0.42,"glare":0.012}'
    embedding = '{"model":"%s","vector":"%s"}' % (MODEL, VECTOR)
    evidence = phone_evidence(text, quality, embedding)
    assert evidence.text and evidence.label and evidence.embedding
    assert evidence.name == 'Lugia ex'
    assert evidence.sharpness == 120.5
    line = stage0_line(_result(), trace='t', source=_source(), evidence=evidence)
    assert 'text=1' in line and 'label=1' in line and 'embedding=1' in line
    assert 'quality=1' in line
    assert 'name_agree=true' in line and 'number_agree=true' in line
    assert 'label_name_agree=true' in line
    assert 'sharpness=120.5' in line and 'card_fraction=0.420' in line
    assert 'vector_top=off' in line and 'would=text' in line
    assert 'LUGIA EX' not in line


def test_a_wrong_embedding_length_or_an_oversized_text_is_left_out():
    short = base64.b64encode(b'\x00' * 10).decode('ascii')
    evidence = phone_evidence(
        '{"v":1,"engine":"apple-vision","name":"' + ('A' * 800) + '"}',
        '{"sharpness":-1,"glare":2}',
        '{"model":"%s","vector":"%s"}' % (MODEL, short),
    )
    assert evidence.text is False
    assert evidence.embedding is False
    assert evidence.sharpness is None
    assert evidence.glare is None


def test_android_litert_embedding_id_is_recognized_as_phone_evidence():
    embedding = '{"model":"2ddf6ec79e37/litert-fp16","vector":"%s"}' % VECTOR
    assert phone_evidence(None, None, embedding).embedding


def test_disagreement_is_a_boolean_and_not_the_phone_text():
    text = '{"v":1,"engine":"mlkit-latin","name":"Charmander","number":"18a/147"}'
    evidence = phone_evidence(text, None, None)
    line = stage0_line(
        _result(name='Bulbasaur', number='1'),
        trace='t',
        source=_source(valid=False),
        evidence=evidence,
    )
    assert 'name_agree=false' in line and 'number_agree=false' in line
    assert 'would=none' in line and 'quad_valid=false' in line
    assert 'Charmander' not in line
