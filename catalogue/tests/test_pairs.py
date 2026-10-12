from bootstrap.pairs import decide_pair


def test_one_identical_crop_is_the_only_confirmed_pair():
    assert decide_pair([("en:hgss1-73", 1.0), ("en:col1-63", 0.4)]) == (
        "paired",
        "crop_probe_identical",
        "en:hgss1-73",
    )


def test_two_identical_crops_stay_in_review():
    assert decide_pair([("en:dp1-118", 1.0), ("en:dp7-92", 0.999)])[0] == "review"


def test_similar_crop_is_not_confirmed():
    status, reason, twin = decide_pair([("en:hgss1-73", 0.85)])
    assert (status, reason, twin) == ("review", "similar_artwork_not_identical", None)


def test_missing_probe_is_a_hold():
    assert decide_pair([]) == ("held", "no_source_image", None)
    assert decide_pair([("en:dp1-72", 0.83)])[0] == "held"
