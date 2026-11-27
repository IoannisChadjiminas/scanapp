"""TCGdex rows get their rarity before a batch is built; a card TCGdex has not rated stops the run."""
import json
import tempfile
import unittest
from pathlib import Path

from fill_tcgdex_fields import main

CARDS = {
    "https://api.tcgdex.net/v2/en/cards/me06-001": {"rarity": "Common", "category": "Pokemon", "illustrator": "A"},
    "https://api.tcgdex.net/v2/en/cards/me06-002": {"rarity": None, "category": "Pokemon"},
}


class FillTcgdexFieldsTest(unittest.TestCase):
    def _run(self, directory, rows):
        path = Path(directory) / "new-or-incomplete-printings.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def test_fills_tcgdex_rows_and_leaves_others(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._run(directory, [
                {"card_name": "Heracross", "source_row_url": "https://api.tcgdex.net/v2/en/cards/me06-001"},
                {"card_name": "Pikachu", "source_row_url": "https://limitlesstcg.com/cards/jp/SI/3"},
            ])
            main(directory, fetch=CARDS.__getitem__)
            rows = [json.loads(line) for line in path.open()]
            self.assertEqual((rows[0]["rarity"], rows[0]["category"], rows[0]["illustrator"]), ("Common", "Pokemon", "A"))
            self.assertNotIn("rarity", rows[1])
            self.assertTrue(path.with_name(path.name + ".bak").is_file())

    def test_a_card_without_rarity_stops_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._run(directory, [
                {"card_name": "Surskit", "source_row_url": "https://api.tcgdex.net/v2/en/cards/me06-002"}])
            before = path.read_text()
            with self.assertRaises(SystemExit):
                main(directory, fetch=CARDS.__getitem__)
            self.assertEqual(path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
