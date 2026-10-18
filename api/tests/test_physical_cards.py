import numpy as np

from app.physical_cards import is_tcg_pocket_card, is_tcg_pocket_card_id
from app.recognition.pipeline import _scan_keep
from app.recognition.printing import ReferencePrintingIndex


def test_pocket_sets_match_the_search_exclusion():
    assert is_tcg_pocket_card("en", "A1")
    assert is_tcg_pocket_card("en", "A2b")
    assert is_tcg_pocket_card("en", "B2a")
    assert is_tcg_pocket_card("en", "P-A")
    assert is_tcg_pocket_card_id("en:A1-001")
    assert is_tcg_pocket_card_id("en:P-A-007")
    assert not is_tcg_pocket_card("en", "sv08.5")
    assert not is_tcg_pocket_card("en", "bwp")
    assert not is_tcg_pocket_card("ja", "A1")
    assert not is_tcg_pocket_card_id("en:bwp-BW77")
    assert not is_tcg_pocket_card_id("en:sv08.5-123")


def test_scan_keep_drops_pocket_rows():
    class Runtime:
        card_languages = np.array(["en", "en", "ja"])
        physical_cards = np.array([True, False, True])

    class Requested:
        reason = "user"
        search = ("en",)

    keep = _scan_keep(Runtime(), Requested())
    assert list(keep) == [True, False, False]


class _SameArt:
    def thumbnail(self, card_id, raw_path):
        del card_id, raw_path
        vector = np.ones(8, dtype=np.float32)
        return vector / np.linalg.norm(vector)


def test_printing_family_leaves_out_the_pocket_card(tmp_path):
    index = ReferencePrintingIndex(tmp_path, feature_store=_SameArt())
    rows = [
        {"id": "en:sv03-006", "name": "Charizard", "language": "en", "set_id": "sv03", "image_path": "a"},
        {"id": "en:A1-006", "name": "Charizard", "language": "en", "set_id": "A1", "image_path": "b"},
    ]

    class Catalog:
        def execute(self, sql, params):
            del sql, params
            return type("Result", (), {"fetchall": lambda self: rows})()

    members, incomplete = index.family(Catalog(), {"card_id": "en:sv03-006", "name": "Charizard", "language": "en"})
    assert [row["id"] for row in members] == ["en:sv03-006"]
    assert incomplete is False
