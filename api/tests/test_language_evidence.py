from app.recognition.language import confident_language_texts, resolve_search_languages
from app.recognition.ocr import OcrHit


def test_unreadable_foreign_script_does_not_override_english_fields():
    hits=[OcrHit('Dragonite V',.99,'name'),OcrHit('weakness',.99,'collector'),
          OcrHit('香香',.53,'collector')]
    assert resolve_search_languages('auto',confident_language_texts(hits)).detected == 'en'


def test_confident_japanese_remains_detected_among_latin_copyright_text():
    hits=[OcrHit('ピカチュウ',.99,'name'),OcrHit('Nintendo Creatures GAME FREAK',.99,'collector')]
    assert resolve_search_languages('auto',confident_language_texts(hits)).detected == 'ja'


def test_unknown_confidence_is_neutral_and_explicit_language_still_wins():
    hits=[OcrHit('ピカチュウ',None,'name')]
    assert resolve_search_languages('auto',confident_language_texts(hits)).detected is None
    assert resolve_search_languages('en',confident_language_texts(hits)).search == ('en',)
