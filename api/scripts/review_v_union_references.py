"""Full-panel identity review supplement for four-part V-UNION cards."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[2] / 'data/image-recovery/20261002-official/en-additional'
rows = {r['id']: r for r in json.loads((root / 'discovery.json').read_text())['records']}
sheet = Image.new('RGB', (1000, 1500), 'white')
draw = ImageDraw.Draw(sheet)
for i, number in enumerate(range(287, 291)):
    row = rows[f'en:swshp-SWSH{number}']
    x, y = (i % 2) * 500, (i // 2) * 750
    draw.text((x + 5, y + 5), row['id'], fill='black')
    with Image.open(root / 'images' / row['file']) as im:
        im = im.convert('RGB')
        sheet.paste(im.resize((490, round(im.height * 490 / im.width))), (x + 5, y + 30))
sheet.save(root / 'review/v-union-full.png')
with Image.open(root / 'images' / rows['en:svp-211']['file']) as im:
    w, h = im.size
    strip = im.crop((0, int(h * .91), int(w * .48), h))
    strip.resize((900, round(strip.height * 900 / strip.width))).save(root / 'review/gothitelle-number.png')
