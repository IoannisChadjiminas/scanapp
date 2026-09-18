from __future__ import annotations

from pathlib import Path

import torch
from transformers import Dinov2Model

from bootstrap.pins import DINOV2_DIM, DINOV2_FILENAME, DINOV2_INPUT_SIZE, DINOV2_MODEL_ID


class _Wrapper(torch.nn.Module):
    def __init__(self, model: Dinov2Model) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        hidden = self.model(pixel_values=pixel_values).last_hidden_state
        cls_token = hidden[:, 0]
        return torch.nn.functional.normalize(cls_token, dim=-1)


def export_dinov2(models_dir: Path) -> dict[str, str | int]:
    dest = models_dir / DINOV2_FILENAME
    if dest.exists():
        print(f"reuse {dest}")
        return {
            "path": str(dest),
            "model_id": DINOV2_MODEL_ID,
            "revision": "cached",
            "dim": DINOV2_DIM,
        }
    print(f"load {DINOV2_MODEL_ID}")
    model = Dinov2Model.from_pretrained(DINOV2_MODEL_ID)
    revision = getattr(model.config, "_commit_hash", None) or "unknown"
    wrapper = _Wrapper(model).eval()
    dummy = torch.randn(1, 3, DINOV2_INPUT_SIZE, DINOV2_INPUT_SIZE)
    print(f"export {dest}")
    torch.onnx.export(
        wrapper,
        dummy,
        dest,
        input_names=["pixel_values"],
        output_names=["embedding"],
        opset_version=17,
        dynamo=False,
    )
    return {
        "path": str(dest),
        "model_id": DINOV2_MODEL_ID,
        "revision": str(revision),
        "dim": DINOV2_DIM,
    }
