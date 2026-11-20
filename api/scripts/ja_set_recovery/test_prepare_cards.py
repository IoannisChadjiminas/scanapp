"""Check that additions to an existing set preserve identities and source names."""
import json
import tempfile
import unittest
from pathlib import Path

from prepare_cards import main


class PrepareCardsTest(unittest.TestCase):
    def test_japanese_additions_reserve_existing_unnumbered_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            group = {"group_id": "SI", "name": "Start Deck 100", "code": "SI",
                     "coverage": "partial_by_count", "catalogue_codes": ["SI"]}
            (run / "set-registry.json").write_text(json.dumps([group]))
            catalogue = {"SI": [{"id": "ja:SI-u01"}, {"id": "ja:SI-001"}]}
            (run / "catalogue.json").write_text(json.dumps(catalogue))
            rows = [{"group_id": "SI", "printed_number": number, "card_name": name,
                     "source_row_url": "https://limitlesstcg.com/cards/jp/SI/" + source}
                    for number, name, source in [("003/414", "トランセル", "3"),
                                                 ("unnumbered (G)", "基本草エネルギー", "G"),
                                                 ("unnumbered (R)", "基本炎エネルギー", "R")]]
            for filename, values in [
                ("new-or-incomplete-printings.jsonl", rows),
                ("image-chosen.jsonl", [dict(row, status="no_file") for row in rows]),
                ("held-mappings.jsonl", [dict(row, status="held", reason="not_verified") for row in rows]),
            ]:
                (run / filename).write_text("".join(json.dumps(row) + "\n" for row in values))
            (run / "verified-mappings.jsonl").write_text("")
            main(str(run), str(run / "catalogue.json"))
            cards = json.loads((run / "cards.json").read_text())
            self.assertEqual([c["id"] for c in cards], ["ja:SI-003", "ja:SI-u02", "ja:SI-u03"])
            self.assertEqual([c["name"] for c in cards], ["トランセル", "基本草エネルギー", "基本炎エネルギー"])
            self.assertTrue(all(c["problem"] is None for c in cards))
            self.assertTrue(all(c["source_row_url"].startswith("https://limitlesstcg.com/") for c in cards))


if __name__ == "__main__":
    unittest.main()
