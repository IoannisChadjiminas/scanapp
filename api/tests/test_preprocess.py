from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.config import Settings
from app.recognition.artifacts import ArtifactError, load_snapshot
from app.recognition.preprocess import MODEL_SIZE, prepare_full_card, to_nchw


def test_pad_preserves_aspect_ratio() -> None:
    image = Image.new("RGB", (100, 200), color=(12, 80, 160))
    prepared = prepare_full_card(image, "pad")
    assert prepared.size == (MODEL_SIZE, MODEL_SIZE)
    array = np.asarray(prepared)
    # Letterbox bars should exist on the left/right for a tall card.
    assert array[:, 0].mean() < 5
    assert array[:, -1].mean() < 5
    assert array[MODEL_SIZE // 2, MODEL_SIZE // 2].mean() > 20


def test_square_resizes_without_crop() -> None:
    image = Image.new("RGB", (80, 160), color=(200, 10, 10))
    prepared = prepare_full_card(image, "square")
    assert prepared.size == (MODEL_SIZE, MODEL_SIZE)
    # Corners come from the original image, not padding.
    assert np.asarray(prepared)[0, 0, 0] > 100


def test_nchw_normalization_shape() -> None:
    image = Image.new("RGB", (224, 224), color=(128, 128, 128))
    tensor = to_nchw(image)
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == np.float32


def test_vector_alignment_rejects_mismatch(tmp_path: Path) -> None:
    embeddings = np.random.rand(3, 384).astype(np.float32)
    ids = np.array(["a", "b"])
    vectors = tmp_path / "vectors" / "pad"
    vectors.mkdir(parents=True)
    np.save(vectors / "embeddings.npy", embeddings)
    np.save(vectors / "embedding_card_ids.npy", ids)
    (vectors / "manifest.json").write_text(
        '{"preprocess_config":"pad","use_ocr":true,"catalogue_version":"x",'
        '"model_revision":"r","embedding_dim":384}'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "dinov2_small.onnx").write_bytes(b"not-a-model")
    settings = Settings(data_dir=tmp_path, preprocess_config="pad")
    try:
        load_snapshot(settings)
        raise AssertionError("expected mismatch")
    except ArtifactError as exc:
        assert "does not match" in str(exc)
