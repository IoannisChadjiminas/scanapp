"""Build immutable reference features offline; never writes to the catalogue.

A bundle's processing contract pins the CPU architecture and the OpenCV build that
extracted it: SIFT keypoints and the LANCZOS resize are not bitwise portable between
SIMD builds (x86 SSE/AVX versus Arm NEON), and the runtime only accepts features that
equal its own live extraction. A new architecture therefore gets a native rebuild,
never a relabelled bundle. The optional checks below make such a rebuild refuse the
wrong host, the wrong catalogue release, or a bundle that disagrees with another
architecture's bundle on anything except the architecture and OpenCV build.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import sqlite3
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, '/app')
from app.recognition.printing import artwork_thumbnail  # noqa: E402
from app.recognition.reference_features import (  # noqa: E402
    SIFT_PROFILES, ReferenceFeatureStore, build_reference_bundle, extract_reference, processing_contract,
)

# The only processing fields allowed to differ between two architectures' bundles.
ARCHITECTURE_FIELDS = {'architecture', 'opencv_build_sha256'}


def load_rows(data_dir):
    with sqlite3.connect((data_dir / 'catalog.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as source:
        source.row_factory = sqlite3.Row
        return [dict(row) for row in source.execute('SELECT id,image_path,rarity FROM cards')]


def subset(rows, limit):
    """Evenly spaced cards by ID, so a smoke build covers several sets and rarities."""
    ordered = sorted(rows, key=lambda r: str(r['id']))
    step = max(1, len(ordered) // limit)
    return ordered[::step][:limit]


def exported_import_ids(data_dir):
    """Import IDs recorded by export_cloud_snapshot.py in each vectors manifest."""
    ids = set()
    for path in sorted((data_dir / 'vectors').glob('*/manifest.json')):
        ids.add((json.loads(path.read_text()).get('exported_from') or {}).get('import_id'))
    return ids


def preflight(args, rows):
    machine = platform.machine()
    if args.expect_architecture and machine != args.expect_architecture:
        raise SystemExit(f'Refusing: this host is {machine}, expected {args.expect_architecture}')
    if args.expect_cards is not None and len(rows) != args.expect_cards:
        raise SystemExit(f'Refusing: catalogue has {len(rows)} cards, expected {args.expect_cards}')
    if args.expect_import_id:
        ids = exported_import_ids(args.data_dir)
        if ids != {args.expect_import_id}:
            raise SystemExit(f'Refusing: exported catalogue import IDs {sorted(map(str, ids))}, '
                             f'expected {args.expect_import_id}')


def compare_manifests(new, other, partial):
    """Same release on two architectures: everything but the architecture fields must match.

    Any other difference is listed in `problems`. `partial` allows `new` to cover a subset
    of `other`'s cards (smoke builds); the catalogue signature is then not comparable.
    """
    problems = []
    if new['schema_version'] != other['schema_version']:
        problems.append('schema_version')
    ours, theirs = new['processing'], other['processing']
    if set(ours) != set(theirs):
        problems.append(f'processing fields {sorted(set(ours) ^ set(theirs))}')
    changed = sorted(k for k in set(ours) & set(theirs) if ours[k] != theirs[k])
    if set(changed) - ARCHITECTURE_FIELDS:
        problems.append(f'processing differs beyond architecture: {sorted(set(changed) - ARCHITECTURE_FIELDS)}')
    records, base = new['records'], other['records']
    if partial:
        if not set(records) <= set(base):
            problems.append(f'{len(set(records) - set(base))} cards absent from the other bundle')
    else:
        if new['catalogue_sha256'] != other['catalogue_sha256']:
            problems.append('catalogue_sha256 (different catalogue release or image mapping)')
        if set(records) != set(base) or new['cards'] != other['cards']:
            problems.append('card coverage')
    mapping, availability, sources = [], [], []
    for card_id in sorted(set(records) & set(base)):
        a, b = records[card_id], base[card_id]
        if a['image_path'] != b['image_path'] or a['art_box'] != b['art_box']:
            mapping.append(card_id)
        elif a['available'] != b['available']:
            availability.append(card_id)
        elif a['available'] and a['source_sha256'] != b['source_sha256']:
            sources.append(card_id)
    for name, ids in (('image mapping/art box', mapping), ('availability', availability),
                      ('source image checksum', sources)):
        if ids:
            problems.append(f'{name} differs on {len(ids)} cards, e.g. {ids[:10]}')
    summary = dict(other_architecture=theirs.get('architecture'), changed_processing_fields=changed,
                   compared_cards=len(set(records) & set(base)), other_available=other['available'])
    return dict(summary, problems=problems)


def mirror_unavailable(output, manifest, other, reason):
    """Copy one explicit release decision from the other bundle: cards it marks unavailable
    with `reason` (e.g. display_only_no_vectors) become unavailable here, with that reason.

    This mirrors a curation step, not numerics; every other comparison stays strict.
    Rewrites manifest.json; the loader validates the result afterwards.
    """
    ids = sorted(cid for cid, r in other['records'].items()
                 if not r['available'] and r.get('unavailable_reason') == reason and cid in manifest['records'])
    for card_id in ids:
        record = manifest['records'][card_id]
        if record['available']:
            (output / record['filename']).unlink()
        manifest['records'][card_id] = dict(image_path=record['image_path'], art_box=record['art_box'],
                                            available=False, unavailable_reason=reason)
    manifest['available'] = sum(r['available'] for r in manifest['records'].values())
    (output / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2))
    return ids


def reject(output, summary, message):
    """Unpublish a finished bundle: without manifest.json no loader can activate it."""
    (output / 'manifest.json').rename(output / 'manifest.rejected.json')
    print(json.dumps(dict(summary, rejected=message)), flush=True)
    raise SystemExit(message + f'; manifest moved to {output / "manifest.rejected.json"}')


def native_check(store, count):
    """Re-extract a spread of available cards live and require bitwise-equal features."""
    available = [(cid, r) for cid, r in sorted(store.manifest['records'].items()) if r['available']]
    sample = available[::max(1, len(available) // count)][:count] if count else []
    deltas = []
    for card_id, record in sample:
        with Image.open(record['image_path']) as original:
            for features, contrast in SIFT_PROFILES:
                live = extract_reference(original, tuple(record['art_box']), features, contrast)
                saved = store.features(card_id, record['image_path'], tuple(record['art_box']), features, contrast)
                if (not np.array_equal(live.points, saved.points) or live.size != saved.size
                        or not np.array_equal(live.descriptors if live.descriptors is not None
                                              else np.empty((0, 128), np.float32),
                                              saved.descriptors if saved.descriptors is not None
                                              else np.empty((0, 128), np.float32))):
                    deltas.append(dict(id=card_id, profile=features))
            thumb = artwork_thumbnail(original)
            if not np.array_equal(thumb if thumb is not None else np.empty(0, np.float32),
                                  store.read(card_id, record['image_path'])['thumbnail']):
                deltas.append(dict(id=card_id, profile='thumbnail'))
    return len(sample), deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--expect-architecture', help='refuse unless platform.machine() equals this, e.g. aarch64')
    parser.add_argument('--expect-import-id', help='refuse unless the exported catalogue came from this import')
    parser.add_argument('--expect-cards', type=int, help='refuse unless the catalogue has exactly this many cards')
    parser.add_argument('--compare-manifest', type=Path,
                        help="another architecture's manifest.json for the same release")
    parser.add_argument('--mirror-unavailable', metavar='REASON',
                        help='with --compare-manifest: mark the cards the other bundle lists as unavailable '
                             'for this reason (a release curation decision) unavailable here too')
    parser.add_argument('--existing', action='store_true',
                        help='check an already built bundle in --output instead of building one')
    parser.add_argument('--native-check', type=int, default=0,
                        help='after the build, re-extract this many cards live and require bitwise equality')
    parser.add_argument('--limit', type=int,
                        help='smoke test only: build this many evenly spaced cards. The bundle is bound to '
                             'that subset and the API rejects it for the full catalogue.')
    args = parser.parse_args()
    rows = load_rows(args.data_dir)
    preflight(args, rows)
    if args.limit:
        rows = subset(rows, args.limit)
    other = json.loads(args.compare_manifest.read_text()) if args.compare_manifest else None
    if args.mirror_unavailable and other is None:
        raise SystemExit('--mirror-unavailable needs --compare-manifest')

    def progress(number, count):
        if number % 250 == 0:
            print(json.dumps({'processed': number, 'total': count}), flush=True)
    cv2.setNumThreads(1)
    started = time.perf_counter()
    if args.existing:
        manifest = json.loads((args.output / 'manifest.json').read_text())
    else:
        manifest = build_reference_bundle(rows, args.data_dir, args.output, progress, workers=args.workers)
    elapsed = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    mirrored = mirror_unavailable(args.output, manifest, other, args.mirror_unavailable) if args.mirror_unavailable else None
    # The same strict loader the API runs: contract, catalogue signature, coverage, checksums.
    # It already refuses a manifest whose architecture or OpenCV build is not this host's.
    store = ReferenceFeatureStore.load(args.output, rows)
    contract = processing_contract()
    assert manifest['processing'] == contract and contract['architecture'] == platform.machine()
    summary = dict(cards=manifest['cards'], available=manifest['available'],
                   bytes=sum(p.stat().st_size for p in args.output.iterdir()), validated=True,
                   subset=bool(args.limit), architecture=contract['architecture'],
                   opencv=contract['opencv'], opencv_build_sha256=contract['opencv_build_sha256'],
                   catalogue_sha256=manifest['catalogue_sha256'], workers=args.workers,
                   build_seconds=round(elapsed, 1),
                   cpu_seconds=round(usage.ru_utime + usage.ru_stime, 1),
                   # ru_maxrss is KiB on Linux, bytes on macOS.
                   peak_rss_mb=round(usage.ru_maxrss / (1 << 20 if sys.platform == 'darwin' else 1 << 10), 1))
    if args.existing:
        summary.update(existing=True, build_seconds=None, cpu_seconds=None, peak_rss_mb=None)
    if mirrored is not None:
        summary['mirrored_unavailable'] = dict(reason=args.mirror_unavailable, cards=mirrored)
    if other is not None:
        summary['compared'] = compare_manifests(manifest, other, partial=bool(args.limit))
        if summary['compared']['problems']:
            reject(args.output, summary, 'Bundle disagrees with the other architecture beyond the architecture fields')
    if args.native_check:
        checked, deltas = native_check(store, args.native_check)
        summary['native_check'] = dict(cards=checked, deltas=deltas)
        if deltas:
            reject(args.output, summary, 'Stored features differ from live extraction on this host')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
