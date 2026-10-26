"""The review record keeps what the phone sent (corners, text with confidences, embedding flag).

Diagnostics only: nothing here changes a result.
"""
from types import SimpleNamespace

from app.routes.scans import phone_inputs


def test_phone_inputs_records_text_confidences_and_the_embedding_flag():
    hint = SimpleNamespace(engine='mlkit-latin', name='Pikachu', name_conf=0.95, number='35/108',
                           number_conf=0.9, number_candidates=('35/108',))
    record = phone_inputs('[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]', hint, '{"v":1}')
    assert record['embedding_sent'] is True
    assert record['client_text']['name_conf'] == 0.95
    assert record['client_text']['number'] == '35/108'
    assert record['client_text']['number_candidates'] == ['35/108']


def test_phone_inputs_without_text_or_embedding():
    record = phone_inputs(None, None, None)
    assert record == {'card_quad': None, 'client_text': None, 'embedding_sent': False}
