"""PRINTING_EXACT_FRACTION, PRINTING_BARE_NUMBER, OCR_SET_CODE_READ, RETRY_OWN_LANGUAGE."""

from app.config import Settings
from app.recognition.footer_evidence import (bare_number_printing, clean_fraction, drop_set_code_reads,
                                             exact_fraction_printing, retry_language_supported,
                                             set_code_index, set_codes)
from app.recognition.ocr import OcrHit


def card(cid, name, number, total=None, language='ja', set_id=None, **extra):
    return {'card_id': cid, 'id': cid, 'name': name, 'view_title': extra.pop('view_title', name),
            'collector_number': number, 'set_total': total, 'language': language,
            'set_id': set_id or cid.split(':')[1].rsplit('-', 1)[0], **extra}


def hits(*reads):
    return [OcrHit(text, conf, region) for text, conf, region in
            ((*r, 'collector')[:3] if len(r) == 2 else r for r in reads)]


RAYQUAZA_MDB = card('ja:MDB-025', 'レックウザEX', '025', 46, view_title='Rayquaza EX',
                    printed_collector_number='025/046')
RAYQUAZA_BW5 = card('ja:BW5-Brn-037', 'Rayquaza EX', '037', 50)
TOTALS = {'ja:BW5-Brn-037': 50, 'ja:MDB-025': 46, 'ja:BW9-037': 76, 'ja:XY1-By-014': 60}


def fetcher(*rows):
    def fetch(language, spellings):
        return [r for r in rows if r['language'] == language and r['collector_number'] in spellings]
    return fetch


def total_of(row):
    return TOTALS.get(row['id'])


def test_the_four_flags_shipped_on_staging_2026_11_10_are_on_by_default():
    s = Settings()
    assert s.printing_exact_fraction is True
    assert s.printing_bare_number is True
    assert s.ocr_set_code_read is True
    assert s.retry_own_language is True


def test_clean_fraction_needs_one_agreed_reliable_fraction():
    assert clean_fraction(hits(('037/050', .98)))[1:] == ('37', 50)
    assert clean_fraction(hits(('037/050', .98), ('037/050', .9)))[1:] == ('37', 50)
    assert clean_fraction(hits(('037/050', .98), ('031/050', .9))) is None
    assert clean_fraction(hits(('037/050', .84))) is None
    assert clean_fraction(hits(('037/050', .98, 'unknown'))) is None
    assert clean_fraction(hits(('SV037/050', .98))) is None
    assert clean_fraction(hits(('3/5', .98))) is None
    assert clean_fraction(hits(('037', .98))) is None


def test_exact_fraction_names_the_recovered_twin():
    got = exact_fraction_printing(RAYQUAZA_MDB, hits(('037/050', .98)),
                                  fetcher(RAYQUAZA_BW5, RAYQUAZA_MDB), total_of)
    assert got == 'ja:BW5-Brn-037'


def test_exact_fraction_changes_nothing_when_the_shown_card_agrees():
    assert exact_fraction_printing(RAYQUAZA_MDB, hits(('025/046', .98)),
                                   fetcher(RAYQUAZA_BW5), total_of) is None


def test_exact_fraction_needs_the_same_title_number_total_and_language():
    read = hits(('037/050', .98))
    other_name = card('ja:BW5-Brn-037', 'Zoroark', '037', 50)
    assert exact_fraction_printing(RAYQUAZA_MDB, read, fetcher(other_name), total_of) is None
    other_total = card('ja:BW9-037', 'Rayquaza EX', '037', 76)
    assert exact_fraction_printing(RAYQUAZA_MDB, read, fetcher(other_total), total_of) is None
    english = card('en:BW5-Brn-037', 'Rayquaza EX', '037', 50, language='en')
    assert exact_fraction_printing(RAYQUAZA_MDB, read, lambda language, spellings: [english], total_of) is None
    assert exact_fraction_printing(RAYQUAZA_MDB, hits(('037/050', .8)), fetcher(RAYQUAZA_BW5), total_of) is None


def test_exact_fraction_stays_open_with_two_matches_or_an_unknown_total():
    read = hits(('037/050', .98))
    second = card('ja:BW5-Rg-037', 'Rayquaza EX', '037', 50)
    totals = {**TOTALS, 'ja:BW5-Rg-037': 50}
    assert exact_fraction_printing(RAYQUAZA_MDB, read, fetcher(RAYQUAZA_BW5, second),
                                   lambda row: totals.get(row['id'])) is None
    unknown = card('ja:XYP-037', 'Rayquaza EX', '037')
    assert exact_fraction_printing(RAYQUAZA_MDB, read, fetcher(RAYQUAZA_BW5, unknown), total_of) is None


def test_exact_fraction_reads_the_printed_alias_total():
    alias = card('ja:MMBS-037', 'Rayquaza EX', '037', None, printed_collector_number='037/050')
    assert exact_fraction_printing(RAYQUAZA_MDB, hits(('037/050', .98)), fetcher(alias), total_of) == 'ja:MMBS-037'


def test_exact_fraction_matches_titles_that_differ_only_in_punctuation():
    leader = card('ja:XYP-076', 'Blastoise-EX', '076')
    twin = card('ja:XY1-By-014', 'Blastoise EX', '014', 60)
    assert exact_fraction_printing(leader, hits(('014/060', .998)), fetcher(twin), total_of) == 'ja:XY1-By-014'


PIKACHU_DPTS = card('ja:DPtS-007', 'Pikachu', '007', 13)
PIKACHU_DPP = card('ja:DPP-113', 'Pikachu', '113')
PIKACHU_SP = card('ja:SP-125', 'Pikachu', '125')


