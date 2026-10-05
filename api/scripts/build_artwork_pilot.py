"""Build a new local pilot artifact, leaving full-card vectors/catalogue untouched."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image

from app.config import Settings
from app.recognition.artifacts import resolve_bundle_dir, sha256_file
from app.recognition.artwork import PROFILES, SCHEMA_VERSION, crop_profile
from app.recognition.embed import DinoEmbedder


PILOT_NAMES = ("Pikachu", "ピカチュウ", "Fuecoco", "ホゲータ", "Bibarel", "ビーダル",
               "Victini", "ビクティニ", "Alakazam ex", "フーディンex", "Mew ex", "Charizard ex")
FULL_ART_RARITIES = {'ultra rare','secret rare','illustration rare','special illustration rare',
                    'full art trainer','holo rare vmax','hyper rare','character rare',
                    'character super rare','shiny ultra rare','shiny rare vmax'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--distractors', type=int, default=512)
    parser.add_argument('--rarity-coverage', action='store_true',
                        help='Expand by generic EN/JA rarity metadata, not test-photo IDs')
    args = parser.parse_args()
    if not 0 <= args.distractors <= 5000:
        parser.error('Pilot distractor limit must be between 0 and 5000')
    settings = Settings(data_dir=Path('/data'), use_ocr=False, store_captures=False)
    root = settings.images_dir.resolve()
    catalog = sqlite3.connect('file:/data/catalog.sqlite?mode=ro', uri=True)
    catalog.row_factory = sqlite3.Row
    rows = [dict(r) for r in catalog.execute('SELECT * FROM cards ORDER BY id')]
    catalog.close()
    def selected(card):
        return card['name'] in PILOT_NAMES or (args.rarity_coverage and card['language'] in {'en','ja'}
            and str(card['rarity'] or '').casefold() in FULL_ART_RARITIES)
    seed = [r for r in rows if selected(r)]
    rest = [r for r in rows if not selected(r) and r['image_path']]
    random.Random(20261002).shuffle(rest)
    chosen = seed + rest[:args.distractors]
    output = args.output.resolve()
    if output.is_relative_to(settings.data_dir.resolve()):
        parser.error('Output must be separate from the existing data volume')
    output.mkdir(parents=True, exist_ok=False)
    model = DinoEmbedder(str(settings.dinov2_path), 1, 1)
    base_dir = resolve_bundle_dir(settings.vectors_dir)
    base = json.loads((base_dir / 'manifest.json').read_text())
    records, vectors, skipped, cached = [], [], [], {}
    for count, card in enumerate(chosen, start=1):
        path = Path(str(card['image_path'] or '')).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            skipped.append({'card_id': card['id'], 'reason': 'reference_unavailable'})
            continue
        try:
            digest = sha256_file(path)
            with Image.open(path) as source:
                image = source.convert('RGB')
            for profile in PROFILES:
                key = (digest, profile)
                vector = cached.get(key)
                if vector is None:
                    vector = model.embed(crop_profile(image, profile), settings.preprocess_config)
                    cached[key] = vector
                records.append({'card_id': card['id'], 'profile': profile,
                                'language': card['language'], 'name': card['name'],
                                'set_name': card['set_name'], 'collector_number': card['collector_number'],
                                'reference_sha256': digest})
                vectors.append(vector)
        except (OSError, ValueError) as exc:
            skipped.append({'card_id': card['id'], 'reason': type(exc).__name__})
        if count % 50 == 0:
            print(json.dumps({'progress': count, 'selected': len(chosen), 'regions': len(records)}), flush=True)
    if not records:
        raise RuntimeError('No usable pilot references')
    np.save(output / 'embeddings.npy', np.asarray(vectors, dtype=np.float32))
    (output / 'records.json').write_text(json.dumps(records, ensure_ascii=False))
    manifest = {'schema_version': SCHEMA_VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                'preprocess_config': settings.preprocess_config,
                'model_sha256': sha256_file(settings.dinov2_path),
                'base_embeddings_sha256': base['embeddings_sha256'],
                'base_ids_sha256': base['ids_sha256'],
                'profiles': {k: list(v) for k, v in PROFILES.items()},
                'indexed_cards': len({r['card_id'] for r in records}), 'indexed_regions': len(records),
                'embeddings_sha256': sha256_file(output / 'embeddings.npy'),
                'records_sha256': sha256_file(output / 'records.json'),
                'pilot_names': list(PILOT_NAMES), 'random_distractors_requested': args.distractors,
                'rarity_selection': sorted(FULL_ART_RARITIES) if args.rarity_coverage else [],
                'scope': 'rarity-expanded subset, not full catalogue' if args.rarity_coverage else 'pilot subset, not full-catalogue accuracy', 'seed': 20261002,
                'profile_status': 'explicit crop hypotheses, not validated layout classification',
                'skipped': skipped}
    # Manifest is the completion marker; an interrupted build cannot load.
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({'completed': str(output), 'cards': manifest['indexed_cards'],
                      'regions': len(records), 'skipped': len(skipped)}), flush=True)


if __name__ == '__main__':
    main()
