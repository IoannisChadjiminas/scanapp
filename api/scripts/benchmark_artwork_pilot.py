"""Paired local artwork pilot: public physical photos versus catalogue controls.

No network, no catalogue writes, no third-party image redistribution. Raw photos
exercise automatic detection with language=auto. Manually annotated artwork
patches are an oracle-assisted diagnostic, not raw-camera end-to-end accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import io
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
import numpy as np
from app.config import Settings
from app.db import init_results
from app.recognition.artifacts import sha256_file
from app.recognition.artwork import ArtworkIndex
from app.recognition.pipeline import recognize_bytes
from app.recognition.printing import ART_BOX, printing_key
from benchmark_printing_crops import FIXTURES, crop_image, load_readonly_runtime


def run_probe(payload, *, runtime, settings, catalog, results, truth, skip_detect, language):
    response = recognize_bytes(payload, settings=settings, runtime=runtime,
        catalog=catalog, results=results, session_id='artwork-pilot',
        skip_detect=skip_detect, language=language, store_capture=False)
    row = results.execute('SELECT combined_ranking_json,ocr_json,visual_ranking_json FROM scans WHERE id=?',
                          (response.id,)).fetchone()
    ranking, evidence = json.loads(row[0]), json.loads(row[1])
    visual = json.loads(row[2])
    top = ranking[0] if ranking else None
    top_correct = bool(top and printing_key(top) == printing_key(truth))
    returned = response.printing_review.plausible_printings if response.printing_review else response.suggestions
    recalled = any((p.set_name, p.collector_number, p.language) ==
                   (truth['set_name'], truth['collector_number'], truth['language']) for p in returned)
    return {'status': response.status.value, 'top_id': top['card_id'] if top else None,
            'top_correct': top_correct, 'candidate_recalled': recalled,
            'automatic_wrong_printing': response.status.value == 'matched' and not top_correct,
            'automatic_claim': response.status.value == 'matched',
            'suggestions': [p.card_id for p in response.suggestions],
            'printing_choices': [p.card_id for p in returned],
            'top_visual_score': top['visual_score'] if top else None,
            'top_artwork_score': top.get('artwork_score') if top else None,
            'retrieved_via': top.get('retrieved_via') if top else None,
            'local_artwork_matches': evidence.get('local_artwork_matches', []),
            'artwork_retrieval': evidence.get('artwork_retrieval', []),
            'frame_selection': evidence.get('frame_selection', {}),
            'boundary_recovery': evidence.get('boundary_recovery', {}),
            'frame_detected': evidence.get('frame_detected'),
            'query_size': evidence.get('query_size'),
            'identity_evidence': {k: top.get(k) for k in ('collector_conflict','structured_collector_conflict','strong_name_conflict','language_conflict')} if top else {},
            'detected_language': evidence.get('detected_language'),
            'ocr_hits': evidence.get('hits', []),
            'framing_review_supported': evidence.get('framing_review_supported',False),
            'metadata_candidate_ids': evidence.get('metadata_candidate_ids', []),
            'full_shortlist_printing_recall': any(printing_key(r) == printing_key(truth)
                for r in visual if 'full_card' in r.get('retrieved_via',[])),
            'artwork_shortlist_printing_recall': any(printing_key(r) == printing_key(truth)
                for r in visual if 'artwork' in r.get('retrieved_via',[])),
            'ocr': response.ocr.model_dump(mode='json'),
            'grading': response.grading.model_dump(mode='json'),
            'confidence': response.confidence.model_dump(mode='json') if response.confidence else None,
            'best_match': response.best_match.model_dump(mode='json') if response.best_match else None,
            'alternatives': [p.model_dump(mode='json') for p in response.alternatives],
            'match_state': response.match_state,
            'message': response.message, 'timings_ms': response.timings_ms,
            'versions': response.versions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-dir', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--artwork-dir', type=Path,
                        help='Reuse a frozen artwork artifact without rebuilding it')
    parser.add_argument('--photos-only', action='store_true',
                        help='Skip reference controls and manually annotated art patches; retain negative controls')
    parser.add_argument('--baseline', type=Path,
                        help='Frozen completed photo report: compare its enabled results with current enabled code')
    parser.add_argument('--only', action='append', default=[],
                        help='Diagnostic subset photo ID; repeatable. Full audit still required before selecting a revision.')
    args = parser.parse_args()
    settings = Settings(data_dir=Path('/data'), catalogue_backend='sqlite',
                        artwork_bundle_dir=None, enable_matched=True, store_captures=False)
    source = sqlite3.connect('file:/data/catalog.sqlite?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:')
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    catalog.execute('PRAGMA query_only=ON')
    runtime = load_readonly_runtime(settings, catalog)
    index = ArtworkIndex.load(args.artwork_dir or args.pilot_dir / 'index', snapshot=runtime.snapshot,
        model_path=settings.dinov2_path,
        known_ids={r[0] for r in catalog.execute('SELECT id FROM cards')},
        known_languages={r[0]: r[1] or 'en' for r in catalog.execute('SELECT id,language FROM cards')})
    results = sqlite3.connect(':memory:')
    results.row_factory = sqlite3.Row
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('artwork-pilot','test','test')")
    results.commit()
    reference_hashes = {r['reference_sha256'] for r in index.records}
    labels = json.loads(args.sources.read_text())['photos']
    parent_count = len(labels)
    if args.only:
        if not set(args.only) <= {p['id'] for p in labels}:
            raise ValueError('Unknown diagnostic subset photo ID')
        labels = [p for p in labels if p['id'] in set(args.only)]
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    if baseline:
        old = baseline['summary']
        if (not args.photos_only or old['source_labels_sha256'] != sha256_file(args.sources)
            or old['full_index_rows'] != len(runtime.snapshot.card_ids)
            or old['artwork_manifest']['base_embeddings_sha256'] != index.manifest['base_embeddings_sha256']
            or old['artwork_manifest']['base_ids_sha256'] != index.manifest['base_ids_sha256']
            or old['artwork_manifest']['model_sha256'] != index.manifest['model_sha256']
            or old['settings'] != runtime.threshold_config()):
            raise ValueError('Baseline labels, full snapshot, model or decision thresholds changed')
        old_cases = {(c['name'], c['condition'], c['group']): c for c in baseline['cases']}
        old_names = {c['name'] for c in baseline['cases'] if c['condition']=='raw_photo'}
        selected_names = {p['id'] for p in labels}
        if (not selected_names <= old_names or (not args.only and old_names != selected_names)):
            raise ValueError('Baseline sample does not match selected photos')
    downloads = {r['id']: r for r in json.loads((args.pilot_dir / 'photos/downloads.json').read_text())['photos']}
    cases = []
    seen_photo_hashes = set()
    # Validate the complete frozen sample before evaluating any image.
    for photo in labels:
        if photo['review_status'] != 'visually_verified':
            raise ValueError('Photo labels require independent visual review')
        record = downloads[photo['id']]
        if record['download_status'] != 'downloaded':
            raise ValueError('Every selected photo must be downloaded')
        digest = sha256_file(args.pilot_dir / 'photos' / (photo['id'] + '.jpg'))
        if digest != record['sha256'] or digest in reference_hashes or digest in seen_photo_hashes:
            raise ValueError('Photo checksum mismatch, duplicate bytes or exact-byte pilot reference overlap')
        seen_photo_hashes.add(digest)
        if not catalog.execute('SELECT 1 FROM cards WHERE id=?', (photo['expected_card_id'],)).fetchone():
            raise ValueError('Photo truth missing from catalogue: ' + photo['expected_card_id'])

    def paired(payload, *, truth, group, condition, name, skip_detect, language, provenance=None):
        if baseline:
            frozen = old_cases[(name, condition, group)]
            if frozen['expected_id'] != truth['id']:
                raise ValueError('Baseline truth changed')
            before = frozen['after']
        else:
            runtime.artwork_index = None
            before = run_probe(payload, runtime=runtime, settings=settings, catalog=catalog,
                               results=results, truth=truth, skip_detect=skip_detect, language=language)
        runtime.artwork_index = index
        after = run_probe(payload, runtime=runtime, settings=settings, catalog=catalog,
                          results=results, truth=truth, skip_detect=skip_detect, language=language)
        case = {'name': name, 'group': group, 'condition': condition,
                'expected_id': truth['id'], 'before': before, 'after': after,
                'truth_in_artwork_pilot': any(r['card_id'] == truth['id'] for r in index.records),
                'provenance': provenance}
        cases.append(case)
        print(json.dumps({'case': case}), flush=True)

    for photo in labels:
        if photo['review_status'] != 'visually_verified':
            raise ValueError('Photo labels require independent visual review')
        record = downloads[photo['id']]
        if record['download_status'] != 'downloaded':
            print(json.dumps({'unavailable': photo['id']}), flush=True)
            continue
        # Never follow downloaded absolute paths from another machine/container.
        path = args.pilot_dir / 'photos' / (photo['id'] + '.jpg')
        digest = sha256_file(path)
        if digest != record['sha256'] or digest in reference_hashes:
            raise ValueError('Photo checksum mismatch or exact-byte reference overlap')
        truth = dict(catalog.execute('SELECT * FROM cards WHERE id=?', (photo['expected_card_id'],)).fetchone())
        provenance = {'page_url': photo['page_url'], 'image_url': photo['image_url'],
                      'sha256': digest, 'conditions': photo['conditions'],
                      'label': photo['visible_label'], 'exact_byte_pilot_reference_overlap': False,
                      'layout': photo.get('layout'), 'language': truth['language'],
                      'catalogue_warning': photo.get('catalogue_warning')}
        paired(path.read_bytes(), truth=truth, group='physical_photo', condition='raw_photo',
               name=photo['id'], skip_detect=False, language='auto', provenance=provenance)
        if photo.get('manual_art_box') and not args.photos_only:
            with Image.open(path) as original:
                patch = crop_image(original.convert('RGB'), tuple(photo['manual_art_box']))
            payload = io.BytesIO()
            patch.save(payload, format='JPEG', quality=90)
            paired(payload.getvalue(), truth=truth, group='physical_photo',
                   condition='manually_annotated_art_patch', name=photo['id'], skip_detect=True,
                   language='auto', provenance={**provenance, 'manual_art_box': photo['manual_art_box']})
    for card_id in (() if args.photos_only else FIXTURES):
        truth = dict(catalog.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone())
        with Image.open(truth['image_path']) as original:
            image = original.convert('RGB')
        for condition, box in (('full_reference', (0,0,1,1)), ('reference_art_crop', ART_BOX)):
            payload = io.BytesIO()
            crop_image(image, box).save(payload, format='JPEG', quality=90)
            paired(payload.getvalue(), truth=truth, group='synthetic_control', condition=condition,
                   name=card_id, skip_detect=True, language=truth['language'])
    negatives = []
    for name,pixels in (
        ('blank',np.full((700,500,3),240,dtype=np.uint8)),
        ('noise',np.random.default_rng(20261002).integers(0,255,(700,500,3),dtype=np.uint8))):
        payload=io.BytesIO()
        Image.fromarray(pixels).save(payload,format='JPEG',quality=90)
        outputs={}
        for label,enabled in (('before',False),('after',True)):
            if baseline and label == 'before':
                outputs[label] = next(n['after'] for n in baseline['negatives'] if n['name']==name)
                continue
            runtime.artwork_index=index if enabled else None
            response=recognize_bytes(payload.getvalue(),settings=settings,runtime=runtime,
                catalog=catalog,results=results,session_id='artwork-pilot',
                language='auto',skip_detect=True,store_capture=False)
            outputs[label]={'status':response.status.value,'suggestions':len(response.suggestions),
                            'automatic_claim':response.status.value=='matched'}
        negatives.append({'name':name,**outputs})
        print(json.dumps({'negative':negatives[-1]}),flush=True)
    metrics = []
    for group, condition in dict.fromkeys((c['group'], c['condition']) for c in cases):
        subset = [c for c in cases if (c['group'], c['condition']) == (group, condition)]
        metrics.append({'group': group, 'condition': condition, 'probes': len(subset),
            **{label: {metric: sum(c[label][metric] for c in subset) for metric in
                       ('top_correct', 'candidate_recalled', 'automatic_claim', 'automatic_wrong_printing')}
               for label in ('before','after')},
            'recall_regressions': sum(c['before']['candidate_recalled'] and not c['after']['candidate_recalled'] for c in subset)})
    code_files = ['app/recognition/artwork.py','app/recognition/pipeline.py',
                  'app/recognition/local_match.py','app/recognition/rank.py',
                  'app/recognition/orientation.py','app/recognition/runtime.py',
                  'app/recognition/detect.py','app/recognition/frame_fallback.py',
                  'app/recognition/identity.py','app/recognition/printing.py',
                  'app/recognition/metadata.py','app/recognition/confidence.py','app/recognition/presentation.py',
                  'app/schemas.py','app/config.py',
                  'app/recognition/ocr.py','app/recognition/language.py','app/recognition/grading.py',
                  'scripts/benchmark_artwork_pilot.py']
    code_hashes = {p:sha256_file(Path(__file__).resolve().parents[1] / p) for p in code_files}
    print(json.dumps({'summary': {'metrics': metrics, 'artwork_manifest': index.manifest,
        'full_index_rows': len(runtime.snapshot.card_ids), 'cases': len(cases),
        'negatives':negatives, 'code_hashes':code_hashes,
        'source_labels_sha256':sha256_file(args.sources),
        'baseline_comparison': {'report_sha256':sha256_file(args.baseline),
            'before_means':'previous frozen enabled-artwork results',
            'before_code_hashes':baseline['summary']['code_hashes'],
            'before_artwork_manifest':baseline['summary']['artwork_manifest']} if baseline else None,
        'sample': {'photos':len(labels),
                   'diagnostic_subset': bool(args.only),
                   'parent_manifest_photos': parent_count,
                   'distinct_printing_ids':len({p['expected_card_id'] for p in labels}),
                   'languages':dict(Counter(c['provenance']['language'] for c in cases
                       if c['condition']=='raw_photo')),
                   'layouts':dict(Counter(p.get('layout','unspecified') for p in labels)),
                   'conditions':dict(Counter(condition for p in labels for condition in p['conditions']))},
        'settings':runtime.threshold_config(),
        'scope': 'local opt-in pilot; no staging/PlanetScale writes; not calibrated accuracy',
        'no_false_specificity_guarantee': False,
        'note': 'Convenience-sample photos, not representative camera accuracy. Physical artwork patches, if enabled, are manually annotated crops. Reference controls, if enabled, overlap reference data by design. Unknown pretraining overlap; internet photos are not authenticated camera captures. Slab-label OCR may assist identification. Printing identity does not prove finish or authenticity.'}}), flush=True)
    results.close()
    catalog.close()


if __name__ == '__main__':
    main()