def test_bare_number_names_the_one_member_with_that_number():
    members = (PIKACHU_DPTS, PIKACHU_DPP, PIKACHU_SP)
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('113', .999), ('10', .9999))) == 'ja:DPP-113'
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('125', .9997), ('541', .8))) == 'ja:SP-125'


def test_bare_number_ignores_short_weak_round_or_fractioned_reads():
    members = (PIKACHU_DPTS, PIKACHU_DPP)
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('113', .94))) is None
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('13', .999))) is None
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('113', .999, 'unknown'))) is None
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('113', .999), ('007/013', .9))) is None
    round_member = card('ja:DPP-120', 'Pikachu', '120')
    assert bare_number_printing(PIKACHU_DPTS, (PIKACHU_DPTS, round_member), hits(('120', .999))) is None
    assert bare_number_printing(PIKACHU_DPTS, (PIKACHU_DPTS, round_member), hits(('020', .999))) is None


def test_bare_number_needs_one_number_and_one_member():
    members = (PIKACHU_DPTS, PIKACHU_DPP, PIKACHU_SP)
    assert bare_number_printing(PIKACHU_DPTS, members, hits(('113', .999), ('125', .999))) is None
    twin = card('ja:XYP-113', 'Pikachu', '113')
    assert bare_number_printing(PIKACHU_DPTS, (*members, twin), hits(('113', .999))) is None
    assert bare_number_printing(PIKACHU_DPP, members, hits(('113', .999))) is None
    assert bare_number_printing(PIKACHU_DPTS, (PIKACHU_DPTS,), hits(('113', .999))) is None


def test_bare_number_allows_only_the_members_own_set_code():
    leader = card('ja:SM12a-037', 'Volcanion', '037', 173)
    member = card('ja:SM6-027', 'Volcanion', '027', 94)
    assert bare_number_printing(leader, (leader, member), hits(('027', .9999), ('SM6', .947), ('7', .889))) == 'ja:SM6-027'
    assert bare_number_printing(leader, (leader, member), hits(('027', .9999), ('SM8', .947))) is None


def test_set_codes_spell_the_set_and_its_base():
    assert set_codes('BW1-Bw') == {'bw1-bw', 'bw1'}
    assert set_codes('SM10a') == {'sm10a'}
    assert set_codes(None) == set()


SETS = set_code_index([{'language': 'ja', 'set_id': 'SM10a'}, {'language': 'ja', 'set_id': 'BW1-Bw'},
                       {'language': 'en', 'set_id': 'sm10'}])
SET_TOTALS = {('ja', 'SM10a'): 54, ('ja', 'BW1-Bw'): 53, ('en', 'sm10'): 214}


def set_total_of(language, set_id):
    return SET_TOTALS.get((language, set_id))


def test_set_code_read_is_dropped_when_the_fraction_confirms_its_total():
    reads = hits(('027/054', .999), ('SM10A', .855))
    kept, dropped = drop_set_code_reads(reads, SETS, set_total_of, ('ja',))
    assert [h.text for h in kept] == ['027/054'] and dropped == ['SM10A']
    kept, dropped = drop_set_code_reads(hits(('037/053', .954), ('BW1', .997)), SETS, set_total_of)
    assert [h.text for h in kept] == ['037/053'] and dropped == ['BW1']


def test_set_code_read_stays_without_a_confirming_fraction():
    for reads in (hits(('SM10A', .9)),
                  hits(('027/070', .999), ('SM10A', .9)),
                  hits(('027/054', .999), ('SM10A', .8)),
                  hits(('027/054', .999), ('SM10A', .9, 'unknown')),
                  hits(('027/054', .999), ('XY7', .9)),
                  hits(('027/054', .999), ('027/070', .9), ('SM10A', .9))):
        kept, dropped = drop_set_code_reads(reads, SETS, set_total_of)
        assert kept == reads and dropped == []
    reads = hits(('027/054', .999), ('SM10A', .9))
    assert drop_set_code_reads(reads, SETS, set_total_of, ('en',)) == (reads, [])


NECROZMA = {'card_id': 'en:swsh5-63', 'name': 'Necrozma', 'collector_number': '63', 'set_total': 163,
            'language': 'en', 'set_id': 'swsh5'}


def retry(lead=NECROZMA, **changes):
    args = dict(first_name='Necrozma', first_name_confidence=1.0, first_numbers=hits(('063/163', .886)),
                retry_name=None, retry_name_confidence=0.0, retry_numbers=hits(('063/163', .947)),
                retry_languages=('en',))
    args.update(changes)
    return retry_language_supported(lead, **args)


def test_retry_is_kept_when_its_own_language_and_fraction_confirm_the_card():
    assert retry() is True


def test_retry_is_not_kept_without_language_fraction_or_agreement():
    assert retry(None) is False
    assert retry(retry_languages=('zh-tw',)) is False
    assert retry(retry_languages=()) is False
    assert retry(retry_numbers=hits(('063', .99))) is False
    assert retry(retry_numbers=hits(('063/163', .8))) is False
    assert retry(retry_numbers=hits(('064/163', .95))) is False
    assert retry(retry_numbers=hits(('063/189', .95))) is False
    assert retry(first_name='Charizard') is False
    assert retry(first_numbers=hits(('012/189', .95))) is False
    assert retry({**NECROZMA, 'strong_name_conflict': True}) is False
    assert retry({**NECROZMA, 'set_total': None}) is False
