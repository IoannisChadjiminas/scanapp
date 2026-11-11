"""OCR each reference image that would get a vector and record its print-language evidence (step 5a).

    python3 scan_reference_print_language.py RELEASE_DIR FEATURE_ROWS_JSON[,...] MODELS_DIR OUT_JSONL [SHARD/SHARDS]

RELEASE_DIR/held.json lists the cards that get vectors. Their image paths come from the
feature-rows / updates files (id → image_path, "/data/..." paths as on staging). For each card
it records the OCR lines, the kana and kanji counts, the English phrases and rule words
(app.recognition.language), and english_print_evidence. Nothing is decided here: the hold list
is chosen from this file and checked by eye.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "/app")
from app.recognition.language import EN_PHRASES, EN_RULE_WORDS, english_print_evidence  # noqa: E402
from app.recognition.ocr import CardOcr  # noqa: E402


def main(release_dir, rows_files, models, out, shard="0/1"):
    k, n = map(int, shard.split("/"))
    held = json.loads((Path(release_dir) / "held.json").read_text())["vectors_added"]
    paths = {}
    for f in rows_files.split(","):
        for r in json.loads(Path(f).read_text()):
            paths[r["id"]] = r["image_path"]
    ids = [h["id"] for h in held][k::n]
    m = Path(models)
    ocr = CardOcr(str(m / "PP-OCRv6_det_small.onnx"), str(m / "PP-OCRv6_rec_small.onnx"),
                  str(m / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"), 2, 1)
    with open(out, "w") as fh:
        for cid in ids:
            with Image.open(paths[cid]) as im:
                result = ocr.engine(np.asarray(im.convert("RGB")))
            lines = [str(t) for t in (getattr(result, "txts", None) or ())]
            blob = "\n".join(lines)
            low = blob.casefold()
            words = set(__import__("re").findall(r"[a-z']+", low))
            fh.write(json.dumps({
                "id": cid, "image_path": paths[cid], "lines": lines,
                "kana": sum(1 for c in blob if 0x3040 <= ord(c) <= 0x30FF),
                "kanji": sum(1 for c in blob if 0x4E00 <= ord(c) <= 0x9FFF),
                "en_phrases": [p for p in EN_PHRASES if p in low],
                "en_rule_words": sorted(words & EN_RULE_WORDS),
                "english_print_evidence": english_print_evidence(lines)}, ensure_ascii=False) + "\n")
            fh.flush()


if __name__ == "__main__":
    main(*sys.argv[1:6])
