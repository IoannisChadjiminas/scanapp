from __future__ import annotations

import re
from pathlib import Path

_JS_PATH = Path(__file__).resolve().parents[1] / "extension" / "lib" / "listing-image.js"


def listing_image_helpers() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    return re.sub(r"^export ", "", text, flags=re.M).strip() + "\n"
