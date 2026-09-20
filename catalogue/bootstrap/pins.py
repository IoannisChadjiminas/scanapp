from __future__ import annotations

# Pinned RapidOCR ONNX artifacts (package rapidocr==3.4.0, registry v3.9.2).
RAPIDOCR_MODELS = {
    "PP-OCRv6_det_small.onnx": {
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx",
        "sha256": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    },
    "PP-OCRv6_rec_small.onnx": {
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/rec/PP-OCRv6_rec_small.onnx",
        "sha256": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    },
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": {
        "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "sha256": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    },
}

DINOV2_MODEL_ID = "facebook/dinov2-small"
DINOV2_FILENAME = "dinov2_small.onnx"
DINOV2_INPUT_SIZE = 224
DINOV2_DIM = 384
TCGDEX_BASE = "https://api.tcgdex.net/v2"
TCGDEX_ASSETS = "https://assets.tcgdex.net"
TPC_BASE = "https://www.pokemon-card.com"
