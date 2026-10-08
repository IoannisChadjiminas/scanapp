import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.card_images import display_image_url
from app.visual_aliases import identity_sha256, validate_visual_aliases, visual_image_owner


class VisualAliasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "original.jpg"
        self.image.write_bytes(b"verified source")
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE cards(id,provider_id,name,set_id,set_name,collector_number,language,category,illustrator,image_path,has_image,remote_image_url)")
        self.db.execute("INSERT INTO cards VALUES ('alias','alias','Unown','exu','Collection','%3F','en','Pokemon',NULL,NULL,0,NULL)")
        self.db.execute("INSERT INTO cards VALUES ('native','native','Unown [?]','ex10','Unseen Forces','?','en','Pokemon',NULL,?,1,NULL)", (str(self.image),))
        self.alias = self.row("alias")
        self.owner = self.row("native")
        self.contract = {"schema_version": 1, "records": [{
            "alias_id": "alias", "owner_id": "native",
            "alias_identity_sha256": identity_sha256(self.alias),
            "owner_identity_sha256": identity_sha256(self.owner),
            "source_sha256": hashlib.sha256(self.image.read_bytes()).hexdigest(),
        }]}

    def row(self, cid):
        return self.db.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()

    def validate(self, contract=None, indexed_ids=("native",)):
        return validate_visual_aliases(self.db, contract or self.contract,
                                       indexed_ids=indexed_ids, image_root=self.root)

    def test_verified_alias_delivers_local_original_without_identity_merge(self):
        before = [tuple(r) for r in self.db.execute("SELECT * FROM cards")]
        registry = self.validate()
        catalog = SimpleNamespace(visual_image_aliases=registry)
        self.assertEqual(visual_image_owner(self.alias, catalog)["id"], "native")
        self.assertEqual(display_image_url(self.alias, catalog), "/api/v1/cards/alias/image")
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM cards")], before)
        with self.assertRaises(TypeError):
            registry["alias"] = {}

    def test_unregistered_alias_has_no_image(self):
        self.assertIsNone(display_image_url(self.alias))

    def test_literal_percent_encoded_id_is_preserved_in_image_url(self):
        catalog = SimpleNamespace(visual_image_aliases={"en:exu-%3F": self.owner})
        self.assertEqual(display_image_url({"id": "en:exu-%3F"}, catalog),
                         "/api/v1/cards/en:exu-%253F/image")

    def test_source_change_rejected(self):
        self.image.write_bytes(b"different print")
        with self.assertRaisesRegex(ValueError, "source checksum"):
            self.validate()

    def test_missing_source_rejected(self):
        self.image.unlink()
        with self.assertRaisesRegex(ValueError, "source missing"):
            self.validate()

    def test_identity_change_rejected(self):
        self.db.execute("UPDATE cards SET illustrator='different artist' WHERE id='native'")
        with self.assertRaisesRegex(ValueError, "identity checksum"):
            self.validate()

    def test_foreign_language_rejected(self):
        self.db.execute("UPDATE cards SET language='ja' WHERE id='native'")
        with self.assertRaisesRegex(ValueError, "language or collector"):
            self.validate()

    def test_different_collector_rejected(self):
        self.db.execute("UPDATE cards SET collector_number='A' WHERE id='native'")
        with self.assertRaisesRegex(ValueError, "language or collector"):
            self.validate()

    def test_missing_owner_rejected(self):
        self.db.execute("DELETE FROM cards WHERE id='native'")
        with self.assertRaisesRegex(ValueError, "missing card"):
            self.validate()

    def test_unindexed_owner_rejected(self):
        with self.assertRaisesRegex(ValueError, "indexed owner"):
            self.validate(indexed_ids=())

    def test_indexed_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "indexed owner"):
            self.validate(indexed_ids=("native", "alias"))

    def test_existing_image_cannot_be_overridden(self):
        self.db.execute("UPDATE cards SET remote_image_url='https://example.test/original.jpg' WHERE id='alias'")
        with self.assertRaisesRegex(ValueError, "replace an existing image"):
            self.validate()

    def test_duplicate_alias_rejected(self):
        contract = copy.deepcopy(self.contract)
        contract["records"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.validate(contract)

    def test_chain_and_cycle_rejected(self):
        contract = copy.deepcopy(self.contract)
        contract["records"][0]["owner_id"] = "alias"
        with self.assertRaisesRegex(ValueError, "chain"):
            self.validate(contract)

    def test_source_outside_root_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside image root"):
            validate_visual_aliases(self.db, self.contract, indexed_ids=("native",),
                                    image_root=self.root / "other")


if __name__ == "__main__":
    unittest.main()
