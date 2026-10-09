from types import SimpleNamespace

from PIL import Image

from app.recognition.ocr_framing import wide_footer_allowed, wide_footer_fractions


BASE = dict(name='Charmeleon', set_id='base1', collector_number='24', printed_collector_number='24/102')
BASE2 = dict(name='Charmeleon', set_id='base4', collector_number='35', printed_collector_number='35/130')
OTHER = dict(name='Comfey', set_id='sv04', collector_number='79', printed_collector_number='79/182')


def engine(*lines):
    seen = []
    def run(patch):
        seen.append(patch.size)
        return [text for text, _ in lines], [score for _, score in lines]
    return SimpleNamespace(_run=run, seen=seen)


def photo(width=1345, height=1600):
    return Image.new('RGB', (width, height))


def test_only_a_photo_wider_than_a_card_gets_the_wide_read():
    assert wide_footer_allowed(photo(1345, 1600))
    assert not wide_footer_allowed(photo(1139, 1600))
    assert not wide_footer_allowed(photo(400, 440))


def test_a_printed_fraction_of_the_named_card_is_kept():
    reader = engine(('unbearably high levels. LV. 32 #5', .97), ('24/102', 1.))
    hits, record = wide_footer_fractions(reader, photo(), 'Charmeleon', [BASE2, BASE, OTHER])
    assert [(hit.text, hit.confidence, hit.region) for hit in hits] == [('24/102', 1., 'collector')]
    # The lower part of the photo, not the bottom strip.
    assert reader.seen == [(1345, 640)]
    assert record['reason'] == 'wide_footer' and record['region'] == 'collector'


def test_a_neighbouring_cards_fraction_is_dropped():
    reader = engine(('79/182', .99), ('24/103', .99), ('102', .99))
    hits, _ = wide_footer_fractions(reader, photo(), 'Charmeleon', [BASE2, BASE, OTHER])
    assert hits == []


def test_a_weak_or_decorated_read_is_dropped():
    reader = engine(('24/102', .84), ('24/102XX', .99), ('24/102', None))
    hits, _ = wide_footer_fractions(reader, photo(), 'Charmeleon', [BASE])
    assert hits == []


def test_the_same_fraction_read_twice_is_one_hit():
    reader = engine(('24/102', .99), ('24/102', .95))
    hits, _ = wide_footer_fractions(reader, photo(), 'Charmeleon', [BASE])
    assert [hit.text for hit in hits] == ['24/102']


def test_no_title_or_no_patch_reader_reads_nothing():
    reader = engine(('24/102', 1.))
    assert wide_footer_fractions(reader, photo(), None, [BASE]) == ([], None)
    assert reader.seen == []
    assert wide_footer_fractions(SimpleNamespace(), photo(), 'Charmeleon', [BASE]) == ([], None)
