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

    def _tcgdex_run(self, run, row):
        group = {"group_id": "me06", "name": "Delta Reign", "code": "me06",
                 "coverage": "absent", "catalogue_codes": []}
        (run / "set-registry.json").write_text(json.dumps([group]))
        (run / "catalogue.json").write_text(json.dumps({}))
        for filename, values in [
            ("new-or-incomplete-printings.jsonl", [row]),
            ("image-chosen.jsonl", [dict(row, status="no_file")]),
            ("held-mappings.jsonl", [dict(row, status="held", reason="not_verified")]),
        ]:
            (run / filename).write_text(json.dumps(values[0]) + "\n")
        (run / "verified-mappings.jsonl").write_text("")

    def test_tcgdex_rows_keep_their_rarity(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            row = {"group_id": "me06", "printed_number": "104/103", "card_name": "Mega Gardevoir ex",
                   "source_row_url": "https://api.tcgdex.net/v2/en/cards/me06-104",
                   "rarity": "Ultra Rare", "category": "Pokemon", "illustrator": "aky CG Works"}
            self._tcgdex_run(run, row)
            main(str(run), str(run / "catalogue.json"))
            card = json.loads((run / "cards.json").read_text())[0]
            self.assertEqual((card["rarity"], card["category"], card["illustrator"]),
                             ("Ultra Rare", "Pokemon", "aky CG Works"))

    def test_tcgdex_row_without_rarity_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            row = {"group_id": "me06", "printed_number": "001/103", "card_name": "Heracross",
                   "source_row_url": "https://api.tcgdex.net/v2/en/cards/me06-001"}
            self._tcgdex_run(run, row)
            with self.assertRaises(SystemExit):
                main(str(run), str(run / "catalogue.json"))


if __name__ == "__main__":
    unittest.main()
