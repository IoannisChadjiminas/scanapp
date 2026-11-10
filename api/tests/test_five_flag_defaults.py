from app.config import Settings


def test_the_five_flags_shipped_on_staging_2026_11_10_are_on_by_default():
    s = Settings()
    assert s.rank_fraction_confirmed is True
    assert s.ocr_fraction_total_guard is True
    assert s.number_led_lookup is True
    assert s.ocr_damage_number_guard is True
    assert s.latin_name_twin is True
