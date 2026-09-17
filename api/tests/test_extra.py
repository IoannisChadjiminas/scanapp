from __future__ import annotations

import json
from pathlib import Path

from bootstrap.extra import import_extra_cards
from app.cardmarket import url_for_row
from app.db import connect


def test_import_extra_cards(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "extra"
    source.mkdir()
    image = source / "demo.jpg"
    image.write_bytes(b"\xff\xd8\xff\xd9")
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "extra-demo",
                        "name": "Demo",
                        "set_id": "x",
                        "set_name": "Extra",
                        "collector_number": "1",
                        "language": "en",
                        "file": "demo.jpg",
                        "cardmarket_expansion": "Base-Set",
                        "cardmarket_set_code": "BS",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("EXTRA_CARDS_DIR", str(source))
    data_dir = tmp_path / "data"
    imported = import_extra_cards(data_dir)
    assert imported == 1
    dest = data_dir / "reference-images" / "extra-demo.jpg"
    assert dest.is_file()
    coverage = json.loads((data_dir / "catalogue-version.json").read_text())
    assert coverage["extra_cards"] == 1
    assert coverage["catalogue_version"].endswith("+extra1")
    row = connect(data_dir / "catalog.sqlite").execute(
        "SELECT * FROM cards WHERE id = 'extra-demo'"
    ).fetchone()
    assert row is not None
    assert (
        row["cardmarket_url"]
        == "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Demo-BS1"
    )
    assert int(row["cardmarket_verified"] or 0) == 0
    assert row["cardmarket_provenance"] == "generated-singles"
    assert url_for_row(row) is None
