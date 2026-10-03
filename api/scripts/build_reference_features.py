"""Build immutable reference features offline; never writes to the catalogue."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.reference_features import build_reference_bundle, ReferenceFeatureStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    with sqlite3.connect((args.data_dir / 'catalog.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as source:
        source.row_factory = sqlite3.Row
        rows = [dict(row) for row in source.execute('SELECT id,image_path,rarity FROM cards')]
    def progress(number, count):
        if number % 250 == 0:
            print(json.dumps({'processed': number, 'total': count}), flush=True)
    cv2.setNumThreads(1)
    manifest = build_reference_bundle(rows, args.data_dir, args.output, progress, workers=args.workers)
    ReferenceFeatureStore.load(args.output, rows)
    print(json.dumps({'cards': manifest['cards'], 'available': manifest['available'],
                      'bytes': sum(p.stat().st_size for p in args.output.iterdir()),
                      'validated': True}), flush=True)


if __name__ == '__main__':
    main()
