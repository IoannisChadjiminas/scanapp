"""Replay the server ranking on stored scans with one switch off and then on,
and list every scan whose first card or choose list changes.

    cd api && .venv/bin/python scripts/stored_scan_replay/replay_ranking.py \
        <work>/cases.jsonl --flag ocr_cutoff_total \
        --catalog <export>/catalog.sqlite --totals <totals>.sqlite

--flag is a Settings field name (e.g. rank_bare_number_guard). The settings
line written by export_cases.py is applied first, so both runs rank as staging
does apart from the flag; --set name=value overrides single settings.
--catalog/--totals add each card's set total and printed number, which number
rules such as OCR_CUTOFF_TOTAL need (the stored top 20 does not carry them).
Prints card ids and names only, never OCR text.
"""
import argparse
import json
import sqlite3

from app.config import get_settings
from app.recognition.ocr import OcrHit
from app.recognition.printing import PRINTING_CHOICES_WIDER_GAP, assess_printings
from app.recognition.rank import extract_collector_candidates, rerank


def parse_value(raw):
    if raw.lower() in ('true', 'false'):
        return raw.lower() == 'true'
    for kind in (int, float):
        try:
            return kind(raw)
        except ValueError:
            pass
    return raw


def card_details(catalog, totals):
    if not catalog:
        return {}
    by_set = {}
    if totals:
        for lang, set_id, total in sqlite3.connect(totals).execute(
                'select language, set_id, official_total from set_totals'):
            by_set[(lang, str(set_id).split(':')[-1].lower())] = total
    details = {}
    for cid, set_id, lang, printed in sqlite3.connect(catalog).execute(
            'select id, set_id, language, printed_collector_number from cards'):
        details[cid] = (by_set.get((lang, str(set_id or '').split(':')[-1].lower())), printed)
    return details


def candidates(case, details):
    out = []
    for v in case['vis']:
        if v.get('visual_score') is None:
            continue
        v = dict(v, combined_score=v['visual_score'], ocr_consistent=None)
        total, printed = details.get(v['card_id'], (None, None))
        if total:
            v['set_total'] = int(total)
        if printed:
            v['printed_collector_number'] = printed
        out.append(v)
    return out


def rank(case, vis, settings):
    hits = [OcrHit(h['text'], h.get('confidence'), h.get('region') or 'unknown')
            for h in case['hits'] if h.get('text')]
    numbers = extract_collector_candidates(
        [x for x in [case['collector'], *case['lines']] if x], hits=hits)
    name_conf = max((h.confidence or 0.0 for h in hits
                     if h.text == case['name'] and h.region == 'name'), default=0.0)
    langs = (case['lang'],) if case.get('lang') else ()
    ranked = rerank(vis, case['name'], numbers, bool(case.get('failed')),
                    detected_languages=langs, name_confidence=name_conf,
                    require_confident_ocr=True)
    review = assess_printings(
        ranked, family=[], hits=numbers, reference_incomplete=False,
        min_visual=settings.threshold_min_visual, min_gap=settings.threshold_min_gap,
        retake=False,
        wider_gap=PRINTING_CHOICES_WIDER_GAP if settings.printing_choices_wider else 0.0)
    choices = [m['card_id'] for m in review.members] if review.ambiguous else []
    return ranked[0] if ranked else None, choices


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cases')
    ap.add_argument('--flag', required=True)
    ap.add_argument('--set', action='append', default=[], metavar='NAME=VALUE')
    ap.add_argument('--catalog')
    ap.add_argument('--totals')
    args = ap.parse_args()

    settings = get_settings()
    if not hasattr(settings, args.flag):
        ap.error(f'unknown setting {args.flag}')
    lines = open(args.cases)
    first = json.loads(next(lines))
    rows = lines if '_settings' in first else [json.dumps(first), *lines]
    for name, value in (first.get('_settings') or {}).items():
        if hasattr(settings, name):
            setattr(settings, name, value)
    for item in args.set:
        name, _, value = item.partition('=')
        setattr(settings, name, parse_value(value))

    details = card_details(args.catalog, args.totals)
    n = top_changed = choices_changed = 0
    for line in rows:
        case = json.loads(line)
        vis = candidates(case, details)
        if not vis:
            continue
        results = []
        for flag in (False, True):
            setattr(settings, args.flag, flag)
            results.append(rank(case, vis, settings))
        (top_off, list_off), (top_on, list_on) = results
        n += 1
        top_moved = (top_off or {}).get('card_id') != (top_on or {}).get('card_id')
        top_changed += top_moved
        choices_changed += list_off != list_on
        if top_moved or list_off != list_on:
            card = lambda c: c and (c['card_id'], c['name'], c.get('collector_number'))
            print(json.dumps({'scan': (case['id'] or '')[:8], 'date': case['created'],
                              'off': card(top_off), 'on': card(top_on),
                              'choices_off': list_off, 'choices_on': list_on},
                             ensure_ascii=False))
    print(json.dumps({'cases': n, 'top_changed': top_changed, 'choices_changed': choices_changed}))


if __name__ == '__main__':
    main()
