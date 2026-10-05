from app.recognition.rank import name_match


def test_professor_display_suffix_does_not_hide_fuzzy_printed_title():
    assert name_match("Professor's Pesoarch","Professor's Research (Professor Magnolia)")
    assert name_match("Professor's Research","Professor's Research (Professor Oak)")
    assert not name_match('Pikachu',"Professor's Research (Professor Magnolia)")
    assert not name_match('Professor Magnolia',"Professor's Research (Professor Magnolia)")


def test_parenthetical_form_is_not_generally_removed():
    # A fuzzy short name must not benefit from stripping an arbitrary suffix.
    assert not name_match('Profesxor', 'Professor (Magnolia)')
