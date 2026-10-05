"""Create legible identity-region sheets from unverified official references."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(exist_ok=False)
    rows = {r['id']: r for r in json.loads(args.discovery.read_text())['records']}
    pending = [rows[r['card_id']] for r in json.loads(args.audit.read_text())['records'] if r['status'] == 'manual_review']
    index = []
    for batch in range(0, len(pending), 12):
        page = Image.new('RGB', (1500, 1240), 'white')
        draw = ImageDraw.Draw(page)
        group = pending[batch:batch + 12]
        for i, row in enumerate(group):
            x, y = (i % 3) * 500, (i // 3) * 310
            draw.text((x + 5, y + 5), row['id'] + ' | ' + row['name'], fill='black')
            with Image.open(args.discovery.parent / 'images' / row['file']) as im:
                im = im.convert('RGB')
                w, h = im.size
                header = im.crop((0, 0, w, int(.20 * h)))
                footer = im.crop((0, int(.82 * h), w, h))
                for crop, offset in [(header, 30), (footer, 175)]:
                    crop = crop.resize((490, round(crop.height * 490 / crop.width)))
                    page.paste(crop, (x + 5, y + offset))
        filename = f'review-{batch // 12:02}.png'
        page.save(args.output / filename)
        index.append({'file': filename, 'card_ids': [r['id'] for r in group]})
    (args.output / 'index.json').write_text(json.dumps(index, indent=2))


if __name__ == '__main__':
    main()
