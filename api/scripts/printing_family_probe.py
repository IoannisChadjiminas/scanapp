"""Would the printing family reach the expected card from what the scanner retrieved?

Read-only. For each retrieved card (a saved scan response or a list of card ids),
prints its species, its artwork correlation with the expected card's reference,
and whether the expected card is in its printing family by exact name (today)
and by species (PRINTING_FAMILY_SPECIES). Prints card ids and names only.

    cd api && .venv/bin/python scripts/printing_family_probe.py \
        --catalog <data>/catalog.sqlite --data-dir <data> \
        --expected ja:PMCG1-021 <saved-response.json | card ids...>

The reference images must be below <data>/reference-images, as on the server.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image

from app.config import get_settings
from app.recognition.printing import MIN_REFERENCE_CORRELATION, ReferencePrintingIndex, artwork_thumbnail
from app.recognition.rank import pokedex_number


def retrieved_ids(sources: list[str]) -> list[str]:
    if len(sources) == 1 and Path(sources[0]).is_file():
        data = json.loads(Path(sources[0]).read_text(encoding='utf-8'))
        rows = data if isinstance(data, list) else (
            data.get('visual_top20') or data.get('candidates') or data.get('ranked') or [])
        return [row if isinstance(row, str) else row['card_id'] for row in rows]
    return sources


def thumbnail(root: Path, row) -> object:
    path = Path(str(row['image_path'] or '')).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    with Image.open(path) as image:
        return artwork_thumbnail(image)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--catalog', required=True)
    ap.add_argument('--data-dir', required=True, type=Path)
    ap.add_argument('--expected', required=True)
    ap.add_argument('retrieved', nargs='+', help='saved response JSON, or card ids in rank order')
    args = ap.parse_args()

    catalog = sqlite3.connect(f'file:{args.catalog}?mode=ro', uri=True)
    catalog.row_factory = sqlite3.Row
    cards = lambda ids: {r['id']: r for r in catalog.execute(
        f"SELECT * FROM cards WHERE id IN ({','.join('?' for _ in ids)})", ids)}
    ids = retrieved_ids(args.retrieved)
    rows = cards([*ids, args.expected])
    root = (args.data_dir / 'reference-images').resolve()
    expected = rows.get(args.expected)
    if expected is None:
        sys.exit(f'{args.expected} is not in the catalogue')
    expected_art = thumbnail(root, expected)
    print(json.dumps({'expected': args.expected, 'name': expected['name'],
                      'species': pokedex_number(expected['name']),
                      'reference_probe': expected_art is not None}, ensure_ascii=False))

    settings = get_settings()
    index = ReferencePrintingIndex(args.data_dir)
    summary = {'retrieved': len(ids), 'reaches_by_name': [], 'reaches_by_species': []}
    for rank, card_id in enumerate(ids, 1):
        row = rows.get(card_id)
        if row is None:
            print(json.dumps({'rank': rank, 'card_id': card_id, 'missing': True}))
            continue
        art = thumbnail(root, row)
        top = {'card_id': card_id, 'name': row['name'], 'language': row['language']}
        reach = {}
        for label, on in (('by_name', False), ('by_species', True)):
            settings.printing_family_species = on
            members, incomplete = index.family(catalog, top)
            reach[label] = any(m['id'] == args.expected for m in members)
            reach[label + '_incomplete'] = incomplete
            if reach[label]:
                summary['reaches_' + label].append(rank)
        print(json.dumps({
            'rank': rank, 'card_id': card_id, 'name': row['name'],
            'species': pokedex_number(row['name']),
            'art_correlation': (round(float(art @ expected_art), 3)
                                if art is not None and expected_art is not None else None),
            'floor': MIN_REFERENCE_CORRELATION, **reach}, ensure_ascii=False))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
