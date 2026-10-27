"""Offline full recognition on stored uploads (plan 2026-10-26, step 0).

Runs the real ``recognize_bytes`` (the full pipeline, not the stage 1 gate) with the staging environment
(``compose.dokploy.yaml``) and a scratch data directory that mirrors the server's layout: the 43,695-row
research index, the research catalogue (with the frozen set totals), the local DINOv2 and PP-OCRv6 models,
reference images, reference features and the artwork bundle. ``persist=False``: nothing is written.

Two case sets:

* ``android_cases.json`` (the 226 Android manual uploads of 25 Oct): the phone's corners and its text were
  not recorded for these, so the text is the server's own read (``--text server``) or none.
* ``phone_cases.json`` (``--phone``): the 201 uploads of 26 Oct whose review record kept what the phone sent.
  The corners, the phone's text with its confidences and the embedding flag are replayed exactly as recorded.
  The embedding itself was not stored, and only the stage 1 gate reads it, which this runner does not run.

It reports how well the offline run reproduces the stored full-pipeline answers (status and first card),
and the per-upload time. Counts and scan ids only go to stdout.

    api/.venv/bin/python api/scripts/full_bench/run_full.py --cases <dir> --data <scratch> --phone
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import statistics
import sys
import time

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
sys.path.insert(0, str(API / 'scripts' / 'stage1_bench'))


def load_env(scratch: Path) -> None:
    """The staging compose defaults, as environment, without overriding anything already set.

    The two bundles staging loads from its container environment are the copies in the scratch folder:
    REFERENCE_FEATURES_DIR (matches the stored results' reference_features version) and ARTWORK_BUNDLE_DIR.
    """
    for key, value in json.loads((scratch / 'staging_env.json').read_text()).items():
        os.environ.setdefault(key, value)
    os.environ['REFERENCE_FEATURES_DIR'] = str(scratch / 'stagebundle' / 'reference-features' / '20261017-ja-sets')
    os.environ['ARTWORK_BUNDLE_DIR'] = str(scratch / 'stagebundle' / 'artwork' / 'PS-CATALOGUE-EN-JA-SETH3-20261017')


def phone_client_text(phone: dict | None, ClientText):
    """The phone's text as the server kept it after parsing (name, confidences, number, candidate texts)."""
    text = (phone or {}).get('client_text')
    if not text:
        return None
    return ClientText(engine=text.get('engine') or 'bench', name=text.get('name'),
                      name_conf=text.get('name_conf'), number=text.get('number'),
                      number_conf=text.get('number_conf'),
                      number_candidates=tuple(text.get('number_candidates') or ()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, required=True, help='folder with the case file and the photos')
    parser.add_argument('--cases-file', default='android_cases.json')
    parser.add_argument('--data', type=Path, required=True, help='scratch data directory (see fulldata)')
    parser.add_argument('--phone', action='store_true',
                        help='replay the phone inputs as recorded (corners, text with confidences)')
    parser.add_argument('--text', choices=('none', 'server'), default='none',
                        help='without --phone: the text the gate gets (server: the server read at 0.95)')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--quad', choices=('none', 'full'), default='none',
                        help='without --phone: card corners sent with the photo (full: the whole upload)')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--foreign-features', action='store_true',
                        help='accept the staging reference bundle on this Mac (its processing contract is '
                             'x86_64 with another OpenCV build). Approximate: features are not byte-identical.')
    args = parser.parse_args()

    load_env(args.data)
    if args.foreign_features:
        from app.recognition import reference_features as _rf
        bundle = json.loads((args.data / 'stagebundle' / 'reference-features' / '20261017-ja-sets'
                             / 'manifest.json').read_text())['processing']
        _rf.processing_contract = lambda: bundle
    from app.config import Settings
    from app.db import connect
    from app.recognition.pipeline import recognize_bytes
    from app.recognition.runtime import Runtime
    from app.recognition.client_text import ClientText
    from app.scan_summary import parse_quad
    import run_bench as rb

    settings = Settings(_env_file=None, data_dir=args.data)
    runtime = Runtime(settings=settings)
    runtime.load()
    if not runtime.ready:
        raise SystemExit(f'runtime not ready: {runtime.error}')
    catalog = connect(args.data / 'catalog.sqlite')
    # The app binds the catalogue after opening it; that is where the reference feature store is attached.
    runtime.bind_card_languages(catalog)

    cases = json.loads((args.cases / args.cases_file).read_text())
    if args.limit:
        cases = cases[:args.limit]
    rows, times = [], []
    counts = Counter()
    for case in cases:
        label = rb.OWNER.get((case.get('ocr_name') or case.get('top_name') or '').strip().lower())
        image = (args.cases / case['input']).read_bytes()
        if args.phone:
            phone = case.get('phone') or {}
            client = phone_client_text(phone, ClientText)
            quad_raw = phone.get('card_quad')
            quad = parse_quad(quad_raw)
            client_reason = 'bench' if client else 'absent'
        else:
            name, number = rb.text_of(case, None, 'server')
            client = None
            if args.text == 'server' and (name or number):
                # The phone reports a confidence per read; the synthetic text uses a confident read (0.95).
                client = ClientText(engine='bench', name=name, number=number, name_conf=0.95, number_conf=0.95)
            quad = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)] if args.quad == 'full' else None
            client_reason = 'bench' if client else 'absent'
        started = time.perf_counter()
        # Route defaults (api/app/routes/scans.py): language auto, graded unset (None), no rotation or crop.
        response = recognize_bytes(image, settings=settings, runtime=runtime, catalog=catalog, results=None,
                                   session_id='bench', persist=False, language='auto', client_text=client,
                                   client_text_reason=client_reason, graded=None, card_quad=quad)
        elapsed = (time.perf_counter() - started) * 1000
        times.append(elapsed)
        status = response.status.value if hasattr(response.status, 'value') else str(response.status)
        shown = response.suggestions[0].card_id if response.suggestions else None
        stored_status, stored_top = case.get('status'), case.get('top')
        row = {'scan': case['scan'], 'status': status, 'shown': shown, 'stored_status': stored_status,
               'stored_top': stored_top, 'label': label, 'ms': round(elapsed, 1),
               'phone_quad': bool(quad), 'phone_text': client is not None}
        row['same_status'] = status == stored_status
        row['same_top'] = bool(shown and stored_top and shown.removeprefix('en:') == stored_top.removeprefix('en:'))
        counts['n'] += 1
        counts['same_status'] += int(row['same_status'])
        counts['same_top'] += int(row['same_top'])
        counts['same_both'] += int(row['same_status'] and row['same_top'])
        if label is not None and shown is not None:
            counts['shown_correct'] += int(shown.removeprefix('en:') == label.removeprefix('en:'))
        rows.append(row)
    summary = {'text': 'phone' if args.phone else args.text, 'quad': 'phone' if args.phone else args.quad,
               'counts': dict(counts),
               'median_ms': round(statistics.median(times), 1) if times else None,
               'p90_ms': round(sorted(times)[int(len(times) * .9) - 1], 1) if times else None}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out:
        args.out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
