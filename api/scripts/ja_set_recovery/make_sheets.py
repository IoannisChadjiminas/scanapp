"""Contact sheets for the eye check: each image next to an enlarged footer, with its row label.

    python3 -I make_sheets.py OUT_DIR LABEL_JSON [PER_SHEET]

LABEL_JSON is a list of {"label": "SAf 001 ...", "file": "path/to/image.png"}. Writes
OUT_DIR/sheet-NN.jpg, PER_SHEET (default 8) cards per sheet in two rows. Look at each sheet and
compare the printed name and number in the picture with the label. The sheet is a viewing aid
only: it decides nothing, and the photos never go into git.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ["/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
         "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]


def font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main(out_dir, label_path, per_sheet=8):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items = json.loads(Path(label_path).read_text())
    cell_w, card_h, foot_h, head = 368, 512, 80, 28
    cols = 4
    per_sheet = int(per_sheet)
    label_font = font(20)
    for sheet, start in enumerate(range(0, len(items), per_sheet), 1):
        chunk = items[start:start + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * cell_w, rows * (head + card_h + foot_h)), "white")
        draw = ImageDraw.Draw(canvas)
        for i, item in enumerate(chunk):
            x, y = (i % cols) * cell_w, (i // cols) * (head + card_h + foot_h)
            draw.text((x + 4, y + 2), item["label"], fill="black", font=label_font)
            with Image.open(item["file"]) as img:
                img = img.convert("RGB")
                card = img.resize((cell_w, card_h))
                canvas.paste(card, (x, y + head))
                w, h = img.size
                foot = img.crop((0, int(h * 0.93), int(w * 0.5), h)).resize((cell_w, foot_h))
                canvas.paste(foot, (x, y + head + card_h))
        canvas.save(out / f"sheet-{sheet:02d}.jpg", quality=85)
    print(json.dumps({"sheets": (len(items) + per_sheet - 1) // per_sheet, "cards": len(items)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
