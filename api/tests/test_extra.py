from __future__ import annotations

import json
from pathlib import Path

from bootstrap.extra import import_extra_cards


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
