"""Preview ordering: near-tied printings show the reader's language first, nothing else moves."""
from app.recognition.language import locale_languages, order_preview_ids

LANG = {'en1': 'en', 'ja1': 'ja', 'en2': 'en', 'zh1': 'zh-tw', 'far-en': 'en'}


def order(ids, scores, preference, gap=.04):
    return order_preview_ids(ids, scores, LANG, preference, gap)


def test_english_printing_moves_ahead_of_a_japanese_one_within_the_gap():
    assert order(['ja1', 'en1', 'zh1'], [.90, .89, .80], ('en',)) == ['en1', 'ja1', 'zh1']


def test_nothing_outside_the_gap_moves_up():
    # far-en is English but .20 behind: it stays behind the tied cards.
    assert order(['ja1', 'zh1', 'far-en'], [.90, .89, .70], ('en',)) == ['ja1', 'zh1', 'far-en']


def test_requested_language_beats_the_phone_locale_and_visual_order_breaks_ties():
    assert order(['en1', 'ja1', 'en2'], [.90, .90, .90], ('ja', 'en')) == ['ja1', 'en1', 'en2']


def test_no_preference_or_empty_input_changes_nothing():
    assert order(['ja1', 'en1'], [.9, .9], ()) == ['ja1', 'en1']
    assert order([], [], ('en',)) == []


def test_unknown_language_goes_after_known_ones_in_the_tie():
    assert order(['mystery', 'ja1'], [.9, .9], ('en', 'ja')) == ['ja1', 'mystery']


def test_locale_to_catalogue_languages():
    assert locale_languages('en_GB') == ('en',)
    assert locale_languages('ja_JP') == ('ja',)
    assert locale_languages('zh_TW') == ('zh-tw',)
    assert locale_languages('zh-Hans_CN') == ('zh-cn',)
    assert locale_languages('pt_BR') == ('pt-br', 'pt')
    assert locale_languages('unknown') == () and locale_languages(None) == ()
    assert locale_languages('xx_YY') == ()
