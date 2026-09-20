from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.db import connect, init_catalog
from bootstrap.catalogue import upsert_card
from bootstrap.embeddings import build_embeddings
from bootstrap.pins import DINOV2_DIM, DINOV2_FILENAME


def _card(conn, card_id: str, image_path: str) -> None:
    upsert_card(
        conn,
        card_id=card_id,
        provider_id=card_id,
        name=card_id,
        set_id="x",
        set_name="X",
        collector_number="1",
        language="en",
        category=None,
        rarity=None,
        illustrator=None,
        variants_json="{}",
        image_path=image_path,
        has_image=1,
        cardmarket_id=None,
        cardmarket_url=None,
        cardmarket_verified=0,
        cardmarket_provenance=None,
        cardmarket_verified_at=None,
    )


def _setup(tmp_path: Path) -> Path:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / DINOV2_FILENAME).write_bytes(b"onnx")
    (tmp_path / "catalogue-version.json").write_text(
        json.dumps(
            {
                "catalogue_version": "test",
                "cards": 2,
                "missing_images": 0,
            }
        )
    )
    return tmp_path


class _FakeEmbedder:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls: list[str] = []

    def embed(self, image, preprocess_config: str) -> np.ndarray:
        del image
        self.calls.append(preprocess_config)
        vector = np.zeros(DINOV2_DIM, dtype=np.float32)
        vector[len(self.calls) % DINOV2_DIM] = 1.0
        return vector


def test_embeddings_only_compute_new_cards(tmp_path: Path, monkeypatch) -> None:
    data_dir = _setup(tmp_path)
    images = data_dir / "reference-images"
    images.mkdir()
    first = images / "a.webp"
    second = images / "b.webp"
    third = images / "c.webp"
    Image.new("RGB", (8, 8), color=(1, 2, 3)).save(first, format="WEBP")
    Image.new("RGB", (8, 8), color=(4, 5, 6)).save(second, format="WEBP")
    Image.new("RGB", (8, 8), color=(7, 8, 9)).save(third, format="WEBP")

    conn = connect(data_dir / "catalog.sqlite")
    init_catalog(conn)
    _card(conn, "en:a", str(first))
    _card(conn, "en:b", str(second))
    conn.commit()

    embedders: list[_FakeEmbedder] = []

    def factory(*args, **kwargs):
        embedder = _FakeEmbedder(*args, **kwargs)
        embedders.append(embedder)
        return embedder

    monkeypatch.setattr("bootstrap.embeddings.DinoEmbedder", factory)
    build_embeddings(data_dir, "pad", "rev")
    assert len(embedders) == 1
    assert len(embedders[0].calls) == 2

    _card(conn, "en:c", str(third))
    conn.commit()
    (data_dir / "catalogue-version.json").write_text(
        json.dumps({"catalogue_version": "test", "cards": 3, "missing_images": 0})
    )
    build_embeddings(data_dir, "pad", "rev")
    assert len(embedders) == 2
    assert len(embedders[1].calls) == 1
    ids = np.load(data_dir / "vectors" / "pad" / (data_dir / "vectors" / "pad" / "ACTIVE").read_text().strip() / "embedding_card_ids.npy")
    assert [str(item) for item in ids.tolist()] == ["en:a", "en:b", "en:c"]
